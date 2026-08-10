-- 0002_domain: projects, services, dependencies and their relationships.
-- Every tenant-owned entity carries organization_id directly (or through a
-- validated relationship) so every query can enforce tenant boundaries.

CREATE TABLE IF NOT EXISTS projects (
    id              uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    slug            text NOT NULL,
    description     text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug)
);
CREATE INDEX IF NOT EXISTS projects_org_idx ON projects (organization_id);

CREATE TABLE IF NOT EXISTS services (
    id              uuid PRIMARY KEY,
    project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            text NOT NULL,
    identifier      text NOT NULL,
    base_url        text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, identifier)
);
CREATE INDEX IF NOT EXISTS services_project_idx ON services (project_id);

-- External dependency catalog entries owned by a project (vendors may also
-- exist in the global catalog; this is the customer's view of a dependency).
CREATE TABLE IF NOT EXISTS dependencies (
    id          uuid PRIMARY KEY,
    project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        text NOT NULL,
    provider    text NOT NULL DEFAULT '',
    type        text NOT NULL DEFAULT 'api'
               CHECK (type IN ('api', 'cloud', 'cdn', 'auth', 'payment', 'email', 'ai', 'database', 'dns', 'other')),
    identifier  text NOT NULL DEFAULT '',
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS dependencies_project_idx ON dependencies (project_id);

-- Critical relationship between a customer service and an external
-- dependency. Drives correlation weighting.
CREATE TABLE IF NOT EXISTS service_dependencies (
    id            uuid PRIMARY KEY,
    service_id    uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    dependency_id uuid NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    criticality   text NOT NULL DEFAULT 'medium'
                 CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
    description   text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (service_id, dependency_id)
);
CREATE INDEX IF NOT EXISTS service_dependencies_dep_idx ON service_dependencies (dependency_id);
