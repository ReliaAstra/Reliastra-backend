package evidence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/errors"
	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Store persists evidence records.
type Store struct {
	pool *pgxpool.Pool
}

// NewStore builds a Store.
func NewStore(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// cols is used for evidence_records alone; joined queries must qualify the
// id column (er.id) to avoid ambiguity.
const cols = `id, incident_id, version, status, generated_at, methodology_version,
	hash_algorithm, hash, storage_key, size_bytes, failure_reason, created_at`

const colsQualified = `er.id, er.incident_id, er.version, er.status, er.generated_at, er.methodology_version,
	er.hash_algorithm, er.hash, er.storage_key, er.size_bytes, er.failure_reason, er.created_at`

func scan(row pgx.Row) (*EvidenceRecord, error) {
	var r EvidenceRecord
	err := row.Scan(&r.ID, &r.IncidentID, &r.Version, &r.Status, &r.GeneratedAt,
		&r.MethodologyVersion, &r.HashAlgorithm, &r.Hash, &r.StorageKey, &r.SizeBytes,
		&r.FailureReason, &r.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, errors.NotFound("evidence_not_found", "evidence record not found")
	}
	if err != nil {
		return nil, err
	}
	return &r, nil
}

// BeginGeneration claims the next version for an incident (status=generating).
// If a previous generation attempt left a generating record, it is reused.
func (s *Store) BeginGeneration(ctx context.Context, incidentID, methodology string) (*EvidenceRecord, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Reuse an in-flight generation to avoid duplicate versions.
	var existing EvidenceRecord
	err = tx.QueryRow(ctx, `SELECT `+cols+` FROM evidence_records
		WHERE incident_id=$1 AND status='generating' ORDER BY version DESC LIMIT 1`,
		incidentID).Scan(&existing.ID, &existing.IncidentID, &existing.Version, &existing.Status,
		&existing.GeneratedAt, &existing.MethodologyVersion, &existing.HashAlgorithm,
		&existing.Hash, &existing.StorageKey, &existing.SizeBytes, &existing.FailureReason,
		&existing.CreatedAt)
	if err == nil {
		if err := tx.Commit(ctx); err != nil {
			return nil, err
		}
		return &existing, nil
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}

	var maxVer *int
	if err := tx.QueryRow(ctx, `SELECT max(version) FROM evidence_records WHERE incident_id=$1`,
		incidentID).Scan(&maxVer); err != nil {
		return nil, err
	}
	version := 1
	if maxVer != nil {
		version = *maxVer + 1
	}
	rec := &EvidenceRecord{
		ID: ids.NewUUID(), IncidentID: incidentID, Version: version,
		Status: StatusGenerating, MethodologyVersion: methodology,
		HashAlgorithm: "sha256",
	}
	_, err = tx.Exec(ctx, `INSERT INTO evidence_records
		(id, incident_id, version, status, methodology_version, hash_algorithm)
		VALUES ($1,$2,$3,$4,$5,$6)`,
		rec.ID, rec.IncidentID, rec.Version, rec.Status, rec.MethodologyVersion, rec.HashAlgorithm)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return rec, nil
}

// Finalize marks a record finalized with its hash and storage key.
func (s *Store) Finalize(ctx context.Context, rec *EvidenceRecord, hash, storageKey string, size int64) error {
	_, err := s.pool.Exec(ctx, `UPDATE evidence_records
		SET status='finalized', generated_at=now(), hash=$2, storage_key=$3, size_bytes=$4, failure_reason=''
		WHERE id=$1 AND status='generating'`, rec.ID, hash, storageKey, size)
	rec.Status = StatusFinalized
	rec.Hash = hash
	rec.StorageKey = storageKey
	rec.SizeBytes = size
	now := time.Now().UTC()
	rec.GeneratedAt = &now
	return err
}

// MarkFailed records a generation failure so retries can reuse the version.
func (s *Store) MarkFailed(ctx context.Context, rec *EvidenceRecord, reason string) error {
	_, err := s.pool.Exec(ctx, `UPDATE evidence_records
		SET status='failed', failure_reason=$2 WHERE id=$1 AND status='generating'`,
		rec.ID, reason)
	rec.Status = StatusFailed
	rec.FailureReason = reason
	return err
}

// ByID returns a record scoped to the org via the incident.
func (s *Store) ByID(ctx context.Context, orgID, id string) (*EvidenceRecord, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+colsQualified+` FROM evidence_records er
		JOIN incidents i ON i.id = er.incident_id
		WHERE er.id=$1 AND i.organization_id=$2`, id, orgID)
	return scan(row)
}

// ListForIncident returns records for an incident (org-scoped).
func (s *Store) ListForIncident(ctx context.Context, orgID, incidentID string) ([]EvidenceRecord, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+colsQualified+` FROM evidence_records er
		JOIN incidents i ON i.id = er.incident_id
		WHERE er.incident_id=$1 AND i.organization_id=$2
		ORDER BY er.version`, incidentID, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []EvidenceRecord
	for rows.Next() {
		r, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *r)
	}
	return out, rows.Err()
}

// LatestForIncident returns the latest record for an incident (internal).
func (s *Store) LatestForIncident(ctx context.Context, incidentID string) (*EvidenceRecord, error) {
	row := s.pool.QueryRow(ctx, `SELECT `+cols+` FROM evidence_records
		WHERE incident_id=$1 ORDER BY version DESC LIMIT 1`, incidentID)
	return scan(row)
}

// CountFinalized returns finalized count (ops metric).
func (s *Store) CountFinalized(ctx context.Context) (int64, error) {
	var n int64
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM evidence_records WHERE status='finalized'`).Scan(&n)
	return n, err
}
