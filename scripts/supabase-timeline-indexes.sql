-- =============================================================================
-- RELIASTRA: Vendor Timeline Endpoint — Supabase SQL
-- =============================================================================
-- Run this in the Supabase SQL Editor.
-- Creates composite indexes on the partitioned observations table
-- required by GET /v1/public/vendors/{vendor_name}/timeline
-- =============================================================================

BEGIN;

-- 1. Composite index: (endpoint_url, timestamp)
--    Primary lookup pattern for per-vendor time-range queries.
--    Covers both the timeline bucket aggregation and the latest-observation query.
CREATE INDEX IF NOT EXISTS ix_obs_endpoint_ts
    ON observations (endpoint_url, timestamp);

-- 2. Composite index: (source_type, endpoint_url, timestamp)
--    The timeline query always filters source_type = 'customer_check' + endpoint URLs
--    + time range. This fully covers the WHERE clause for optimal index-only scan.
CREATE INDEX IF NOT EXISTS ix_obs_source_endpoint_ts
    ON observations (source_type, endpoint_url, timestamp);

-- 3. Composite index: (endpoint_url, region, timestamp)
--    Future-proofing for multi-region support. Currently the timeline
--    defaults to region='us-east-1' but the schema allows per-region filtering.
CREATE INDEX IF NOT EXISTS ix_obs_endpoint_region_ts
    ON observations (endpoint_url, region, timestamp);

COMMIT;
