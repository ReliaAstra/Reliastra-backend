package incidents

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Store persists incidents, their events and correlations.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

const cols = `id, number, project_id, organization_id, service_id, dependency_id,
	status, severity, started_at, detected_at, resolved_at, title, summary,
	attributed_dependency_id, confidence, evidence_score, correlation_version, created_at, updated_at`

func scanIncident(row pgx.Row) (*Incident, error) {
	var i Incident
	var serviceID, dependencyID, attributedDependencyID *string
	err := row.Scan(&i.ID, &i.Number, &i.ProjectID, &i.OrganizationID, &serviceID, &dependencyID,
		&i.Status, &i.Severity, &i.StartedAt, &i.DetectedAt, &i.ResolvedAt, &i.Title, &i.Summary,
		&attributedDependencyID, &i.Confidence, &i.EvidenceScore, &i.CorrelationVersion,
		&i.CreatedAt, &i.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("incident_not_found", "incident not found")
	}
	if err != nil {
		return nil, err
	}
	if serviceID != nil {
		i.ServiceID = *serviceID
	}
	if dependencyID != nil {
		i.DependencyID = *dependencyID
	}
	if attributedDependencyID != nil {
		i.AttributedDependencyID = *attributedDependencyID
	}
	return &i, nil
}

// NextNumber allocates the next incident number for a year (atomic). It runs
// on the caller's transaction: the sequence update must be atomic with the
// incident insert, and using the pool while a transaction is open would
// deadlock pools with MaxConns=1.
func (s *Store) NextNumber(ctx context.Context, tx pgx.Tx, year int) (string, error) {
	var seq int64
	err := tx.QueryRow(ctx, `
		INSERT INTO incident_sequences (year, last_value) VALUES ($1, 1)
		ON CONFLICT (year) DO UPDATE SET last_value = incident_sequences.last_value + 1
		RETURNING last_value`, year).Scan(&seq)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("INC-%d-%06d", year, seq), nil
}

// Create inserts a new incident with its initial event, in a transaction.
// Returns the incident and the allocated number.
func (s *Store) Create(ctx context.Context, tx pgx.Tx, i *Incident) (*Incident, error) {
	if i.ID == "" {
		i.ID = ids.NewUUID()
	}
	now := time.Now().UTC()
	if i.DetectedAt.IsZero() {
		i.DetectedAt = now
	}
	if i.StartedAt.IsZero() {
		i.StartedAt = now
	}
	if i.CreatedAt.IsZero() {
		i.CreatedAt = now
	}
	i.UpdatedAt = now
	_, err := tx.Exec(ctx, `INSERT INTO incidents
		(id, number, project_id, organization_id, service_id, dependency_id,
		 status, severity, started_at, detected_at, title, summary)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
		i.ID, i.Number, i.ProjectID, i.OrganizationID, nullable(i.ServiceID), nullable(i.DependencyID),
		i.Status, i.Severity, i.StartedAt, i.DetectedAt, i.Title, i.Summary)
	if err != nil {
		return nil, err
	}
	return i, nil
}

// OpenForTarget returns the open incident for a target, if any. The target
// is identified by (service_id, dependency_id) with either side NULL; NULL
// must match NULL, so IS NOT DISTINCT FROM is required.
func (s *Store) OpenForTarget(ctx context.Context, serviceID, dependencyID string) (*Incident, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM incidents
		WHERE service_id IS NOT DISTINCT FROM $1
		  AND dependency_id IS NOT DISTINCT FROM $2
		  AND status IN ('candidate','investigating','confirmed')
		ORDER BY created_at DESC LIMIT 1`,
		nullable(serviceID), nullable(dependencyID))
	return scanIncident(row)
}

// ByID returns an incident scoped to an org.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*Incident, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM incidents WHERE id=$1 AND organization_id=$2`, id, orgID)
	return scanIncident(row)
}

// ByIDAny returns an incident by id regardless of org (internal processes).
func (s *Store) ByIDAny(ctx context.Context, id string) (*Incident, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM incidents WHERE id=$1`, id)
	return scanIncident(row)
}

// ByNumber returns an incident by its INC-... number (scoped to org).
func (s *Store) ByNumber(ctx context.Context, orgID, number string) (*Incident, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM incidents WHERE number=$1 AND organization_id=$2`, number, orgID)
	return scanIncident(row)
}

// List returns incidents for an org with optional status/project filters.
func (s *Store) List(ctx context.Context, orgID, projectID, status string, limit, offset int) ([]Incident, error) {
	query := `SELECT ` + cols + ` FROM incidents WHERE organization_id=$1`
	args := []any{orgID}
	if projectID != "" {
		query += ` AND project_id = $` + itoa(len(args)+1)
		args = append(args, projectID)
	}
	if status != "" {
		query += ` AND status = $` + itoa(len(args)+1)
		args = append(args, status)
	}
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	query += ` ORDER BY created_at DESC LIMIT $` + itoa(len(args)+1) + ` OFFSET $` + itoa(len(args)+2)
	args = append(args, limit, offset)
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Incident
	for rows.Next() {
		i, err := scanIncident(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *i)
	}
	return out, rows.Err()
}

// Transition applies a state transition atomically: updates the incident and
// inserts the audit event. Returns ErrInvalidTransition when disallowed and
// a conflict error when the expected from-status no longer holds.
func (s *Store) Transition(ctx context.Context, tx pgx.Tx, inc *Incident, to, reason, actorType, actorID string, metadata map[string]any) error {
	if !CanTransition(inc.Status, to) {
		return &ErrInvalidTransition{From: inc.Status, To: to}
	}
	now := time.Now().UTC()
	var resolvedAt any
	if to == StatusResolved {
		resolvedAt = now
	}
	tag, err := tx.Exec(ctx, `UPDATE incidents SET status=$2, resolved_at=$3, updated_at=now()
		WHERE id=$1 AND status=$4`, inc.ID, to, resolvedAt, inc.Status)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.Conflict("incident_state_changed", "incident changed state concurrently; re-read and retry")
	}
	meta, _ := json.Marshal(metadata)
	_, err = tx.Exec(ctx, `INSERT INTO incident_events
		(id, incident_id, from_status, to_status, reason, actor_type, actor_id, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		ids.NewUUID(), inc.ID, inc.Status, to, reason, actorType, actorID, string(meta))
	if err != nil {
		return err
	}
	inc.Status = to
	if to == StatusResolved {
		inc.ResolvedAt = &now
	}
	inc.UpdatedAt = now
	return nil
}

// ListEvents returns the transition history for an incident.
func (s *Store) ListEvents(ctx context.Context, incidentID string) ([]IncidentEvent, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, incident_id, from_status, to_status, reason,
		actor_type, actor_id, metadata, created_at
		FROM incident_events WHERE incident_id=$1 ORDER BY created_at`, incidentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []IncidentEvent
	for rows.Next() {
		var e IncidentEvent
		var meta []byte
		if err := rows.Scan(&e.ID, &e.IncidentID, &e.FromStatus, &e.ToStatus, &e.Reason,
			&e.ActorType, &e.ActorID, &meta, &e.CreatedAt); err != nil {
			return nil, err
		}
		_ = json.Unmarshal(meta, &e.Metadata)
		out = append(out, e)
	}
	return out, rows.Err()
}

// UpdateAttribution writes correlation results onto the incident.
func (s *Store) UpdateAttribution(ctx context.Context, tx pgx.Tx, incID, dependencyID, confidence, version string, score float64) error {
	_, err := tx.Exec(ctx, `UPDATE incidents SET attributed_dependency_id=$2, confidence=$3,
		evidence_score=$4, correlation_version=$5, updated_at=now() WHERE id=$1`,
		incID, nullable(dependencyID), confidence, score, version)
	return err
}

// CountOpen returns the number of open incidents for an org (ops metric).
func (s *Store) CountOpen(ctx context.Context, orgID string) (int64, error) {
	var n int64
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM incidents
		WHERE organization_id=$1 AND status IN ('candidate','investigating','confirmed')`, orgID).Scan(&n)
	return n, err
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func itoa(n int) string {
	if n < 10 {
		return string(rune('0' + n))
	}
	return itoa(n/10) + string(rune('0'+n%10))
}
