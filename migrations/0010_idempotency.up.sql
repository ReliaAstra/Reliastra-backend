-- 0010_idempotency: client-supplied idempotency keys.
-- Guarantees safe retries of externally-triggered mutations
-- (evidence generation, monitor creation, webhook ingestion).

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id            uuid PRIMARY KEY,
    key           text NOT NULL,
    scope         text NOT NULL,      -- e.g. organization id or incident id
    resource_type text NOT NULL DEFAULT '',
    resource_id   text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    UNIQUE (key, scope)
);
CREATE INDEX IF NOT EXISTS idempotency_keys_scope_idx ON idempotency_keys (scope, created_at);
