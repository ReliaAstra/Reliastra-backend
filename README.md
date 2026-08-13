# RELIASTRA MVP — EXTERNAL DEPENDENCY INTELLIGENCE PLATFORM BACKEND

Reliastra is an **external dependency intelligence platform** that monitors third-party vendor APIs and services from independent geographic locations, correlates vendor failures with customer-reported incidents, and generates timestamped SLA evidence reports.

---

## 🚀 Features & Core Tenets

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
6. **Triple Authentication**:
   - **Email/Password** registration and login with bcrypt-hashed passwords.
   - **Google OAuth 2.0** — authorization code flow with automatic account creation, email-based account linking, and verified email enforcement.
   - **GitHub OAuth 2.0** — authorization code flow with parallel user info + email fetching, multi-tier email resolution (public → primary verified → any verified → noreply fallback), and automatic account creation.
   - JWT Access (`15m` expiry) and Refresh (`7d` expiry) tokens for all human user flows.
   - Hashed API keys (SHA-256) for programmatic and CI/CD access (`rel_...`).
7. **SLA Evidence Generation**:
   - Renders structured incident metadata, per-region latency charts (embedded SVG), SLA degradation percentages, and cross-vendor correlations into pixel-perfect PDF evidence reports.
   - Automatically calculates cryptographic SHA-256 checksums and logs immutable events to the audit trail.

---

## 🛠️ Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| **API Framework** | FastAPI (Python 3.11+) | Auto-OpenAPI generation, async-native, Pydantic v2 validation |
| **ORM / Models** | SQLAlchemy 2.0 (async) | Fully typed async ORM with Alembic migration support |
| **Database** | PostgreSQL 15+ | JSONB support + native RANGE partitioning for high-volume time-series data |
| **Cache / Queue** | Redis 7+ | Celery broker/backend, idempotency cache, rate limiting |
| **Task Queue** | Celery + Celery Beat | Check scheduler (every 10s), evidence PDF generation, alert dispatch |
| **Object Storage** | MinIO (S3-Compatible) | Storage for generated evidence PDF reports |
| **Auth** | JWT + API Keys + OAuth 2.0 | Stateless, organization-scoped, RBAC-ready; Google & GitHub OAuth support |
| **PDF Generation** | Playwright / HTML | High-fidelity HTML to PDF rendering with automatic local fallback |

---

## 📁 Project Structure

```
reliastra/
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
│   │   ├── auth/               # Email auth, Google OAuth, GitHub OAuth, refresh, logout
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
│       └── email.py            # SMTP/SES email sending client
├── templates/
│   └── evidence/
│       └── default.html        # Jinja2 HTML template for SLA evidence PDF reports
├── tests/
│   ├── conftest.py             # Pytest fixtures: embedded PostgreSQL, FakeRedis, async TestClient
│   ├── unit/                   # Comprehensive service tests with mocked repositories
│   ├── integration/            # Full API endpoint tests
│   └── e2e/                    # Full E2E check execution, correlation, and evidence flow
├── docker-compose.yml          # Bootstraps Postgres, Redis, MinIO, MailHog, API, Celery Worker & Beat
├── Dockerfile                  # Application Docker image
├── celery_worker.dockerfile    # Dedicated Celery worker Dockerfile
├── alembic.ini                 # Alembic configuration
└── pyproject.toml              # Poetry dependencies, pytest configuration
```

---

## 🐳 Docker Compose Up Instructions

To boot up all Reliastra MVP backend services locally:

1. Ensure Docker and Docker Compose are installed.
2. From the repository root, start the stack:
   ```bash
   docker-compose up -d --build
   ```
3. Docker Compose will launch:
   - **PostgreSQL 15 (`postgres`)**: Port `5432` (persistent volume `postgres_data`)
   - **Redis 7 (`redis`)**: Port `6379`
   - **MinIO (`minio`)**: Ports `9000` (API) and `9001` (Web Console, default user/pass: `minioadmin`/`minioadmin`)
   - **MailHog (`mailhog`)**: Ports `1025` (SMTP) and `8025` (Web UI for viewing email alerts)
   - **Reliastra API (`api`)**: Port `8000` (auto-runs Alembic migrations and starts Uvicorn)
   - **Celery Worker (`celery-worker`)**: Executes background checks, alerts, and evidence generation
   - **Celery Beat (`celery-beat`)**: Runs check scheduler every 10 seconds

4. Verify service health:
   ```bash
   curl http://localhost:8000/health
   # {"status": "ok", "service": "reliastra-backend"}
   ```

---

## 📖 API Documentation & Frontend Integration Guide

FastAPI automatically generates live interactive OpenAPI documentation:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) (Exported locally to `docs/openapi.json`)
- **Frontend & Dashboard Integration Guide**: See [`docs/FRONTEND_API_INTEGRATION_GUIDE.md`](./docs/FRONTEND_API_INTEGRATION_GUIDE.md) for complete TypeScript interfaces, authentication workflows, RBAC matrix, and pre-built Axios interceptor patterns.

---

## 🧪 How to Run Tests

The test suite runs with **zero external dependencies required** by leveraging embedded PostgreSQL (`pgserver`) and `fakeredis` in `tests/conftest.py`.

### Using Poetry / Virtual Environment

1. Install dependencies:
   ```bash
   poetry install
   # Or using pip in a virtual environment:
   # pip install -r requirements.txt / pip install -e .
   ```
2. Run all unit, integration, and E2E tests:
   ```bash
   poetry run pytest -v
   ```
3. Run specific test suites:
   ```bash
   # Unit tests only (service layer with mocked repositories):
   poetry run pytest tests/unit -v

   # Integration tests only (every API endpoint):
   poetry run pytest tests/integration -v

   # End-to-end check execution & correlation flow:
   poetry run pytest tests/e2e -v
   ```

---

## 🔐 OAuth Configuration (Google & GitHub)

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

---

## 🏛️ Architecture Decision Records (ADRs)

### ADR-001: Why FastAPI + SQLAlchemy 2.0 Async?
- **Decision**: Use FastAPI with SQLAlchemy 2.0 in fully asynchronous mode (`asyncpg`).
- **Rationale**: FastAPI provides auto-generated OpenAPI documentation, native Pydantic v2 validation, and async endpoint execution. Using SQLAlchemy 2.0 async mode ensures the event loop is never blocked during I/O-bound database operations, which is critical for scaling high-frequency check execution and multi-tenant analytics.

### ADR-002: Why Celery over Pure Asyncio for Checks?
- **Decision**: Use Celery + Celery Beat backed by Redis for check scheduling and background task execution.
- **Rationale**: Check execution requires reliable scheduling (Beat running every 10 seconds), automatic retries, distributed worker pooling, and task queue visibility. Implementing this on raw `asyncio` would require rebuilding a distributed task broker. Celery allows workers (`checks`, `evidence`, `notifications`) to scale independently from the stateless HTTP API tier.

### ADR-003: Why Partition `CheckResult` by Month?
- **Decision**: Use PostgreSQL native range partitioning (`PARTITION BY RANGE (executed_at)`) for the `check_results` table.
- **Rationale**: `CheckResult` is the highest-volume table in the system (potentially millions of rows per month). Partitioning by month allows PostgreSQL to drop old partitions efficiently without table locks, improves index density for recent dashboard queries, and enables seamless future migration to OLAP time-series engines (e.g., ClickHouse or TimescaleDB) without application changes.

### ADR-004: Why Application-Layer Encryption for `Dependency.headers`?
- **Decision**: Encrypt sensitive vendor API keys and headers in `Dependency.headers` at the application layer using symmetric Fernet encryption before storing them in the JSONB column.
- **Rationale**: Vendor API credentials must never be stored plaintext. Deriving a deterministic Fernet key from `SECRET_KEY` protects credentials against database dump leaks without requiring PostgreSQL Transparent Data Encryption (TDE), which is difficult to manage across containerized and Kubernetes environments.

### ADR-005: Why Playwright over WeasyPrint for PDF Evidence Reports?
- **Decision**: Use Playwright headless browser rendering for PDF evidence report generation, with an automatic `xhtml2pdf` fallback for offline or lightweight test sandboxes.
- **Rationale**: Evidence reports must be pixel-perfect with embedded SVG latency charts and responsive tables. Playwright renders HTML and CSS exactly like a modern web browser, supporting flexbox and complex CSS features where WeasyPrint falls short. The automatic fallback ensures tests and lightweight containers remain resilient even if Chromium binaries are absent.

### ADR-006: Why Authorization Code Flow for OAuth (not Implicit/PKCE)?
- **Decision**: Implement both Google and GitHub OAuth using the server-side authorization code flow, where the backend exchanges the code for tokens and the frontend never handles provider access tokens directly.
- **Rationale**: The authorization code flow keeps OAuth client secrets server-side (never exposed to the browser), eliminates token leakage risk on the frontend, and allows the backend to perform account linking and user creation atomically within a single database transaction. This is more secure than the implicit flow (deprecated by OAuth 2.1) and simpler than PKCE for server-rendered API backends. The backend acts as a trusted intermediary, exchanging the short-lived authorization code for provider tokens, fetching user profiles, and returning only Reliastra JWTs to the frontend.

### ADR-007: Why Email-Based Account Linking Across OAuth Providers?
- **Decision**: When a user authenticates via Google or GitHub and an existing user with the same email already exists, automatically link the OAuth identity to the existing account instead of creating a duplicate.
- **Rationale**: Users expect to use the same account across sign-in methods. Without email-based linking, a user who signs up with email and later tries Google SSO would get a confusing "account already exists" error. The linking approach reduces friction and matches the behavior of major platforms (GitHub, GitLab, Notion). The trade-off is that an attacker who controls an unverified email on a provider could potentially link to another user's account — this is mitigated by requiring verified emails on Google and prioritizing verified emails on GitHub.
