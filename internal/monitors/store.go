package monitors

import (
	"context"
	"encoding/json"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Store persists monitors, their region assignments and encrypted secrets.
type Store struct {
	pool    *pgxpool.Pool
	enc     Encryptor
}

// Encryptor encrypts/decrypts monitor secrets (see platform/encryption).
type Encryptor interface {
	Encrypt(plaintext []byte) (string, error)
	Decrypt(serialized string) ([]byte, error)
	KeyVersion() int
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool, enc Encryptor) *Store {
	return &Store{pool: pool, enc: enc}
}

const cols = `id, project_id, organization_id, service_id, dependency_id, vendor_id,
	name, type, target, configuration, interval_seconds, timeout_seconds, max_attempts,
	enabled, visibility, status, created_at, updated_at`

func scanMonitor(row pgx.Row) (*Monitor, error) {
	var m Monitor
	var projectID, organizationID, serviceID, dependencyID, vendorID *string
	err := row.Scan(&m.ID, &projectID, &organizationID, &serviceID, &dependencyID, &vendorID,
		&m.Name, &m.Type, &m.Target, &m.Configuration, &m.IntervalSeconds, &m.TimeoutSeconds, &m.MaxAttempts,
		&m.Enabled, &m.Visibility, &m.Status, &m.CreatedAt, &m.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("monitor_not_found", "monitor not found")
	}
	if err != nil {
		return nil, err
	}
	if projectID != nil {
		m.ProjectID = *projectID
	}
	if organizationID != nil {
		m.OrganizationID = *organizationID
	}
	if serviceID != nil {
		m.ServiceID = *serviceID
	}
	if dependencyID != nil {
		m.DependencyID = *dependencyID
	}
	if vendorID != nil {
		m.VendorID = *vendorID
	}
	return &m, nil
}

// validateTargets ensures service_id/dependency_id belong to orgID and that
// they are mutually exclusive (at least one required).
func (s *Store) validateTargets(ctx context.Context, orgID, serviceID, dependencyID string) error {
	if serviceID != "" && dependencyID != "" {
		return errors.Validation("invalid_target", "a monitor targets either a service or a dependency, not both", nil)
	}
	if serviceID != "" {
		var one int
		err := s.pool.QueryRow(ctx, `
			SELECT 1 FROM services sv JOIN projects p ON p.id = sv.project_id
			WHERE sv.id=$1 AND p.organization_id=$2`, serviceID, orgID).Scan(&one)
		if err == pgx.ErrNoRows {
			return errors.NotFound("service_not_found", "service not found in this organization")
		}
		if err != nil {
			return err
		}
	}
	if dependencyID != "" {
		var one int
		err := s.pool.QueryRow(ctx, `
			SELECT 1 FROM dependencies d JOIN projects p ON p.id = d.project_id
			WHERE d.id=$1 AND p.organization_id=$2`, dependencyID, orgID).Scan(&one)
		if err == pgx.ErrNoRows {
			return errors.NotFound("dependency_not_found", "dependency not found in this organization")
		}
		if err != nil {
			return err
		}
	}
	if serviceID == "" && dependencyID == "" {
		return errors.Validation("invalid_target", "a customer monitor must target a service or a dependency", nil)
	}
	return nil
}

// validateRegions ensures all region ids exist and are active.
func (s *Store) validateRegions(ctx context.Context, regionIDs []string) error {
	for _, rid := range regionIDs {
		var one int
		err := s.pool.QueryRow(ctx, `SELECT 1 FROM regions WHERE id=$1 AND status='active'`, rid).Scan(&one)
		if err == pgx.ErrNoRows {
			return errors.Validation("invalid_region", "unknown or inactive region", map[string]any{"region_id": rid})
		}
		if err != nil {
			return err
		}
	}
	return nil
}

// Create inserts a customer monitor with its regions and encrypted secrets in
// one transaction.
func (s *Store) Create(ctx context.Context, orgID string, m *Monitor, regionIDs []string, secrets map[string]string, secretBody string) (*Monitor, error) {
	if err := s.validateTargets(ctx, orgID, m.ServiceID, m.DependencyID); err != nil {
		return nil, err
	}
	if len(regionIDs) == 0 {
		return nil, errors.Validation("regions_required", "at least one observation region is required", nil)
	}
	if err := s.validateRegions(ctx, regionIDs); err != nil {
		return nil, err
	}
	m.ID = ids.NewUUID()
	m.OrganizationID = orgID
	m.Visibility = "customer"
	m.Status = "active"
	m.NextRunAt = time.Now().UTC()

	// Encrypt secrets (headers + optional body).
	var secretJSON []byte
	if len(secrets) > 0 || secretBody != "" {
		payload := map[string]any{"headers": secrets}
		if secretBody != "" {
			payload["body"] = secretBody
		}
		raw, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		enc, err := s.enc.Encrypt(raw)
		if err != nil {
			return nil, errors.Internal("encryption_failed", "failed to secure monitor credentials")
		}
		secretJSON = []byte(enc)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	_, err = tx.Exec(ctx, `INSERT INTO monitors
		(id, project_id, organization_id, service_id, dependency_id, name, type, target,
		 configuration, interval_seconds, timeout_seconds, max_attempts, enabled, next_run_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, now())`,
		m.ID, sqlNull(m.ProjectID), orgID, sqlNull(m.ServiceID), sqlNull(m.DependencyID),
		m.Name, m.Type, m.Target, m.Configuration, m.IntervalSeconds, m.TimeoutSeconds, m.MaxAttempts, m.Enabled)
	if err != nil {
		return nil, err
	}
	for _, rid := range regionIDs {
		if _, err := tx.Exec(ctx,
			`INSERT INTO monitor_regions (monitor_id, region_id) VALUES ($1,$2)`, m.ID, rid); err != nil {
			return nil, err
		}
	}
	if len(secretJSON) > 0 {
		if _, err := tx.Exec(ctx, `INSERT INTO monitor_secrets (monitor_id, ciphertext, key_version, nonce)
			VALUES ($1, $2, $3, $4)`, m.ID, []byte(secretJSON), s.enc.KeyVersion(), []byte("")); err != nil {
			return nil, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return m, nil
}

// ByID returns a customer monitor scoped to the org.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*Monitor, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM monitors WHERE id=$1 AND organization_id=$2 AND visibility='customer'`, id, orgID)
	m, err := scanMonitor(row)
	if err != nil {
		return nil, err
	}
	return m, nil
}

// ByIDAny returns a monitor regardless of visibility (internal use).
func (s *Store) ByIDAny(ctx context.Context, id string) (*Monitor, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM monitors WHERE id=$1`, id)
	return scanMonitor(row)
}

// List returns customer monitors in an org with optional filters.
func (s *Store) List(ctx context.Context, orgID, projectID string, enabled *bool) ([]Monitor, error) {
	query := `SELECT ` + cols + ` FROM monitors WHERE organization_id=$1 AND visibility='customer'`
	args := []any{orgID}
	if projectID != "" {
		query += ` AND project_id = $2`
		args = append(args, projectID)
	}
	if enabled != nil {
		query += ` AND enabled = $` + itoa(len(args)+1)
		args = append(args, *enabled)
	}
	query += ` ORDER BY created_at`
	return s.queryMonitors(ctx, query, args...)
}

func (s *Store) queryMonitors(ctx context.Context, query string, args ...any) ([]Monitor, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Monitor
	for rows.Next() {
		m, err := scanMonitor(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *m)
	}
	return out, rows.Err()
}

// Regions returns the region ids assigned to a monitor.
func (s *Store) Regions(ctx context.Context, monitorID string) ([]string, error) {
	rows, err := s.pool.Query(ctx, `SELECT region_id FROM monitor_regions WHERE monitor_id=$1 ORDER BY created_at`, monitorID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

// Update patches a monitor (config, intervals, enabled, regions, secrets).
func (s *Store) Update(ctx context.Context, orgID, id string, patch map[string]any, regionIDs []string, secrets map[string]string, secretBody string) (*Monitor, error) {
	existing, err := s.ByID(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	if v, ok := patch["name"]; ok {
		existing.Name = v.(string)
	}
	if v, ok := patch["target"]; ok {
		existing.Target = v.(string)
	}
	if v, ok := patch["configuration"]; ok {
		existing.Configuration = v.(json.RawMessage)
	}
	if v, ok := patch["interval_seconds"]; ok {
		existing.IntervalSeconds = v.(int)
	}
	if v, ok := patch["timeout_seconds"]; ok {
		existing.TimeoutSeconds = v.(int)
	}
	if v, ok := patch["max_attempts"]; ok {
		existing.MaxAttempts = v.(int)
	}
	if v, ok := patch["enabled"]; ok {
		existing.Enabled = v.(bool)
	}
	_, err = s.pool.Exec(ctx, `UPDATE monitors SET name=$1, target=$2, configuration=$3,
		interval_seconds=$4, timeout_seconds=$5, max_attempts=$6, enabled=$7, updated_at=now()
		WHERE id=$8 AND organization_id=$9`,
		existing.Name, existing.Target, existing.Configuration, existing.IntervalSeconds,
		existing.TimeoutSeconds, existing.MaxAttempts, existing.Enabled, existing.ID, orgID)
	if err != nil {
		return nil, err
	}
	if regionIDs != nil {
		tx, err := s.pool.Begin(ctx)
		if err != nil {
			return nil, err
		}
		defer tx.Rollback(ctx) //nolint:errcheck
		if _, err := tx.Exec(ctx, `DELETE FROM monitor_regions WHERE monitor_id=$1`, existing.ID); err != nil {
			return nil, err
		}
		for _, rid := range regionIDs {
			if _, err := tx.Exec(ctx, `INSERT INTO monitor_regions (monitor_id, region_id) VALUES ($1,$2)`, existing.ID, rid); err != nil {
				return nil, err
			}
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, err
		}
	}
	if secrets != nil || secretBody != "" {
		payload := map[string]any{"headers": secrets}
		if secretBody != "" {
			payload["body"] = secretBody
		}
		raw, _ := json.Marshal(payload)
		enc, err := s.enc.Encrypt(raw)
		if err != nil {
			return nil, errors.Internal("encryption_failed", "failed to secure monitor credentials")
		}
		if _, err := s.pool.Exec(ctx, `INSERT INTO monitor_secrets (monitor_id, ciphertext, key_version, nonce)
			VALUES ($1,$2,$3,$4)
			ON CONFLICT (monitor_id) DO UPDATE SET ciphertext=EXCLUDED.ciphertext, updated_at=now()`,
			existing.ID, []byte(enc), s.enc.KeyVersion(), []byte("")); err != nil {
			return nil, err
		}
	}
	return existing, nil
}

// Delete removes a monitor.
func (s *Store) Delete(ctx context.Context, orgID, id string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM monitors WHERE id=$1 AND organization_id=$2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.NotFound("monitor_not_found", "monitor not found")
	}
	return nil
}

// DecryptSecrets returns the decrypted header secrets + body for a monitor.
func (s *Store) DecryptSecrets(ctx context.Context, monitorID string) (map[string]string, string, error) {
	var ciphertext []byte
	err := s.pool.QueryRow(ctx, `SELECT ciphertext FROM monitor_secrets WHERE monitor_id=$1`, monitorID).Scan(&ciphertext)
	if err == pgx.ErrNoRows {
		return nil, "", nil
	}
	if err != nil {
		return nil, "", err
	}
	plain, err := s.enc.Decrypt(string(ciphertext))
	if err != nil {
		return nil, "", errors.Internal("decryption_failed", "failed to decrypt monitor credentials")
	}
	var payload struct {
		Headers map[string]string `json:"headers"`
		Body    string            `json:"body"`
	}
	if err := json.Unmarshal(plain, &payload); err != nil {
		return nil, "", errors.Internal("decryption_failed", "failed to decrypt monitor credentials")
	}
	if payload.Headers == nil {
		payload.Headers = map[string]string{}
	}
	return payload.Headers, payload.Body, nil
}

// CountByOrg returns the number of customer monitors in an org.
func (s *Store) CountByOrg(ctx context.Context, orgID string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM monitors WHERE organization_id=$1 AND visibility='customer'`, orgID).Scan(&n)
	return n, err
}

// DueMonitors returns enabled monitors whose next_run_at is within the
// lookahead window, oldest first (scheduler query). next_run_at is loaded so
// the scheduler can detect missed runs and advance deterministically.
func (s *Store) DueMonitors(ctx context.Context, lookahead time.Duration, batch int) ([]Monitor, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+cols+`, next_run_at
		FROM monitors
		WHERE enabled = true AND status = 'active' AND next_run_at <= now() + $1
		ORDER BY next_run_at
		LIMIT $2`, lookahead, batch)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Monitor
	for rows.Next() {
		var m Monitor
		var projectID, organizationID, serviceID, dependencyID, vendorID *string
		if err := rows.Scan(&m.ID, &projectID, &organizationID, &serviceID, &dependencyID, &vendorID,
			&m.Name, &m.Type, &m.Target, &m.Configuration, &m.IntervalSeconds, &m.TimeoutSeconds, &m.MaxAttempts,
			&m.Enabled, &m.Visibility, &m.Status, &m.CreatedAt, &m.UpdatedAt, &m.NextRunAt); err != nil {
			return nil, err
		}
		if projectID != nil {
			m.ProjectID = *projectID
		}
		if organizationID != nil {
			m.OrganizationID = *organizationID
		}
		if serviceID != nil {
			m.ServiceID = *serviceID
		}
		if dependencyID != nil {
			m.DependencyID = *dependencyID
		}
		if vendorID != nil {
			m.VendorID = *vendorID
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// AdvanceNextRun moves a monitor's next_run_at forward by its interval.
// The update is conditional on the current value to remain safe under
// concurrent schedulers.
func (s *Store) AdvanceNextRun(ctx context.Context, monitorID string, current time.Time, interval time.Duration) error {
	_, err := s.pool.Exec(ctx, `UPDATE monitors SET next_run_at = $1 WHERE id = $2 AND next_run_at = $3`,
		current.Add(interval), monitorID, current)
	return err
}

// SetNextRun pins next_run_at (used when monitors are created/updated).
func (s *Store) SetNextRun(ctx context.Context, monitorID string, t time.Time) error {
	_, err := s.pool.Exec(ctx, `UPDATE monitors SET next_run_at=$1 WHERE id=$2`, t, monitorID)
	return err
}

// ListAllRegions returns all active regions (for scheduler job creation).
func (s *Store) ListRegionsForMonitor(ctx context.Context, monitorID string) ([]string, error) {
	return s.Regions(ctx, monitorID)
}

func sqlNull(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func itoa(n int) string { return strconv.Itoa(n) }
