// Package outbox implements the transactional outbox pattern: events are
// written in the same PostgreSQL transaction as the domain change they
// describe, then consumed asynchronously by the notifier process.
//
// This guarantees that "database updated but event lost" cannot happen:
// either both the domain change and the outbox row commit, or neither does.
package outbox

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Event is a domain event written to the outbox.
type Event struct {
	ID             string
	EventType      string
	AggregateType  string
	AggregateID    string
	OrganizationID string
	Payload        map[string]any
}

// Store writes and reads outbox events.
type Store struct {
	pool *pgxpool.Pool
}

// New creates an outbox store.
func New(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// Writer is anything that can insert an outbox event within a transaction.
type Writer interface {
	// WriteOutbox inserts an outbox event using tx.
	WriteOutbox(ctx context.Context, tx pgx.Tx, ev Event) error
}

// WriteOnce inserts an outbox event idempotently (by event id). Returns true
// when a new row was inserted, false when it already existed. Used for
// client-idempotent triggers (evidence generation).
func (s *Store) WriteOnce(ctx context.Context, ev Event) (bool, error) {
	payload, err := json.Marshal(ev.Payload)
	if err != nil {
		return false, err
	}
	tag, err := s.pool.Exec(ctx, `INSERT INTO outbox_events
		(id, event_type, aggregate_type, aggregate_id, organization_id, payload)
		VALUES ($1,$2,$3,$4,$5,$6)
		ON CONFLICT (id) DO NOTHING`,
		ev.ID, ev.EventType, ev.AggregateType, ev.AggregateID, sqlNull(ev.OrganizationID), string(payload))
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// Write inserts an outbox event on the given transaction (use with tx from
// the domain transaction). If tx is nil it uses the pool directly.
func (s *Store) Write(ctx context.Context, tx pgx.Tx, ev Event) error {
	payload, err := json.Marshal(ev.Payload)
	if err != nil {
		return fmt.Errorf("outbox: marshal payload: %w", err)
	}
	org := sqlNull(ev.OrganizationID)
	if tx != nil {
		_, err = tx.Exec(ctx, `INSERT INTO outbox_events
			(id, event_type, aggregate_type, aggregate_id, organization_id, payload)
			VALUES ($1,$2,$3,$4,$5,$6)`,
			ev.ID, ev.EventType, ev.AggregateType, ev.AggregateID, org, string(payload))
	} else {
		_, err = s.pool.Exec(ctx, `INSERT INTO outbox_events
			(id, event_type, aggregate_type, aggregate_id, organization_id, payload)
			VALUES ($1,$2,$3,$4,$5,$6)`,
			ev.ID, ev.EventType, ev.AggregateType, ev.AggregateID, org, string(payload))
	}
	if err != nil {
		return fmt.Errorf("outbox: insert event %s: %w", ev.EventType, err)
	}
	return nil
}

// PendingEvent is an event ready for consumption.
type PendingEvent struct {
	ID             string
	EventType      string
	AggregateType  string
	AggregateID    string
	OrganizationID string
	Payload        map[string]any
	Attempt        int
	CreatedAt      time.Time
}

// ClaimPending atomically marks up to limit pending events as processing and
// returns them. The caller must Complete or Fail each.
func (s *Store) ClaimPending(ctx context.Context, limit int) ([]PendingEvent, error) {
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT id FROM outbox_events
			WHERE status = 'pending' AND available_after <= now()
			ORDER BY created_at
			LIMIT $1
			FOR UPDATE SKIP LOCKED
		)
		UPDATE outbox_events e
		SET status = 'processing', attempt = attempt + 1
		FROM candidates c WHERE e.id = c.id
		RETURNING e.id, e.event_type, e.aggregate_type, e.aggregate_id,
		          COALESCE(e.organization_id::text,''), e.payload, e.attempt, e.created_at
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("outbox: claim: %w", err)
	}
	defer rows.Close()
	var out []PendingEvent
	for rows.Next() {
		var ev PendingEvent
		var payload []byte
		if err := rows.Scan(&ev.ID, &ev.EventType, &ev.AggregateType, &ev.AggregateID,
			&ev.OrganizationID, &payload, &ev.Attempt, &ev.CreatedAt); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(payload, &ev.Payload); err != nil {
			return nil, fmt.Errorf("outbox: payload for %s: %w", ev.ID, err)
		}
		out = append(out, ev)
	}
	return out, rows.Err()
}

// Complete marks an event processed.
func (s *Store) Complete(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx, `UPDATE outbox_events SET status='processed', processed_at=now() WHERE id=$1`, id)
	return err
}

// Fail marks an event failed; it becomes available again after backoff unless
// maxAttempts is exceeded, in which case it goes to dead.
func (s *Store) Fail(ctx context.Context, id string, maxAttempts int, backoff time.Duration) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE outbox_events
		SET status = CASE WHEN attempt >= $2 THEN 'dead' ELSE 'pending' END,
		    available_after = CASE WHEN attempt >= $2 THEN available_after ELSE now() + $3 END
		WHERE id = $1`, id, maxAttempts, backoff)
	return err
}

// DeadLetterEvents returns events that permanently failed (for ops tooling).
func (s *Store) DeadLetterEvents(ctx context.Context, limit int) ([]PendingEvent, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, event_type, aggregate_type, aggregate_id, COALESCE(organization_id::text,''), payload, attempt, created_at
		FROM outbox_events WHERE status = 'dead' ORDER BY created_at LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []PendingEvent
	for rows.Next() {
		var ev PendingEvent
		var payload []byte
		if err := rows.Scan(&ev.ID, &ev.EventType, &ev.AggregateType, &ev.AggregateID,
			&ev.OrganizationID, &payload, &ev.Attempt, &ev.CreatedAt); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(payload, &ev.Payload)
		out = append(out, ev)
	}
	return out, rows.Err()
}

// RequeueDead moves dead events back to pending (ops recovery action).
func (s *Store) RequeueDead(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx, `UPDATE outbox_events SET status='pending', available_after=now(), attempt=0 WHERE id=$1 AND status='dead'`, id)
	return err
}

// CountPending returns the number of pending+processing events (ops metric).
func (s *Store) CountPending(ctx context.Context) (int64, error) {
	var n int64
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE status IN ('pending','processing')`).Scan(&n)
	return n, err
}

func sqlNull(s string) any {
	if s == "" {
		return nil
	}
	return s
}
