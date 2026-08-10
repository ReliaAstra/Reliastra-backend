-- 0005_incidents: incidents, state transitions, correlation results.
-- Incident numbers like INC-2026-000184 are allocated from per-year
-- sequences (incident_sequences) so they are human-readable and stable.

CREATE TABLE IF NOT EXISTS incident_sequences (
    year        int PRIMARY KEY,
    last_value  bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS incidents (
    id              uuid PRIMARY KEY,
    number          text NOT NULL,
    project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    service_id      uuid REFERENCES services(id) ON DELETE SET NULL,
    dependency_id   uuid REFERENCES dependencies(id) ON DELETE SET NULL,
    status          text NOT NULL DEFAULT 'candidate'
                   CHECK (status IN ('candidate', 'investigating', 'confirmed', 'resolved', 'false_positive')),
    severity        text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    started_at      timestamptz NOT NULL,
    detected_at     timestamptz,
    resolved_at     timestamptz,
    title           text NOT NULL,
    summary         text NOT NULL DEFAULT '',
    -- Attribution produced by the correlation engine (deterministic v1).
    attributed_dependency_id uuid REFERENCES dependencies(id) ON DELETE SET NULL,
    confidence      text NOT NULL DEFAULT 'none' CHECK (confidence IN ('none', 'low', 'medium', 'high')),
    evidence_score  double precision NOT NULL DEFAULT 0,
    correlation_version text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incidents_org_idx ON incidents (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_project_idx ON incidents (project_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS incidents_number_key ON incidents (number);
-- One open incident per target at a time.
CREATE UNIQUE INDEX IF NOT EXISTS incidents_open_target_idx
    ON incidents (service_id, dependency_id)
    WHERE status IN ('candidate', 'investigating', 'confirmed');

-- Append-only state transition history. This is the audit trail of the
-- incident state machine.
CREATE TABLE IF NOT EXISTS incident_events (
    id          uuid PRIMARY KEY,
    incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    from_status text NOT NULL,
    to_status   text NOT NULL,
    reason      text NOT NULL DEFAULT '',
    actor_type  text NOT NULL DEFAULT 'system' CHECK (actor_type IN ('system', 'user')),
    actor_id    text NOT NULL DEFAULT '',
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incident_events_incident_idx ON incident_events (incident_id, created_at);

-- Deterministic correlation results, one row per (incident, dependency).
-- The algorithm version and scoring configuration version are recorded so
-- any historical conclusion can be reproduced.
CREATE TABLE IF NOT EXISTS incident_correlations (
    id                     uuid PRIMARY KEY,
    incident_id            uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    dependency_id          uuid NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    correlation_version    text NOT NULL,
    scoring_config_version text NOT NULL,
    evidence_score         double precision NOT NULL DEFAULT 0,
    confidence             text NOT NULL DEFAULT 'low' CHECK (confidence IN ('low', 'medium', 'high')),
    temporal_overlap       double precision NOT NULL DEFAULT 0,
    regional_overlap       double precision NOT NULL DEFAULT 0,
    latency_similarity     double precision NOT NULL DEFAULT 0,
    error_similarity       double precision NOT NULL DEFAULT 0,
    failure_overlap        double precision NOT NULL DEFAULT 0,
    criticality_weight     double precision NOT NULL DEFAULT 1,
    service_failure_rate   double precision NOT NULL DEFAULT 0,
    dependency_failure_rate double precision NOT NULL DEFAULT 0,
    explanations           jsonb NOT NULL DEFAULT '[]',
    window_start           timestamptz NOT NULL,
    window_end             timestamptz NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (incident_id, dependency_id)
);
CREATE INDEX IF NOT EXISTS incident_correlations_incident_idx ON incident_correlations (incident_id);
