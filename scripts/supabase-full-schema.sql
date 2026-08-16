-- =============================================================================
-- RELIASTRA — FULL APPLICATION SCHEMA
-- =============================================================================
-- Run this in the Supabase SQL Editor on a FRESH database.
-- Creates every table, index, and seed data the application requires.
-- Wrapped in a single transaction so it either all succeeds or rolls back.
-- =============================================================================
-- NOTE: This script is idempotent where safe (indexes use IF NOT EXISTS).
--       Tables use CREATE TABLE IF NOT EXISTS. Seed data uses INSERT ... ON CONFLICT DO NOTHING.
--       Safe to re-run on a partially-migrated database.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. USERS & AUTH
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    google_id VARCHAR(255) UNIQUE,
    github_id VARCHAR(255) UNIQUE,
    avatar_url VARCHAR(500),
    auth_provider VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id ON users (google_id) WHERE google_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_github_id ON users (github_id) WHERE github_id IS NOT NULL;

-- =============================================================================
-- 2. ORGANIZATIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150) NOT NULL,
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    has_agency_mode BOOLEAN NOT NULL DEFAULT FALSE,
    is_founding_customer BOOLEAN NOT NULL DEFAULT FALSE,
    founding_discount_pct INTEGER NOT NULL DEFAULT 0,
    stripe_customer_id VARCHAR(100),
    stripe_subscription_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_slug ON organizations (slug);

-- =============================================================================
-- 3. ORGANIZATION MEMBERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_organization_members_org_id ON organization_members (org_id);
CREATE INDEX IF NOT EXISTS ix_organization_members_user_id ON organization_members (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_organization_members_org_id_user_id ON organization_members (org_id, user_id);

-- =============================================================================
-- 4. DEPENDENCIES
-- =============================================================================

CREATE TABLE IF NOT EXISTS dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    application_id UUID,
    name VARCHAR(150) NOT NULL,
    endpoint_url VARCHAR(500) NOT NULL,
    method VARCHAR(10) NOT NULL DEFAULT 'GET',
    headers JSONB,
    expected_status_codes JSONB NOT NULL DEFAULT '[200]',
    timeout_seconds INTEGER NOT NULL DEFAULT 10,
    check_interval_seconds INTEGER NOT NULL DEFAULT 300,
    next_check_at TIMESTAMPTZ,
    regions JSONB NOT NULL DEFAULT '["us-east", "eu-west"]',
    alert_threshold_ms INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_dependencies_org_id ON dependencies (org_id);
CREATE INDEX IF NOT EXISTS ix_dependencies_next_check_at ON dependencies (next_check_at);
CREATE INDEX IF NOT EXISTS ix_dependencies_application_id ON dependencies (application_id);

-- =============================================================================
-- 5. CHECK RESULTS (partitioned)
-- =============================================================================

CREATE TABLE IF NOT EXISTS check_results (
    id UUID NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    dependency_id UUID NOT NULL,
    org_id UUID NOT NULL,
    region VARCHAR(50) NOT NULL,
    latency_ms FLOAT NOT NULL,
    status_code INTEGER,
    is_up BOOLEAN NOT NULL,
    error_message VARCHAR(500),
    quorum_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT pk_check_results PRIMARY KEY (id, executed_at)
) PARTITION BY RANGE (executed_at);

-- Default partition catches all writes without requiring monthly partition creation
CREATE TABLE IF NOT EXISTS check_results_default PARTITION OF check_results DEFAULT;

CREATE INDEX IF NOT EXISTS ix_check_results_dependency_id ON check_results (dependency_id);
CREATE INDEX IF NOT EXISTS ix_check_results_org_id ON check_results (org_id);
CREATE INDEX IF NOT EXISTS ix_check_results_executed_at ON check_results (executed_at);

-- =============================================================================
-- 6. INCIDENTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dependency_id UUID NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    severity VARCHAR(30) NOT NULL DEFAULT 'major',
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    root_cause VARCHAR(50) NOT NULL DEFAULT 'unknown',
    description VARCHAR(1000),
    evidence_report_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_incidents_org_id ON incidents (org_id);
CREATE INDEX IF NOT EXISTS ix_incidents_dependency_id ON incidents (dependency_id);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents (status);
CREATE INDEX IF NOT EXISTS ix_incidents_started_at ON incidents (started_at);

-- =============================================================================
-- 7. INCIDENT CORRELATIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS incident_correlations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    correlated_dependency_id UUID NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    correlation_confidence FLOAT NOT NULL DEFAULT 0.85,
    time_window_seconds INTEGER NOT NULL DEFAULT 300,
    correlation_method VARCHAR(50) NOT NULL DEFAULT 'temporal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_incident_correlations_incident_id ON incident_correlations (incident_id);
CREATE INDEX IF NOT EXISTS ix_incident_correlations_correlated_dep_id ON incident_correlations (correlated_dependency_id);

-- =============================================================================
-- 8. EVIDENCE REPORTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS evidence_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    checksum VARCHAR(100) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_evidence_reports_org_id ON evidence_reports (org_id);
CREATE INDEX IF NOT EXISTS ix_evidence_reports_incident_id ON evidence_reports (incident_id);
CREATE INDEX IF NOT EXISTS ix_evidence_reports_checksum ON evidence_reports (checksum);

-- =============================================================================
-- 9. VENDOR TRACKINGS
-- =============================================================================

CREATE TABLE IF NOT EXISTS vendor_trackings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    endpoint_url VARCHAR(500) NOT NULL,
    category VARCHAR(100) NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    last_check_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_vendor_trackings_vendor_name ON vendor_trackings (vendor_name);

-- Seed 5 public vendors
INSERT INTO vendor_trackings (id, vendor_name, display_name, endpoint_url, category, is_public, created_at, updated_at)
VALUES
    ('11111111-0001-0001-0001-000000000001', 'stripe',    'Stripe',    'https://status.stripe.com',            'payments',       TRUE, NOW(), NOW()),
    ('11111111-0001-0001-0001-000000000002', 'auth0',     'Auth0',     'https://status.auth0.com',             'auth',           TRUE, NOW(), NOW()),
    ('11111111-0001-0001-0001-000000000003', 'cloudflare','Cloudflare', 'https://www.cloudflarestatus.com',     'cdn',            TRUE, NOW(), NOW()),
    ('11111111-0001-0001-0001-000000000004', 'openai',    'OpenAI',    'https://status.openai.com',            'ai',             TRUE, NOW(), NOW()),
    ('11111111-0001-0001-0001-000000000005', 'twilio',    'Twilio',    'https://status.twilio.com',            'communications', TRUE, NOW(), NOW())
ON CONFLICT (vendor_name) DO NOTHING;

-- =============================================================================
-- 10. VENDOR ENDPOINTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS vendor_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendor_trackings(id) ON DELETE CASCADE,
    endpoint_url VARCHAR(500) NOT NULL,
    check_interval_seconds INTEGER NOT NULL DEFAULT 300,
    regions JSONB NOT NULL DEFAULT '["us-east", "eu-west"]',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    health_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
    last_check_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vendor_endpoints_vendor_url UNIQUE (vendor_id, endpoint_url)
);

CREATE INDEX IF NOT EXISTS ix_vendor_endpoints_vendor_id ON vendor_endpoints (vendor_id);

-- Seed vendor endpoints (one per seed vendor)
INSERT INTO vendor_endpoints (id, vendor_id, endpoint_url, check_interval_seconds, regions, is_active, health_status, created_at, updated_at)
SELECT
    gen_random_uuid(),
    vt.id,
    vt.endpoint_url,
    300,
    '["us-east", "eu-west"]'::JSONB,
    TRUE,
    'unknown',
    NOW(),
    NOW()
FROM vendor_trackings vt
WHERE NOT EXISTS (
    SELECT 1 FROM vendor_endpoints ve WHERE ve.vendor_id = vt.id
);

-- =============================================================================
-- 11. ALERT CONFIGS (notifications)
-- =============================================================================

CREATE TABLE IF NOT EXISTS alert_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_alert_configs_org_id ON alert_configs (org_id);

-- =============================================================================
-- 12. API KEYS
-- =============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    prefix VARCHAR(20) NOT NULL,
    hashed_key VARCHAR(100) NOT NULL,
    scopes JSONB NOT NULL DEFAULT '[]',
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_api_keys_org_id ON api_keys (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_hashed_key ON api_keys (hashed_key);

-- =============================================================================
-- 13. REFRESH TOKENS
-- =============================================================================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(100) NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);

-- =============================================================================
-- 14. AUDIT LOGS
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID,
    user_id UUID,
    event_type VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_org_id ON audit_logs (org_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs (event_type);

-- =============================================================================
-- 15. SUBSCRIPTIONS (Paystack billing)
-- =============================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL DEFAULT 'paystack',
    provider_customer_id VARCHAR(200),
    provider_subscription_id VARCHAR(200),
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    status VARCHAR(30) NOT NULL DEFAULT 'inactive',
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscriptions_organization_id UNIQUE (organization_id)
);

CREATE INDEX IF NOT EXISTS ix_subscriptions_organization_id ON subscriptions (organization_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_provider_customer_id ON subscriptions (provider_customer_id);

-- =============================================================================
-- 16. OBSERVATIONS (partitioned)
-- =============================================================================

CREATE TABLE IF NOT EXISTS observations (
    id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_id UUID,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    region VARCHAR(50) NOT NULL,
    endpoint_url VARCHAR(500) NOT NULL,
    latency_ms FLOAT NOT NULL,
    status_code INTEGER,
    response_time_ms FLOAT,
    tls_version VARCHAR(20),
    tls_certificate_issuer VARCHAR(200),
    tls_certificate_expiry TIMESTAMPTZ,
    error_type VARCHAR(50),
    error_message VARCHAR(500),
    metadata JSONB,
    CONSTRAINT pk_observations PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Default partition catches all writes
CREATE TABLE IF NOT EXISTS observations_default PARTITION OF observations DEFAULT;

-- Base indexes from migration 0003
CREATE INDEX IF NOT EXISTS ix_observations_timestamp ON observations (timestamp);
CREATE INDEX IF NOT EXISTS ix_observations_source_type ON observations (source_type);
CREATE INDEX IF NOT EXISTS ix_observations_source_id ON observations (source_id);
CREATE INDEX IF NOT EXISTS ix_observations_org_id ON observations (org_id);
CREATE INDEX IF NOT EXISTS ix_observations_source_timestamp ON observations (source_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_observations_org_timestamp ON observations (org_id, timestamp);

-- =============================================================================
-- 17. EMAIL VERIFICATION TOKENS
-- =============================================================================

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_user_id ON email_verification_tokens (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_email_verification_tokens_hash ON email_verification_tokens (token_hash);

-- =============================================================================
-- 18. PASSWORD RESET TOKENS
-- =============================================================================

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_password_reset_tokens_hash ON password_reset_tokens (token_hash);

-- =============================================================================
-- 19. ATTRIBUTION RESULTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS attribution_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    suspected_dependency_id UUID NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    classification VARCHAR(50) NOT NULL DEFAULT 'unknown',
    confidence_score FLOAT NOT NULL DEFAULT 0,
    signal_breakdown JSONB NOT NULL DEFAULT '{}',
    supporting_evidence JSONB NOT NULL DEFAULT '{}',
    contradicting_evidence JSONB NOT NULL DEFAULT '{}',
    methodology_version VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_attribution_results_incident_id UNIQUE (incident_id)
);

CREATE INDEX IF NOT EXISTS ix_attribution_results_incident_id ON attribution_results (incident_id);
CREATE INDEX IF NOT EXISTS ix_attribution_results_org_id ON attribution_results (org_id);
CREATE INDEX IF NOT EXISTS ix_attribution_results_suspected_dep_id ON attribution_results (suspected_dependency_id);

-- =============================================================================
-- 20. EVIDENCE SNAPSHOTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS evidence_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dependency_id UUID NOT NULL REFERENCES dependencies(id) ON DELETE CASCADE,
    time_window_start TIMESTAMPTZ NOT NULL,
    time_window_end TIMESTAMPTZ NOT NULL,
    observation_ids JSONB NOT NULL DEFAULT '[]',
    attribution_result JSONB,
    methodology_version VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    data_hash VARCHAR(64) NOT NULL,
    verification_id VARCHAR(32) NOT NULL,
    report_file_path VARCHAR(500),
    report_checksum VARCHAR(64),
    json_evidence_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_evidence_snapshots_verification_id UNIQUE (verification_id)
);

CREATE INDEX IF NOT EXISTS ix_evidence_snapshots_incident_id ON evidence_snapshots (incident_id);
CREATE INDEX IF NOT EXISTS ix_evidence_snapshots_org_id ON evidence_snapshots (org_id);
CREATE INDEX IF NOT EXISTS ix_evidence_snapshots_dependency_id ON evidence_snapshots (dependency_id);
CREATE INDEX IF NOT EXISTS ix_evidence_snapshots_data_hash ON evidence_snapshots (data_hash);
CREATE INDEX IF NOT EXISTS ix_evidence_snapshots_verification_id ON evidence_snapshots (verification_id);

-- =============================================================================
-- 21. CLIENTS (agency hierarchy)
-- =============================================================================

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_clients_org_id ON clients (org_id);

-- =============================================================================
-- 22. APPLICATIONS (agency hierarchy)
-- =============================================================================

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_applications_org_id ON applications (org_id);
CREATE INDEX IF NOT EXISTS ix_applications_client_id ON applications (client_id);

-- Add FK for dependencies.application_id (already added the column above)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_dependencies_application_id_applications'
    ) THEN
        ALTER TABLE dependencies
            ADD CONSTRAINT fk_dependencies_application_id_applications
            FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE SET NULL;
    END IF;
END $$;

-- =============================================================================
-- 23. AI PROVIDERS
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) NOT NULL,
    endpoint_url VARCHAR(500) NOT NULL,
    encrypted_api_key TEXT,
    model_name VARCHAR(100) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    max_tokens INTEGER NOT NULL DEFAULT 4096,
    temperature FLOAT NOT NULL DEFAULT 0.3,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_providers_organization_id ON ai_providers (organization_id);

-- At most one default provider per organization
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_providers_default_per_org
    ON ai_providers (organization_id)
    WHERE is_default = TRUE;

-- =============================================================================
-- 24. TIMELINE INDEXES (vendor time-series performance)
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_obs_endpoint_ts
    ON observations (endpoint_url, timestamp);

CREATE INDEX IF NOT EXISTS ix_obs_source_endpoint_ts
    ON observations (source_type, endpoint_url, timestamp);

CREATE INDEX IF NOT EXISTS ix_obs_endpoint_region_ts
    ON observations (endpoint_url, region, timestamp);

COMMIT;

-- =============================================================================
-- DONE — 24 tables, all indexes, all seed data, all foreign keys.
-- =============================================================================
-- Tables created (in dependency order):
--   1.  users
--   2.  organizations
--   3.  organization_members
--   4.  dependencies
--   5.  check_results (partitioned + default partition)
--   6.  incidents
--   7.  incident_correlations
--   8.  evidence_reports
--   9.  vendor_trackings (5 seed vendors)
--   10. vendor_endpoints (auto-seeded from vendors)
--   11. alert_configs
--   12. api_keys
--   13. refresh_tokens
--   14. audit_logs
--   15. subscriptions
--   16. observations (partitioned + default partition)
--   17. email_verification_tokens
--   18. password_reset_tokens
--   19. attribution_results
--   20. evidence_snapshots
--   21. clients
--   22. applications
--   23. ai_providers
--   24. +3 timeline composite indexes on observations
-- =============================================================================
