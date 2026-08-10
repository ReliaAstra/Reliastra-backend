-- 0012_workers: worker fleet registry for observability.
-- Workers heartbeat here; the operations dashboard and alerting use it.
-- It is informational only — correctness never depends on it.

CREATE TABLE IF NOT EXISTS workers (
    id          text PRIMARY KEY,
    region_id   uuid REFERENCES regions(id) ON DELETE SET NULL,
    version     text NOT NULL DEFAULT '',
    capacity    int NOT NULL DEFAULT 1,
    status      text NOT NULL DEFAULT 'starting'
               CHECK (status IN ('starting', 'running', 'draining', 'stopped')),
    started_at  timestamptz NOT NULL DEFAULT now(),
    heartbeat_at timestamptz NOT NULL DEFAULT now(),
    stopped_at  timestamptz
);
CREATE INDEX IF NOT EXISTS workers_heartbeat_idx ON workers (heartbeat_at);
