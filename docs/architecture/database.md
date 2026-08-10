# Database design

## Source of truth

PostgreSQL is the source of truth for all durable application state. Redis is
auxiliary (rate limiting, coordination); object storage holds blobs
(evidence artifacts) whose metadata + hashes live in PostgreSQL.

## Schema overview (12 migrations)

| Migration | Tables |
|---|---|
| 0001 tenancy | users, organizations, organization_members, sessions (token hash only), api_keys (hash only) |
| 0002 domain | projects, services, dependencies, service_dependencies |
| 0003 monitoring | regions, monitors, monitor_secrets (envelope-encrypted) |
| 0004 checks | check_jobs, check_results, observations |
| 0005 incidents | incidents, incident_events, incident_correlations, incident_sequences |
| 0006 evidence | evidence_records |
| 0007 notifications | outbox_events, notification_channels (encrypted), notification_deliveries |
| 0008 audit | audit_logs (append-only) |
| 0009 public | vendors, public_observations |
| 0010 idempotency | idempotency_keys |
| 0011 scheduling | monitor_regions, monitors.next_run_at |
| 0012 workers | workers (heartbeats; informational) |
| 0013 constraints | correlation confidence 'none'; NULLS NOT DISTINCT open-incident index |

## Key constraints worth knowing

- Every tenant-owned entity carries `organization_id` directly or via a
  validated join through `projects`. All queries enforce the tenant boundary.
- `check_jobs` unique `(monitor_id, region_id, scheduled_for)` → idempotent
  scheduling.
- `check_results` unique `(job_id, attempt)` → one result per attempt.
- Partial unique index on open incidents with `NULLS NOT DISTINCT` → one
  open incident per (service, dependency) including NULL-matched targets.
- `notification_deliveries` unique `(event_id, channel_id)` → idempotent
  fan-out.
- `outbox_events` statuses: pending/processing/processed/dead, with
  `available_after` for backoff.
- `sessions.token_hash`, `api_keys.key_hash` are SHA-256; plaintext tokens
  are shown once and never stored.

## Indexes

Indexes target the hot query patterns:

- `monitors (enabled, status, next_run_at)` — the scheduler's due scan
- `check_jobs (status, scheduled_for) WHERE status IN (pending, leased,
  running)` — lease pickup
- `check_results (monitor_id, created_at DESC)` — monitor history API
- `observations (target_type, target_id, observed_at DESC)` — correlation +
  incident detection
- `incidents (organization_id, created_at DESC)` — incident list
- `incident_events (incident_id, created_at)` — audit trail
- `outbox_events (status, available_after, created_at) WHERE status IN
  (pending, processing)` — outbox polling
- `audit_logs (organization_id, created_at DESC)`

## Partitioning readiness

`check_results` and `observations` are the high-volume tables. Phase 1 keeps
them plain; the migration path to time-based partitioning (PostgreSQL native
range partitioning on `created_at` / `observed_at`) is:

1. Add partition key column or confirm the existing timestamp is the
   partition key.
2. `CREATE TABLE check_results_new (...) PARTITION BY RANGE (created_at)`
   with monthly partitions; identical indexes/constraints.
3. Insert new data into the partitioned table (application writes target the
   parent).
4. Backfill historical rows, then swap: rename + drop the old table.
5. Partition maintenance (create/drop monthly partitions, `DETACH PARTITION`
   for archival) via a scheduled job.

Do not partition in Phase 1; the schema is ready for it.

## Migrations

- Files: `NNNN_name.up.sql` / `NNNN_name.down.sql`, embedded and applied
  transactionally by the `migrate` binary; state in `schema_migrations`.
- `make migrate-up|migrate-down|migrate-status`.
- **Deployment sequencing:** run `migrate up` before starting new code
  (migration-before-compatible-code), and prefer additive migrations so the
  previous version keeps working during rolling deploys.

## Query mode

The default `RELI_DATABASE_QUERY_MODE=exec` uses the extended protocol
without a statement cache: jsonb/timestamptz parameters are passed as text
and the server infers types, which is compatible with PGlite, RDS proxies and
PgBouncer transaction mode. `simple` (simple protocol) and `cache` (pgx
default prepared-statement cache) are available where parse overhead matters.
