package notifications

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Store persists channels and deliveries.
type Store struct {
	pool *pgxpool.Pool
	enc  Encryptor
}

// Encryptor encrypts channel configs at rest.
type Encryptor interface {
	Encrypt(plaintext []byte) (string, error)
	Decrypt(serialized string) ([]byte, error)
	KeyVersion() int
}

// NewStore builds the Store.
func NewStore(pool *pgxpool.Pool, enc Encryptor) *Store { return &Store{pool: pool, enc: enc} }

// UpsertChannel creates or updates a channel with encrypted config.
func (s *Store) UpsertChannel(ctx context.Context, orgID, id, typ, name string, enabled bool, cfg map[string]string) (*Channel, error) {
	if id == "" {
		id = ids.NewUUID()
	}
	raw, _ := json.Marshal(cfg)
	enc, err := s.enc.Encrypt(raw)
	if err != nil {
		return nil, err
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO notification_channels
		(id, organization_id, type, name, config_encrypted, key_version, nonce, enabled)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name,
			config_encrypted=EXCLUDED.config_encrypted, enabled=EXCLUDED.enabled, updated_at=now()`,
		id, orgID, typ, name, []byte(enc), s.enc.KeyVersion(), []byte(""), enabled)
	if err != nil {
		return nil, err
	}
	return &Channel{ID: id, OrganizationID: orgID, Type: typ, Name: name, Enabled: enabled, Config: cfg}, nil
}

// ListChannels returns org channels with decrypted configs.
func (s *Store) ListChannels(ctx context.Context, orgID string) ([]Channel, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, organization_id, type, name, config_encrypted, enabled, created_at, updated_at
		FROM notification_channels WHERE organization_id=$1 ORDER BY created_at`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Channel
	for rows.Next() {
		var c Channel
		var enc []byte
		if err := rows.Scan(&c.ID, &c.OrganizationID, &c.Type, &c.Name, &enc, &c.Enabled,
			&c.CreatedAt, &c.UpdatedAt); err != nil {
			return nil, err
		}
		cfg, err := s.decrypt(enc)
		if err == nil {
			c.Config = cfg
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

func (s *Store) decrypt(enc []byte) (map[string]string, error) {
	plain, err := s.enc.Decrypt(string(enc))
	if err != nil {
		return nil, err
	}
	var cfg map[string]string
	if err := json.Unmarshal(plain, &cfg); err != nil {
		return nil, err
	}
	return cfg, nil
}

// EnabledChannels returns enabled channels for an org with configs.
func (s *Store) EnabledChannels(ctx context.Context, orgID string) ([]Channel, error) {
	all, err := s.ListChannels(ctx, orgID)
	if err != nil {
		return nil, err
	}
	var out []Channel
	for _, c := range all {
		if c.Enabled {
			out = append(out, c)
		}
	}
	return out, nil
}

// DeleteChannel removes a channel (org-scoped).
func (s *Store) DeleteChannel(ctx context.Context, orgID, id string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM notification_channels WHERE id=$1 AND organization_id=$2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("channel_not_found", "notification channel not found")
	}
	return nil
}

// CreateDeliveries enqueues one delivery per enabled channel for an event.
// Idempotent: the unique (event_id, channel_id) constraint makes duplicate
// outbox consumption harmless.
func (s *Store) CreateDeliveries(ctx context.Context, orgID, eventID, eventType string) (int, error) {
	channels, err := s.EnabledChannels(ctx, orgID)
	if err != nil {
		return 0, err
	}
	created := 0
	for _, ch := range channels {
		_, err := s.pool.Exec(ctx, `INSERT INTO notification_deliveries
			(id, organization_id, event_id, channel_id, event_type, status)
			VALUES ($1,$2,$3,$4,$5,'pending')
			ON CONFLICT (event_id, channel_id) DO NOTHING`,
			ids.NewUUID(), orgID, eventID, ch.ID, eventType)
		if err != nil {
			return created, err
		}
		created++
	}
	return created, nil
}

// ClaimDueDeliveries atomically leases due deliveries for sending.
func (s *Store) ClaimDueDeliveries(ctx context.Context, limit int) ([]Delivery, error) {
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT id FROM notification_deliveries
			WHERE status IN ('pending','retrying') AND (next_attempt_at IS NULL OR next_attempt_at <= now())
			ORDER BY created_at LIMIT $1 FOR UPDATE SKIP LOCKED
		)
		UPDATE notification_deliveries d SET status='sending', attempt = attempt + 1
		FROM candidates c WHERE d.id = c.id
		RETURNING d.id, d.organization_id, d.event_id, d.channel_id, d.event_type, d.status, d.attempt, d.created_at`,
		limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Delivery
	for rows.Next() {
		var d Delivery
		if err := rows.Scan(&d.ID, &d.OrganizationID, &d.EventID, &d.ChannelID, &d.EventType,
			&d.Status, &d.Attempt, &d.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

// MarkSent records a successful delivery.
func (s *Store) MarkSent(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx, `UPDATE notification_deliveries SET status='sent', sent_at=now(), last_error=''
		WHERE id=$1`, id)
	return err
}

// MarkRetry schedules a retry with backoff.
func (s *Store) MarkRetry(ctx context.Context, id string, attempt int, nextAttempt time.Time, lastErr string) error {
	_, err := s.pool.Exec(ctx, `UPDATE notification_deliveries
		SET status='retrying', attempt=$2, next_attempt_at=$3, last_error=$4 WHERE id=$1`,
		id, attempt, nextAttempt, truncateErr(lastErr))
	return err
}

// MarkDeadLetter marks a delivery permanently failed.
func (s *Store) MarkDeadLetter(ctx context.Context, id string, lastErr string) error {
	_, err := s.pool.Exec(ctx, `UPDATE notification_deliveries
		SET status='dead_letter', last_error=$2 WHERE id=$1`, id, truncateErr(lastErr))
	return err
}

// ChannelByID returns a channel with config (used by the sender).
func (s *Store) ChannelByID(ctx context.Context, id string) (*Channel, error) {
	row := s.pool.QueryRow(ctx, `SELECT id, organization_id, type, name, config_encrypted, enabled, created_at, updated_at
		FROM notification_channels WHERE id=$1`, id)
	var c Channel
	var enc []byte
	err := row.Scan(&c.ID, &c.OrganizationID, &c.Type, &c.Name, &enc, &c.Enabled, &c.CreatedAt, &c.UpdatedAt)
	if err != nil {
		return nil, err
	}
	if cfg, err := s.decrypt(enc); err == nil {
		c.Config = cfg
	}
	return &c, nil
}

func truncateErr(s string) string {
	if len(s) > 500 {
		return s[:500]
	}
	return s
}

// unused guard
var _ = pgx.ErrNoRows
