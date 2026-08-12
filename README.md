# Reliastra — External Dependency Intelligence Platform

Reliastra monitors third-party vendor APIs and services, correlates failures with customer-reported incidents, attributes blame using a deterministic 5-signal engine, and generates cryptographically verifiable SLA evidence reports.

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/ReliaAstra/Reliastra-backend.git
cd Reliastra-backend
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, and SECRET_KEY at minimum

# 3. Run database migrations
alembic upgrade head

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Production Deployment

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL with asyncpg driver | `postgresql+asyncpg://user:pass@host:5432/reliastra` |
| `REDIS_URL` | Redis for rate limiting, Celery, idempotency | `redis://host:6379/0` |
| `SECRET_KEY` | JWT signing key (min 32 chars) | Use `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENVIRONMENT` | Set to `production` | `production` |
| `CORS_ORIGINS` | JSON array of allowed frontend origins | `["https://yourdomain.com"]` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `PAYSTACK_SECRET_KEY` | _(empty)_ | Paystack API secret key |
| `PAYSTACK_PUBLIC_KEY` | _(empty)_ | Paystack public key for checkout |
| `MINIO_ENDPOINT` | `localhost:9000` | S3-compatible storage for evidence PDFs |
| `MINIO_ACCESS_KEY` | `minioadmin` | Storage access key |
| `MINIO_SECRET_KEY` | `minioadmin` | Storage secret key |
| `SMTP_HOST` | `localhost` | SMTP server for notifications |
| `SMTP_PORT` | `1025` | SMTP port |
| `SMTP_FROM` | `noreply@reliastra.com` | Sender email address |

### Deployment Checklist

1. Set all required environment variables (DATABASE_URL, REDIS_URL, SECRET_KEY, ENVIRONMENT, CORS_ORIGINS)
2. Ensure PostgreSQL 15+ and Redis 7+ are accessible from the container
3. Run `alembic upgrade head` to create database tables
4. Set `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY` to enable billing
5. Set `MINIO_*` variables to enable evidence PDF storage
6. Verify health: `GET /health` should return `{"status": "ok", ...}`

### Docker Compose (Local Development)

```bash
docker-compose up -d --build
```

This starts PostgreSQL, Redis, MinIO, MailHog, the API server, and Celery workers. The API auto-runs migrations on startup.

## API Documentation

- **Swagger UI**: `/docs`
- **OpenAPI JSON**: `/openapi.json`
- **Frontend Integration Guide**: [`docs/FRONTEND_API_INTEGRATION_GUIDE.md`](./docs/FRONTEND_API_INTEGRATION_GUIDE.md)

## Architecture

### Domain Modules

The codebase follows a modular monolith pattern. Each module contains its own router, service, repository, models, and schemas:

| Module | Prefix | Auth | Description |
|--------|--------|------|-------------|
| Authentication | `/v1/auth` | Public | Register, login, refresh, logout |
| Users | `/v1/users` | JWT/API Key | User profile management |
| Organizations | `/v1/orgs` | JWT/API Key | Multi-tenant org and member management |
| Dependencies | `/v1/orgs/{id}/dependencies` | JWT/API Key | External API monitoring targets |
| Checks | `/v1/orgs/{id}/checks` | JWT/API Key | Check execution results and history |
| Incidents | `/v1/orgs/{id}/incidents` | JWT/API Key | Incident detection and correlation |
| Evidence | `/v1/orgs/{id}/evidence` | JWT/API Key | SLA evidence report generation |
| Vendors | `/v1/public/vendors` | Public | Global vendor status tracking |
| Notifications | `/v1/orgs/{id}/notifications` | JWT/API Key | Alert channel management |
| Dashboard | `/v1/orgs/{id}/dashboard` | JWT/API Key | Aggregated analytics |
| Billing | `/v1/orgs/{id}/billing` | JWT/API Key | Paystack payment integration |
| API Keys | `/v1/orgs/{id}/api-keys` | JWT/API Key | Programmatic access keys |
| Agencies | `/v1/orgs/{id}/agencies` | JWT/API Key | Agency hierarchy management |
| AI Integration | `/v1/orgs/{id}/ai-providers` | JWT/API Key | Provider-agnostic AI configuration |
| Verification | `/v1/verify/{id}` | Public | Evidence cryptographic verification |

### Authentication

Two authentication methods are supported:

- **JWT**: `Authorization: Bearer <token>` — 15min access, 7-day refresh
- **API Keys**: `X-API-Key: rel_xxxxxxxx` — SHA-256 hashed, scope-enforced

### RBAC Hierarchy

```
Owner (40) > Admin (30) > Member (20) > Viewer (10)
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (Python 3.11+) |
| ORM | SQLAlchemy 2.0 (async, asyncpg) |
| Database | PostgreSQL 15+ |
| Cache / Queue | Redis 7+ |
| Task Queue | Celery + Beat |
| Object Storage | MinIO (S3-compatible) |
| Billing | Paystack |
| Auth | JWT + SHA-256 API Keys |
| Encryption | Fernet (derived from SECRET_KEY) |

## Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests (zero external dependencies — uses embedded PostgreSQL + FakeRedis)
pytest -v

# Run specific suites
pytest tests/unit -v        # Service layer with mocked repos
pytest tests/integration -v # Full API endpoint tests
pytest tests/e2e -v         # End-to-end check execution and evidence flow
```

## Project Structure

```
Reliastra-backend/
├── app/
│   ├── main.py              # FastAPI app factory, middleware, lifespan
│   ├── config.py            # Pydantic Settings (env vars)
│   ├── dependencies.py      # Auth, org context, RBAC dependencies
│   ├── core/                # Security, permissions, exceptions, rate limiting
│   ├── db/                  # SQLAlchemy engine, session, Alembic migrations
│   ├── modules/             # 15 domain modules
│   └── infrastructure/      # Redis, Celery, MinIO, SMTP clients
├── templates/evidence/      # Jinja2 evidence report template
├── tests/                   # Unit, integration, and E2E tests
├── docs/                    # OpenAPI spec and frontend integration guide
├── docker-compose.yml       # Local development stack
├── .env.example             # Environment variable reference
└── alembic.ini              # Database migration config
```

## License

Proprietary — All rights reserved.
