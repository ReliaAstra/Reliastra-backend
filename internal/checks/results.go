package checks

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// CheckResult is one normalized result of a completed check attempt.
type CheckResult struct {
	ID               string         `json:"id"`
	JobID            string         `json:"job_id"`
	Attempt          int            `json:"attempt"`
	MonitorID        string         `json:"monitor_id"`
	RegionID         string         `json:"region_id"`
	StartedAt        time.Time      `json:"started_at"`
	CompletedAt      time.Time      `json:"completed_at"`
	Success          bool           `json:"success"`
	StatusCode       int            `json:"status_code,omitempty"`
	LatencyMS        int            `json:"latency_ms"`
	DNSMS            int            `json:"dns_ms"`
	ConnectMS        int            `json:"connect_ms"`
	TLSMS            int            `json:"tls_ms"`
	TTFBMS           int            `json:"ttfb_ms"`
	ErrorClass       string         `json:"error_class,omitempty"`
	ErrorCode        string         `json:"error_code,omitempty"`
	ErrorMessage     string         `json:"error_message,omitempty"`
	ResponseSize     int64          `json:"response_size"`
	AssertionsPassed int            `json:"assertions_passed"`
	AssertionsFailed int            `json:"assertions_failed"`
	Metadata         map[string]any `json:"metadata,omitempty"`
	CreatedAt        time.Time      `json:"created_at"`
}

// ResultStore persists check results.
type ResultStore struct {
	pool *pgxpool.Pool
}

// NewResultStore builds a ResultStore.
func NewResultStore(pool *pgxpool.Pool) *ResultStore { return &ResultStore{pool: pool} }

// InsertResult writes a result row on tx (same transaction as job status).
func (s *ResultStore) InsertResult(ctx context.Context, tx pgx.Tx, r *CheckResult) error {
	if r.ID == "" {
		r.ID = ids.NewUUID()
	}
	if r.Metadata == nil {
		r.Metadata = map[string]any{}
	}
	meta, err := json.Marshal(r.Metadata)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `INSERT INTO check_results
		(id, job_id, attempt, monitor_id, region_id, started_at, completed_at, success,
		 status_code, latency_ms, dns_ms, connect_ms, tls_ms, ttfb_ms,
		 error_class, error_code, error_message, response_size,
		 assertions_passed, assertions_failed, metadata)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)`,
		r.ID, r.JobID, r.Attempt, r.MonitorID, r.RegionID, r.StartedAt, r.CompletedAt, r.Success,
		nullableInt(r.StatusCode), r.LatencyMS, r.DNSMS, r.ConnectMS, r.TLSMS, r.TTFBMS,
		r.ErrorClass, r.ErrorCode, r.ErrorMessage, r.ResponseSize,
		r.AssertionsPassed, r.AssertionsFailed, string(meta))
	return err
}

// ListForMonitor returns recent results for a monitor (API).
func (s *ResultStore) ListForMonitor(ctx context.Context, monitorID string, limit int, since time.Time) ([]CheckResult, error) {
	query := `SELECT id, job_id, attempt, monitor_id, region_id, started_at, completed_at, success,
		status_code, latency_ms, dns_ms, connect_ms, tls_ms, ttfb_ms,
		error_class, error_code, error_message, response_size,
		assertions_passed, assertions_failed, metadata, created_at
		FROM check_results WHERE monitor_id = $1`
	args := []any{monitorID}
	if !since.IsZero() {
		query += ` AND completed_at >= $2`
		args = append(args, since)
	}
	query += ` ORDER BY completed_at DESC LIMIT $` + itoa(len(args)+1)
	args = append(args, limit)
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanResults(rows)
}

func scanResults(rows pgx.Rows) ([]CheckResult, error) {
	var out []CheckResult
	for rows.Next() {
		var r CheckResult
		var meta []byte
		var statusCode *int
		if err := rows.Scan(&r.ID, &r.JobID, &r.Attempt, &r.MonitorID, &r.RegionID,
			&r.StartedAt, &r.CompletedAt, &r.Success, &statusCode, &r.LatencyMS,
			&r.DNSMS, &r.ConnectMS, &r.TLSMS, &r.TTFBMS, &r.ErrorClass, &r.ErrorCode,
			&r.ErrorMessage, &r.ResponseSize, &r.AssertionsPassed, &r.AssertionsFailed,
			&meta, &r.CreatedAt); err != nil {
			return nil, err
		}
		if statusCode != nil {
			r.StatusCode = *statusCode
		}
		_ = json.Unmarshal(meta, &r.Metadata)
		out = append(out, r)
	}
	return out, rows.Err()
}

func nullableInt(v int) any {
	if v == 0 {
		return nil
	}
	return v
}

func itoa(n int) string {
	if n < 10 {
		return string(rune('0' + n))
	}
	return itoa(n/10) + string(rune('0'+n%10))
}
