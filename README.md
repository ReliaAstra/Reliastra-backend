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

## Features & Core Tenets

1. **API-First Only**: Every piece of data, every operation, and every query goes through versioned REST API endpoints (`/v1/*`). No direct database access; no GraphQL.
2. **Modular Architecture**: The codebase is organized by domain modules (`app/modules/`). Each domain (`auth`, `users`, `organizations`, `dependencies`, `checks`, `incidents`, `evidence`, `vendors`, `notifications`, `dashboard`, `billing`, `api_keys`) is self-contained with its own explicit interface contract:
   ```
   router.py → service.py → repository.py → models.py
   ```
3. **Extensibility by Design**:
   - Notification routing uses a Strategy pattern with a pluggable `CHANNEL_REGISTRY` supporting Email, Slack, PagerDuty, and Webhooks.
   - Incident correlation uses an extensible `BaseCorrelationStrategy` interface with Temporal Correlation (`±5m` window) implemented as the MVP default.
4. **Scalability Hooks**:
   - High-volume time-series check execution data (`CheckResult`) is partitioned by month using PostgreSQL native range partitioning (`PARTITION BY RANGE (executed_at)`).
   - Redis-backed sliding window rate limiter, idempotency caching (`Idempotency-Key` header with 24h TTL), and Celery task queues.
5. **Multi-Tenant & RBAC**: Every API call is scoped to an Organization. Roles follow the hierarchy:
   ```
   Owner (40) > Admin (30) > Member (20) > Viewer (10)
   ```
6. **Triple Authentication & Account Security**:
   - **Email/Password** registration and login with bcrypt-hashed passwords.
   - **Google OAuth 2.0** — authorization code flow with automatic account creation, email-based account linking, and verified email enforcement.
   - **GitHub OAuth 2.0** — authorization code flow with parallel user info + email fetching, multi-tier email resolution (public → primary verified → any verified → noreply fallback), and automatic account creation.
   - **Email Verification** — one-time link sent to user's inbox, SHA-256 hashed tokens with 60-minute expiry, automatic revocation of prior tokens on re-send.
   - **Password Reset** — anti-enumeration forgot-password flow (generic success message regardless of email existence), SHA-256 hashed tokens with 15-minute expiry, single-use tokens with automatic revocation.
   - JWT Access (`15m` expiry) and Refresh (`7d` expiry) tokens for all human user flows.
   - Hashed API keys (SHA-256) for programmatic and CI/CD access (`rel_...`).
7. **SLA Evidence Generation**:
   - Renders structured incident metadata, per-region latency charts (embedded SVG), SLA degradation percentages, and cross-vendor correlations into pixel-perfect PDF evidence reports.
   - Automatically calculates cryptographic SHA-256 checksums and logs immutable events to the audit trail.

## Production Deployment

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL with asyncpg driver (works with Supabase, Neon, RDS, etc.) | `postgresql+asyncpg://user:pass@host:5432/reliastra` |
| `DATABASE_SSL_MODE` | SSL mode for external databases (`require`, `verify-full`) | `require` |
| `REDIS_URL` | Redis for rate limiting, Celery, idempotency | `redis://host:6379/0` |
| `SECRET_KEY` | JWT signing key (min 32 chars) | Use `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENVIRONMENT` | Set to `production` | `production` |
| `CORS_ORIGINS` | JSON array of allowed frontend origins | `["https://yourdomain.com"]` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `GOOGLE_AUTH_ENABLED` | `false` | Enable Google OAuth |
| `GOOGLE_CLIENT_ID` | _(empty)_ | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | _(empty)_ | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | _(empty)_ | Google OAuth redirect URI |
| `GITHUB_AUTH_ENABLED` | `false` | Enable GitHub OAuth |
| `GITHUB_CLIENT_ID` | _(empty)_ | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | _(empty)_ | GitHub OAuth client secret |
| `GITHUB_REDIRECT_URI` | _(empty)_ | GitHub OAuth redirect URI |
| `PAYSTACK_SECRET_KEY` | _(empty)_ | Paystack API secret key |
| `PAYSTACK_PUBLIC_KEY` | _(empty)_ | Paystack public key for checkout |
| `MINIO_ENDPOINT` | `localhost:9000` | S3-compatible storage for evidence PDFs |
| `MINIO_ACCESS_KEY` | `minioadmin` | Storage access key |
| `MINIO_SECRET_KEY` | `minioadmin` | Storage secret key |
| `SMTP_HOST` | `localhost` | SMTP server for notifications |
| `SMTP_PORT` | `1025` | SMTP port |
| `SMTP_FROM` | `noreply@reliastra.com` | Sender email address |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | Frontend base URL for email verification & password reset links |
| `SMTP_USE_TLS` | `false` | Enable TLS for SMTP (STARTTLS on port 587) |

### Deployment Checklist

1. Set all required environment variables (DATABASE_URL, REDIS_URL, SECRET_KEY, ENVIRONMENT, CORS_ORIGINS)
2. Ensure PostgreSQL 15+ and Redis 7+ are accessible from the container
3. Run `alembic upgrade head` to create database tables
4. Set OAuth variables to enable Google/GitHub sign-in
5. Set `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY` to enable billing
6. Set `MINIO_*` variables to enable evidence PDF storage
7. Verify health: `GET /health` should return `{"status": "ok", ...}`

### Docker Compose (Local Development)

```bash
docker-compose up -d --build
```

This starts PostgreSQL, Redis, MinIO, MailHog, the API server, and Celery workers. The API auto-runs migrations on startup.

## API Documentation

- **Swagger UI**: `/docs`
- **ReDoc UI**: `/redoc`
- **OpenAPI JSON**: `/openapi.json`
- **Frontend Integration Guide**: [`docs/FRONTEND_API_INTEGRATION_GUIDE.md`](./docs/FRONTEND_API_INTEGRATION_GUIDE.md)

## Architecture

### Domain Modules

The codebase follows a modular monolith pattern. Each module contains its own router, service, repository, models, and schemas:

| Module | Prefix | Auth | Description |
|--------|--------|------|-------------|
| Authentication | `/v1/auth` | Public | Register, login, refresh, logout, Google & GitHub OAuth, email verification, password reset |
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

Three authentication methods are supported for human users:

- **Email/Password**: `POST /v1/auth/register` and `POST /v1/auth/login`
- **Google OAuth**: `GET /v1/auth/google/url` → `POST /v1/auth/google`
- **GitHub OAuth**: `GET /v1/auth/github/url` → `POST /v1/auth/github`
- **JWT**: `Authorization: Bearer <token>` — 15min access, 7-day refresh
- **API Keys**: `X-API-Key: rel_xxxxxxxx` — SHA-256 hashed, scope-enforced
- **Email Verification**: `POST /v1/auth/send-verification` → `POST /v1/auth/verify-email`
- **Password Reset**: `POST /v1/auth/forgot-password` → `POST /v1/auth/reset-password`

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
| Auth | JWT + SHA-256 API Keys + OAuth 2.0 (Google, GitHub) |
| Encryption | Fernet (derived from SECRET_KEY) |

## OAuth Configuration (Google & GitHub)

OAuth providers are disabled by default. To enable, set the following environment variables:

```bash
# Google OAuth 2.0
GOOGLE_AUTH_ENABLED=true
GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="GOCSPX-xxxxxxxxxx"
GOOGLE_REDIRECT_URI="https://yourapp.com/auth/google/callback"

# GitHub OAuth 2.0
GITHUB_AUTH_ENABLED=true
GITHUB_CLIENT_ID="Ov23li_xxxxxxxx"
GITHUB_CLIENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
GITHUB_REDIRECT_URI="https://yourapp.com/auth/github/callback"
```

### OAuth Flow Summary

Both providers follow the **authorization code flow**:

1. **Frontend** calls `GET /v1/auth/{provider}/url` → receives an `authorization_url` + `state` token.
2. **Frontend** redirects the user to the provider's consent screen.
3. **Provider** redirects back to the frontend with a `code` query parameter.
4. **Frontend** sends `POST /v1/auth/{provider}` with `{ "code": "..." }`.
5. **Backend** exchanges the code for an access token, fetches user profile, finds or creates the local user, and returns JWT tokens.

### OAuth Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/auth/google/url` | Get Google OAuth authorization URL + state token |
| `POST` | `/v1/auth/google` | Exchange Google auth code for JWT tokens |
| `GET` | `/v1/auth/github/url` | Get GitHub OAuth authorization URL + state token |
| `POST` | `/v1/auth/github` | Exchange GitHub auth code for JWT tokens |

### Account Linking Behavior

If a user with the same email already exists (e.g., registered via email/password or the other OAuth provider), the OAuth flow **links** the new provider identity to the existing account rather than creating a duplicate. This means:
- A user who signs up with email can later sign in with Google or GitHub using the same email.
- A Google OAuth user can later sign in with GitHub if both use the same email.
- The `auth_provider` field is updated to reflect the most recently used provider.

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
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan hooks, idempotency & CORS middleware
│   ├── config.py               # Pydantic Settings & environment variable validation
│   ├── dependencies.py         # FastAPI dependency injection (DB session, auth, org context, RBAC)
│   ├── core/                   # Cross-cutting concerns
│   │   ├── security.py         # Password hashing, JWT encode/decode, API key generation, Fernet encryption
│   │   ├── permissions.py      # Role enum, hierarchy, and plan limit helpers
│   │   ├── exceptions.py       # Standard error envelope & global exception handlers
│   │   ├── pagination.py       # Standard cursor/offset pagination schemas
│   │   ├── rate_limit.py       # Redis sliding window rate limiter
│   │   └── audit_log.py        # Immutable audit log model and service
│   ├── db/
│   │   ├── session.py          # AsyncSession factory, engine, and get_db dependency
│   │   ├── base.py             # DeclarativeBase, mixins (UUIDMixin, TimestampMixin, SoftDeleteMixin)
│   │   └── migrations/         # Alembic migration scripts and env.py
│   ├── modules/                # Self-contained domain modules
│   │   ├── auth/               # Email auth, Google OAuth, GitHub OAuth, refresh, logout, email verification, password reset
│   │   ├── users/              # Current user profile (/me)
│   │   ├── organizations/      # Organizations & RBAC members management
│   │   ├── dependencies/       # External endpoints monitoring configurations
│   │   ├── checks/             # Check execution engine, time-series check results, quorum logic
│   │   ├── incidents/          # Service degradation detection, temporal correlation, resolution
│   │   ├── evidence/           # SLA report HTML/PDF generation & storage pipeline
│   │   ├── vendors/            # Public vendor tracking (Stripe, Auth0, Cloudflare, OpenAI, Twilio)
│   │   ├── notifications/      # Extensible alert routing (Email, Slack, PagerDuty, Webhook)
│   │   ├── dashboard/          # Read-only aggregated analytics endpoints
│   │   ├── billing/            # Stripe hooks stubbed for MVP & plan limits
│   │   └── api_keys/           # Programmatic access key management
│   └── infrastructure/
│       ├── celery_app.py       # Celery configuration and Beat check schedule
│       ├── redis_client.py     # Shared async Redis client
│       ├── storage.py          # S3/MinIO storage abstraction with fallback
│       └── email.py            # SMTP email sending client (verification & password reset emails)
├── templates/evidence/      # Jinja2 evidence report template
├── tests/                   # Unit, integration, and E2E tests
├── docs/                    # OpenAPI spec and frontend integration guide
├── docker-compose.yml       # Local development stack
├── .env.example             # Environment variable reference
└── alembic.ini              # Database migration config
```

## License

Proprietary — All rights reserved.
