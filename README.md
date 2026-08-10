# Reliastra Backend — Phase 1

**External Dependency Intelligence and Incident Evidence.**

Reliastra independently observes customer services *and* their external
dependencies, correlates the two deterministically, and produces verifiable
evidence describing what happened when a service degrades.

> **Observation is disposable. Evidence is durable.**
> Raw monitoring data can expire; finalized evidence and the data necessary
> to explain an incident must remain trustworthy.

## Architecture at a glance

```
API (stateless)   Scheduler        Worker × N         Notifier
   │                  │                │                 │
   └─────────┬────────┴── PostgreSQL ──┴─── object storage
             │         (source of truth)      (evidence artifacts)
             └── Redis (rate limit / coordination, optional)
```

- **API** — auth, tenancy, CRUD, queries. Never executes checks synchronously.
- **Scheduler** — creates durable `check_jobs` for due monitors (idempotent,
  jittered, missed-run aware). Multiple schedulers may run concurrently.
- **Worker** — leases jobs with `FOR UPDATE SKIP LOCKED`, executes
  SSRF-safe HTTP checks, writes result + observation + outbox event in one
  transaction, feeds the incident detector.
- **Notifier** — drains the transactional outbox: async evidence generation
  and notification delivery (email/Slack) with retry + dead-letter.
- **Incident engine** — deterministic rules (consecutive failures, failure
  rate, region consensus); explicit auditable state machine.
- **Correlation engine** — deterministic v1 scoring
  (temporal/regional/latency/error/failure overlap × criticality), versioned
  and explainable. No AI in the attribution path.
- **Evidence engine** — canonical JSON + PDF artifact, SHA-256 hash in
  PostgreSQL, byte-immutable, verifiable (`GET /v1/evidence/{id}/verify`).

## Quick start (development)

Prerequisites: Go 1.25+, PostgreSQL 15+, Redis (optional), object storage
(filesystem backend is fine for dev).

```bash
# 1. Configure environment
export RELI_DATABASE_URL='postgres://reliastra:password@localhost:5432/reliastra?sslmode=disable'
export RELI_ENCRYPTION_MASTER_KEY=$(openssl rand -hex 32)
export RELI_ENV=development

# 2. Migrate + seed
make migrate-up
make seed

# 3. Run the processes
make run-api            # or: ./bin/api
go run ./cmd/scheduler
go run ./cmd/worker
go run ./cmd/notifier
```

Smoke test:

```bash
curl -s localhost:8080/health/live
curl -s -X POST localhost:8080/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"super-secret-password"}'
```

## Docker

```bash
cp .env.example .env   # edit RELI_ENCRYPTION_MASTER_KEY etc.
make docker-build
docker compose up -d
```

See `deployments/compose/.env.example` for the full configuration reference.

## Configuration

All configuration is environment-based (`RELI_*`), validated at startup.
Required values fail fast; optional values have safe defaults. Never run
production without `RELI_ENCRYPTION_MASTER_KEY` (validated).

Key variables (see `internal/platform/config` for the complete list):

| Variable | Default | Purpose |
|---|---|---|
| `RELI_DATABASE_URL` | — (required) | PostgreSQL DSN |
| `RELI_DATABASE_QUERY_MODE` | `exec` | pgx protocol mode (exec/simple/cache) |
| `RELI_REDIS_ADDR` | (empty) | Redis; empty disables distributed rate limiting |
| `RELI_OBJECT_STORE_BACKEND` | `filesystem` | `s3` or `filesystem` |
| `RELI_OBJECT_STORE_*` | — | S3 endpoint/bucket/keys for `s3` |
| `RELI_ENCRYPTION_MASTER_KEY` | — (required in prod) | 32-byte hex AES key for secrets at rest |
| `RELI_SCHEDULER_*`, `RELI_WORKER_*`, `RELI_NOTIFIER_*` | — | per-process tuning |
| `RELI_INCIDENT_*` | — | detection rule thresholds |
| `RELI_PLANS_DEFAULT` | `free` | plan limits (entitlements) |

## API

OpenAPI contract: `api/openapi/openapi.yaml`.

All responses use a uniform envelope. Authenticated endpoints use
`Authorization: Bearer <token>`; user sessions pick the tenant with
`X-Reliasorg: <organization_id>`.

Core endpoints: auth (`/v1/auth/*`, `/v1/me`), organizations, projects,
services, dependencies + links, monitors + results, regions, incidents,
evidence (generate/verify/download), API keys, notification channels, audit
logs, public vendor tracking (`/v1/vendors/*`), `/health/live`,
`/health/ready`, `/metrics` (Prometheus).

## Documentation

- `docs/architecture/` — architecture, job execution, correlation algorithm,
  evidence, database, observability
- `docs/security/` — threat model
- `docs/operations/` — backups/restore (RPO/RTO)
- `docs/disaster-recovery/` — runbook (10 failure scenarios)
- `docs/testing/` — testing strategy

## Testing

```bash
make test               # unit tests
make test-integration   # e2e against a real PostgreSQL (RELI_TEST_DATABASE_URL)
make lint               # go vet
```

## Repo layout

```
cmd/{api,scheduler,worker,notifier,migrate}   process entrypoints
internal/{auth,organizations,projects,services,dependencies,monitors,
          regions,checks,incidents,correlation,evidence,notifications,
          billing,audit,health,publictracking,seed}   domain modules
internal/platform/{config,database,redis,objectstore,encryption,outbox,
                   ratelimit,httpapi,app}     infrastructure
pkg/{logging,metrics,tracing,errors,clock,ids}
migrations/                                   embedded SQL migrations
api/openapi/                                  OpenAPI contract
deployments/  docs/  tests/{integration,load} scripts/
```
