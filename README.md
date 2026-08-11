# Reliastra Backend

Reliastra is an API-first, multi-tenant external-dependency intelligence service. It runs independent HTTP checks, confirms failures by regional quorum, correlates customer and vendor incidents, and produces tamper-evident SLA evidence PDFs in S3-compatible storage.

## Stack

Python 3.11, FastAPI, async SQLAlchemy/asyncpg, PostgreSQL 15, Redis 7, Celery/Beat, MinIO, Playwright, Jinja2, and Alembic.

## Start the complete stack

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env
# Replace every `replace-with-...` value in .env. DATABASE_URL must use the same
# POSTGRES_PASSWORD value. SECRET_KEY must contain at least 32 characters.
docker compose up --build
```

Services:

- API and OpenAPI UI: <http://localhost:8000/docs>
- Health/readiness: <http://localhost:8000/healthz> and <http://localhost:8000/readyz>
- MinIO console: <http://localhost:9001>
- MailHog: <http://localhost:8025>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3001>

The API container applies Alembic migrations before starting. The initial migration creates all tables, native monthly `check_results` partitions for 2025–2031, a default safety partition, and the five public vendor records (Stripe, Auth0, Cloudflare, OpenAI, and Twilio). Production operations should add the next year's partitions before year end.

## First API flow

```bash
curl -sS http://localhost:8000/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"CorrectHorse9Battery","full_name":"Example Owner"}'
```

Registration returns the user, personal organization, access token, and refresh token. Authenticated organization calls use:

```text
Authorization: Bearer <access-token>
X-Organization-ID: <organization-uuid>  # optional when org_id is already in the path
```

Programmatic clients use `Authorization: ApiKey <key>`. The plaintext API key is returned only by `POST /v1/orgs/{org_id}/api-keys/`; only its SHA-256 digest is persisted.

## Check and evidence workers

Celery Beat claims due dependencies every 10 seconds with `FOR UPDATE SKIP LOCKED`, advances `next_check_at`, and fans work out per configured region. A failure needs two distinct regions inside 60 seconds. Recovery needs two consecutive successful checks in two regions. Resolved correlated incidents on Standard or higher can queue Playwright PDF generation; files are uploaded to MinIO and only object metadata plus SHA-256 is stored in PostgreSQL.

Install Chromium when running workers outside Docker:

```bash
poetry install
poetry run playwright install chromium
```

## Database migrations

```bash
poetry run alembic upgrade head
poetry run alembic downgrade -1
```

`CheckResult` has a composite physical primary key `(id, executed_at)`. PostgreSQL requires every unique key on a partitioned table to contain the partition key; the API still treats `id` as the stable result identifier. See ADR-003.

## Tests and static checks

```bash
poetry install
poetry run pytest
poetry run ruff check app tests
poetry run mypy app
```

The suite covers security and RBAC policy, plan enforcement, recovery quorum, extension registration, every required OpenAPI route, the strict module file contract, and the incident service flow. Docker-backed deployments should additionally smoke-test migrations and Playwright against the exact production image.

## Architecture

The enforced dependency direction is:

```text
router -> service -> repository -> model
```

Routers contain transport concerns only. Services own policy. Repositories own persistence statements. Cross-domain orchestration uses public services or named Celery tasks. Dashboard reads compose public service methods and may use the configured replica session. Headers are Fernet-encrypted before entering JSONB. APIs use a stable error envelope:

```json
{"error":{"code":"RESOURCE_NOT_FOUND","message":"...","details":{}}}
```

The implementation has no process-global database, Redis, or storage clients; FastAPI lifespan state and constructor injection own those resources. Celery's application object is the sole framework-required module-level runtime object.

### Architecture decision records

- [ADR-001: FastAPI and async SQLAlchemy](docs/adr/001-fastapi-async-sqlalchemy.md)
- [ADR-002: Celery for distributed checks](docs/adr/002-celery-check-execution.md)
- [ADR-003: Native monthly check partitions](docs/adr/003-check-result-partitioning.md)
- [ADR-004: Application-layer header encryption](docs/adr/004-header-encryption.md)
- [ADR-005: Playwright evidence rendering](docs/adr/005-playwright-pdf.md)

## Production notes

- Put the API behind TLS and a trusted reverse proxy.
- Use separate Redis databases/clusters for rate limiting and Celery at scale.
- Rotate `SECRET_KEY` through a managed secret store; encrypted dependency headers require a staged key-rotation procedure.
- Restrict MinIO bucket access and enable object locking/versioning for stronger evidence retention.
- Set `DATABASE_REPLICA_URL` for dashboard read traffic.
- Restrict `/metrics`, `/healthz`, and `/readyz` to the platform network at the ingress. Prometheus and Grafana are included in Compose; production deployments should use managed persistence and SSO.
