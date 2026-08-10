# Job execution architecture

## 1. Model

Every check execution is a durable `check_jobs` row:

```
id, monitor_id, region_id, scheduled_for, attempt, status,
lease_until, worker_id, retry_after, created_at, started_at, completed_at
```

Statuses: `pending → leased → running → succeeded | failed | expired |
cancelled`. Jobs are idempotent by construction:
`UNIQUE (monitor_id, region_id, scheduled_for)` means the same scheduled
check can only ever exist once, even if two schedulers race.

## 2. Scheduler

The scheduler is a poll loop over `monitors.next_run_at`:

1. **Reclaim expired leases.** Jobs in `leased`/`running` whose
   `lease_until < now()` are returned to `pending` (attempt+1, backoff) or
   marked `expired` past `max_attempts`.
2. **Find due monitors.** `enabled AND status='active' AND next_run_at <=
   now()+lookahead`, oldest first, bounded batch.
3. **Missed-run handling.** If `next_run_at` is older than
   `missed_job_window` (e.g. the monitor was disabled for a day), the backlog
   is dropped: `next_run_at` is pinned to `now` instead of creating a burst.
4. **Create jobs.** One job per assigned region, scheduled at
   `next_run_at + jitter(±jitter_max_pct)` to spread simultaneous due
   monitors and avoid thundering herds.
5. **Advance.** `UPDATE monitors SET next_run_at = next_run_at + interval
   WHERE id = $1 AND next_run_at = $old` — conditional, so concurrent
   schedulers cannot double-advance.

Scheduling never uses goroutine-per-monitor; the loop is bounded and
batch-oriented.

## 3. Leasing (the concurrency model)

Workers lease jobs with:

```sql
WITH candidates AS (
    SELECT id FROM check_jobs
    WHERE status = 'pending' AND scheduled_for <= now()
      AND (retry_after IS NULL OR retry_after <= now())
    ORDER BY scheduled_for
    LIMIT $batch
    FOR UPDATE SKIP LOCKED
)
UPDATE check_jobs j SET status = 'leased', lease_until = now() + $lease,
       worker_id = $worker
FROM candidates c WHERE j.id = c.id
RETURNING j.*;
```

- `FOR UPDATE SKIP LOCKED` guarantees **exactly one worker** ever leases a
  given job: concurrent leases skip rows already locked by another
  transaction.
- A worker marks the job `running` and holds it for `lease_until`. If the
  worker dies (crash, kill, partition), the scheduler's reclaim loop returns
  the job to `pending` after the lease expires. **Two workers can never
  permanently own the same job.**
- On graceful shutdown a worker releases its *unstarted* leases immediately
  (`leased → pending`), so they are retried promptly; in-flight jobs drain up
  to `graceful_shutdown` timeout and then rely on lease expiry.

## 4. Worker behavior

- Bounded concurrency: a semaphore of `worker_concurrency`.
- **Per-organization fairness**: a per-org semaphore
  (`org_fairness_max_concurrent`) bounds concurrent checks per tenant so one
  abusive customer cannot consume the worker pool.
- Every check has an explicit execution timeout (`timeout_seconds`), bounded
  response size, bounded redirects, and an SSRF-safe dialer.
- The poll context never cancels a running check: leasing uses a short
  timeout; execution uses the worker lifetime context + per-check timeout.

## 5. Result + observation transaction

A completed check writes, in **one transaction**:

1. `check_results` row (bounded metadata, normalized failure taxonomy)
2. `observations` row (normalized observation: target, region, availability,
   latency, status, failure_class) — or `public_observations` for public
   monitors, on the same tx
3. job status: `succeeded` / `failed` / `pending` (retry with `retry_after`)
4. `outbox_events` row: `check.completed` (drives detection)

Commit is the durability point. A crash before commit = check never
happened (job lease expires and it is retried); after commit = everything is
durable.

## 6. Retries

Retries are classified by failure class (see `internal/failure`):

| Class | Retry? |
|---|---|
| `dns_failure`, `connection_timeout`, `connection_refused`, `http_5xx`, `network_error`, `tls_failure` | Yes (transient infrastructure) |
| `http_4xx`, `assertion_failed`, `latency_exceeded`, `ssrf_blocked`, `invalid_response` | No (deterministic; fail fast) |

Backoff is exponential with ±20% jitter, capped at `max_backoff`; the retry
policy is configuration-injected (no magic numbers in code). A job past
`max_attempts` is marked `failed` with its final result preserved. Retried
jobs accumulate one `check_results` row per attempt (unique
`(job_id, attempt)`); the latest attempt is authoritative.

## 7. Failure scenarios answered

- **What if the process crashes immediately after this operation?**
  The result transaction is atomic; either the result+observation+outbox
  exist or the job is retried.
- **What if two workers execute it?** Impossible by construction: leases are
  transactional. A duplicated *delivery* is prevented by the
  `UNIQUE (event_id, channel_id)` on `notification_deliveries`; duplicated
  incidents by the `NULLS NOT DISTINCT` partial unique index.
- **What if the scheduler restarts mid-tick?** Job creation is idempotent;
  the next tick resumes.
