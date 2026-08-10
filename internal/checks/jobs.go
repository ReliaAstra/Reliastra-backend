// Package checks implements the durable execution engine: check jobs,
// leasing, scheduling, worker execution, results and normalized observations.
//
// Concurrency model (documented in docs/architecture/job-execution.md):
//   - Jobs are created idempotently (unique monitor+region+scheduled_for).
//   - Workers acquire jobs with "SELECT ... FOR UPDATE SKIP LOCKED" inside a
//     CTE so two workers can never lease the same job simultaneously.
//   - Leases expire (lease_until); a reclaim loop re-queues abandoned jobs
//     with backoff and bounded attempts.
//   - Results and observations are written in the same transaction as the
//     job status change, so a crash never loses a completed check.
package checks

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ReliaAstra/reliastra-backend/pkg/ids"
)

// Job statuses.
const (
	JobPending   = "pending"
	JobLeased    = "leased"
	JobRunning   = "running"
	JobSucceeded = "succeeded"
	JobFailed    = "failed"
	JobExpired   = "expired"
	JobCancelled = "cancelled"
)

// Job is a durable check job.
type Job struct {
	ID           string     `json:"id"`
	MonitorID    string     `json:"monitor_id"`
	RegionID     string     `json:"region_id"`
	ScheduledFor time.Time  `json:"scheduled_for"`
	Attempt      int        `json:"attempt"`
	Status       string     `json:"status"`
	LeaseUntil   *time.Time `json:"lease_until,omitempty"`
	WorkerID     string     `json:"worker_id,omitempty"`
	RetryAfter   *time.Time `json:"retry_after,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	StartedAt    *time.Time `json:"started_at,omitempty"`
	CompletedAt  *time.Time `json:"completed_at,omitempty"`
}

// JobStore persists check jobs.
type JobStore struct {
	pool *pgxpool.Pool
}

// NewJobStore builds a JobStore.
func NewJobStore(pool *pgxpool.Pool) *JobStore { return &JobStore{pool: pool} }

const jobCols = `id, monitor_id, region_id, scheduled_for, attempt, status, lease_until,
	worker_id, retry_after, created_at, started_at, completed_at`

func scanJob(row pgx.Row) (*Job, error) {
	var j Job
	err := row.Scan(&j.ID, &j.MonitorID, &j.RegionID, &j.ScheduledFor, &j.Attempt, &j.Status,
		&j.LeaseUntil, &j.WorkerID, &j.RetryAfter, &j.CreatedAt, &j.StartedAt, &j.CompletedAt)
	if err != nil {
		return nil, err
	}
	return &j, nil
}

// CreateJob inserts a job, ignoring duplicates (idempotent scheduling).
func (s *JobStore) CreateJob(ctx context.Context, j *Job) (bool, error) {
	tag, err := s.pool.Exec(ctx, `INSERT INTO check_jobs
		(id, monitor_id, region_id, scheduled_for, attempt, status)
		VALUES ($1,$2,$3,$4,$5,'pending')
		ON CONFLICT (monitor_id, region_id, scheduled_for) DO NOTHING`,
		j.ID, j.MonitorID, j.RegionID, j.ScheduledFor, j.Attempt)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// LeaseDue atomically leases up to batch due jobs for a worker.
// FOR UPDATE SKIP LOCKED guarantees each job is leased to exactly one worker.
func (s *JobStore) LeaseDue(ctx context.Context, workerID string, leaseDuration time.Duration, batch int) ([]Job, error) {
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT id FROM check_jobs
			WHERE status = 'pending' AND scheduled_for <= now()
			  AND (retry_after IS NULL OR retry_after <= now())
			ORDER BY scheduled_for
			LIMIT $1
			FOR UPDATE SKIP LOCKED
		)
		UPDATE check_jobs j
		SET status = 'leased',
		    lease_until = now() + $2,
		    worker_id = $3,
		    started_at = COALESCE(started_at, now())
		FROM candidates c WHERE j.id = c.id
		RETURNING j.`+jobCols,
		batch, leaseDuration, workerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Job
	for rows.Next() {
		j, err := scanJob(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *j)
	}
	return out, rows.Err()
}

// MarkRunning transitions a leased job to running (worker owns it).
func (s *JobStore) MarkRunning(ctx context.Context, jobID, workerID string, leaseUntil time.Time) error {
	_, err := s.pool.Exec(ctx, `UPDATE check_jobs SET status='running', worker_id=$2, lease_until=$3
		WHERE id=$1 AND status='leased'`, jobID, workerID, leaseUntil)
	return err
}

// Complete finalizes a job as succeeded or failed. Called inside the result
// transaction so a crash cannot lose the result.
func (s *JobStore) Complete(ctx context.Context, tx pgx.Tx, jobID, status string, completedAt time.Time) error {
	_, err := tx.Exec(ctx, `UPDATE check_jobs SET status=$2, completed_at=$3, lease_until=NULL
		WHERE id=$1`, jobID, status, completedAt)
	return err
}

// Requeue returns a job to pending with backoff for a retry.
func (s *JobStore) Requeue(ctx context.Context, jobID string, attempt int, retryAfter time.Time) error {
	_, err := s.pool.Exec(ctx, `UPDATE check_jobs SET status='pending', attempt=$2, retry_after=$3,
		lease_until=NULL, worker_id='' WHERE id=$1`, jobID, attempt, retryAfter)
	return err
}

// RequeueTx returns a job to pending inside the result transaction.
func (s *JobStore) RequeueTx(ctx context.Context, tx pgx.Tx, jobID string, attempt int, retryAfter time.Time) error {
	_, err := tx.Exec(ctx, `UPDATE check_jobs SET status='pending', attempt=$2, retry_after=$3,
		lease_until=NULL, worker_id='' WHERE id=$1`, jobID, attempt, retryAfter)
	return err
}

// CompleteNow finalizes a job without a result transaction (unrecoverable
// errors).
func (s *JobStore) CompleteNow(ctx context.Context, jobID, status string) error {
	_, err := s.pool.Exec(ctx, `UPDATE check_jobs SET status=$2, completed_at=now(), lease_until=NULL
		WHERE id=$1`, jobID, status)
	return err
}

// ExpireLeases reclaims jobs whose lease expired (worker died / crashed).
// Attempts are incremented; jobs past maxAttempts are marked expired.
// Returns the number of jobs re-queued and the number expired.
func (s *JobStore) ExpireLeases(ctx context.Context, now time.Time, maxAttempts int, backoff func(attempt int) time.Duration) (requeued, expired int, err error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, attempt FROM check_jobs
		WHERE status IN ('leased','running') AND lease_until < $1
		LIMIT 1000`, now)
	if err != nil {
		return 0, 0, err
	}
	type jobRef struct {
		id      string
		attempt int
	}
	var refs []jobRef
	for rows.Next() {
		var r jobRef
		if err := rows.Scan(&r.id, &r.attempt); err != nil {
			rows.Close()
			return 0, 0, err
		}
		refs = append(refs, r)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, 0, err
	}
	for _, r := range refs {
		if r.attempt+1 > maxAttempts {
			if _, err := s.pool.Exec(ctx, `UPDATE check_jobs SET status='expired', lease_until=NULL
				WHERE id=$1`, r.id); err != nil {
				return requeued, expired, err
			}
			expired++
			continue
		}
		retryAfter := time.Now().UTC().Add(backoff(r.attempt))
		if _, err := s.pool.Exec(ctx, `UPDATE check_jobs SET status='pending', attempt=$2,
			retry_after=$3, lease_until=NULL, worker_id='' WHERE id=$1`, r.id, r.attempt+1, retryAfter); err != nil {
			return requeued, expired, err
		}
		requeued++
	}
	return requeued, expired, nil
}

// ByID fetches a job.
func (s *JobStore) ByID(ctx context.Context, id string) (*Job, error) {
	return scanJob(s.pool.QueryRow(ctx, `SELECT `+jobCols+` FROM check_jobs WHERE id=$1`, id))
}

// ListForMonitor returns recent jobs for a monitor (API).
func (s *JobStore) ListForMonitor(ctx context.Context, monitorID string, limit int) ([]Job, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+jobCols+` FROM check_jobs WHERE monitor_id=$1
		ORDER BY scheduled_for DESC LIMIT $2`, monitorID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Job
	for rows.Next() {
		j, err := scanJob(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *j)
	}
	return out, rows.Err()
}

// CountsByStatus returns pending/running job counts (ops metric).
func (s *JobStore) CountsByStatus(ctx context.Context) (map[string]int64, error) {
	rows, err := s.pool.Query(ctx, `SELECT status, count(*) FROM check_jobs GROUP BY status`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]int64{}
	for rows.Next() {
		var st string
		var n int64
		if err := rows.Scan(&st, &n); err != nil {
			return nil, err
		}
		out[st] = n
	}
	return out, rows.Err()
}

// Marshal helpers
var _ = json.Marshal
var _ = ids.NewUUID
