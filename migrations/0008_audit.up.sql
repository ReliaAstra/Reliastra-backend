-- 0008_audit: append-only audit log. No UPDATE/DELETE paths exist in the API.

CREATE TABLE IF NOT EXISTS audit_logs (
    id              uuid PRIMARY KEY,
    organization_id uuid,
    actor_id        text NOT NULL DEFAULT '',
    actor_type      text NOT NULL DEFAULT 'user' CHECK (actor_type IN ('user', 'api_key', 'system')),
    action          text NOT NULL,
    resource_type   text NOT NULL DEFAULT '',
    resource_id     text NOT NULL DEFAULT '',
    metadata        jsonb NOT NULL DEFAULT '{}',
    ip_address      text NOT NULL DEFAULT '',
    user_agent      text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_logs_org_idx ON audit_logs (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_logs_action_idx ON audit_logs (action, created_at DESC);
