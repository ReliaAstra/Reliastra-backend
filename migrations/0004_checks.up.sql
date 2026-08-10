-- 0004_checks: durable check jobs, normalized results, observations.
-- check_results and observations are high-volume tables; they are designed
-- for future time-based partitioning (see docs/architecture/database.md).
-- The migration path is documented there; Phase 1 keeps them as plain tables.

CREATE TABLE IF NOT EXISTS check_jobs (
    id            uuid PRIMARY KEY,
    monitor_id    uuid NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    region_id     uuid NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    scheduled_for timestamptz NOT NULL,
    attempt       int NOT NULL DEFAULT 1,
    status        text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'leased', 'running', 'succeeded', 'failed', 'expired', 'cancelled')),
    lease_until   timestamptz,
    worker_id     text NOT NULL DEFAULT '',
    retry_after   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    completed_at  timestamptz,
    UNIQUE (monitor_id, region_id, scheduled_for)
);
CREATE INDEX IF NOT EXISTS check_jobs_due_idx ON check_jobs (status, scheduled_for) WHERE status IN ('pending', 'leased', 'running');
CREATE INDEX IF NOT EXISTS check_jobs_monitor_idx ON check_jobs (monitor_id, scheduled_for DESC);

CREATE TABLE IF NOT EXISTS check_results (
    id               uuid PRIMARY KEY,
    job_id           uuid NOT NULL REFERENCES check_jobs(id),
    attempt          int NOT NULL DEFAULT 1,
    monitor_id       uuid NOT NULL REFERENCES monitors(id),
    region_id        uuid NOT NULL REFERENCES regions(id),
    started_at       timestamptz NOT NULL,
    completed_at     timestamptz NOT NULL,
    success          boolean NOT NULL,
    status_code      int,
    latency_ms       int NOT NULL DEFAULT 0,
    dns_ms           int NOT NULL DEFAULT 0,
    connect_ms       int NOT NULL DEFAULT 0,
    tls_ms           int NOT NULL DEFAULT 0,
    ttfb_ms          int NOT NULL DEFAULT 0,
    error_class      text NOT NULL DEFAULT '',
    error_code       text NOT NULL DEFAULT '',
    error_message    text NOT NULL DEFAULT '',
    response_size    bigint NOT NULL DEFAULT 0,
    assertions_passed int NOT NULL DEFAULT 0,
    assertions_failed int NOT NULL DEFAULT 0,
    metadata         jsonb NOT NULL DEFAULT '{}',
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS check_results_monitor_idx ON check_results (monitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS check_results_job_idx ON check_results (job_id);
-- One result row per attempt; retried jobs accumulate result rows.
CREATE UNIQUE INDEX IF NOT EXISTS check_results_job_attempt_key ON check_results (job_id, attempt);

-- Normalized observations: the abstraction correlation and the incident
-- engine operate on. One row per completed check, written in the same
-- transaction as check_results.
CREATE TABLE IF NOT EXISTS observations (
    id            uuid PRIMARY KEY,
    target_type   text NOT NULL CHECK (target_type IN ('service', 'dependency', 'public')),
    target_id     uuid NOT NULL,
    monitor_id    uuid NOT NULL,
    region_id     uuid NOT NULL,
    organization_id uuid,
    observed_at   timestamptz NOT NULL,
    availability  boolean NOT NULL,
    latency_ms    int NOT NULL DEFAULT 0,
    status        text NOT NULL CHECK (status IN ('ok', 'degraded', 'down')),
    failure_class text NOT NULL DEFAULT '',
    metadata      jsonb NOT NULL DEFAULT '{}',
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS observations_target_idx ON observations (target_type, target_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS observations_org_idx ON observations (organization_id, observed_at DESC);
