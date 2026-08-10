-- 0003_monitoring: regions, monitors, encrypted monitor secrets.

CREATE TABLE IF NOT EXISTS regions (
    id           uuid PRIMARY KEY,
    name         text NOT NULL,
    slug         text NOT NULL,
    country      text NOT NULL DEFAULT '',
    provider     text NOT NULL DEFAULT '',
    status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'retired')),
    capabilities jsonb NOT NULL DEFAULT '[]',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slug)
);

-- A monitor defines WHAT to observe. service_id/dependency_id are mutually
-- exclusive and at least one is required for customer monitors. Public
-- monitors (visibility = 'public') track the global vendor catalog and carry
-- no tenant relationship (project_id NULL).
CREATE TABLE IF NOT EXISTS monitors (
    id               uuid PRIMARY KEY,
    project_id       uuid REFERENCES projects(id) ON DELETE CASCADE,
    organization_id  uuid REFERENCES organizations(id) ON DELETE CASCADE,
    service_id       uuid REFERENCES services(id) ON DELETE CASCADE,
    dependency_id    uuid REFERENCES dependencies(id) ON DELETE CASCADE,
    vendor_id        uuid,
    name             text NOT NULL,
    type             text NOT NULL DEFAULT 'http' CHECK (type IN ('http', 'dns', 'tcp', 'browser', 'webhook', 'semantic')),
    target           text NOT NULL,
    configuration    jsonb NOT NULL DEFAULT '{}',
    interval_seconds int NOT NULL DEFAULT 60 CHECK (interval_seconds >= 10),
    timeout_seconds  int NOT NULL DEFAULT 10 CHECK (timeout_seconds BETWEEN 1 AND 120),
    max_attempts     int NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    enabled          boolean NOT NULL DEFAULT true,
    visibility       text NOT NULL DEFAULT 'customer' CHECK (visibility IN ('customer', 'public')),
    status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (visibility = 'public' OR (service_id IS NOT NULL OR dependency_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS monitors_org_idx ON monitors (organization_id);
CREATE INDEX IF NOT EXISTS monitors_project_idx ON monitors (project_id);
CREATE INDEX IF NOT EXISTS monitors_enabled_idx ON monitors (enabled, interval_seconds);

-- Secrets embedded in monitor configuration (authorization headers, request
-- bodies marked sensitive) are envelope-encrypted with AES-256-GCM. The
-- plaintext never touches PostgreSQL or logs.
CREATE TABLE IF NOT EXISTS monitor_secrets (
    monitor_id   uuid PRIMARY KEY REFERENCES monitors(id) ON DELETE CASCADE,
    ciphertext   bytea NOT NULL,
    key_version  int NOT NULL,
    nonce        bytea NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
