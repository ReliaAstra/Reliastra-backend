# RELIASTRA

Reliastra monitors third-party vendor APIs and services, correlates failures with customer-reported incidents, attributes blame with a deterministic engine, and generates cryptographically verifiable SLA evidence reports.

This is the canonical Reliastra monorepo: the Next.js frontend and the FastAPI backend live side by side as independent applications.

## Repository structure

```
Reliastra/
├── frontend/     # Next.js app (marketing, partner network, dashboard UI)
├── backend/      # FastAPI app (API, workers, evidence, billing)
├── docs/architecture/
├── .github/workflows/
├── Makefile
└── README.md
```

Source applications were consolidated from:

- Frontend: https://github.com/ReliaAstra/Frontend
- Backend: https://github.com/ReliaAstra/Reliastra-backend

Those repositories are kept as references. Application code was not rewritten for this move.

## Architecture

```
User
  ↓
Next.js frontend          frontend/
  ↓  existing HTTP API contract
Reliastra API             backend/  (FastAPI, /v1/*)
  ↓
PostgreSQL · Redis · Celery · Supabase Storage (S3)
  ↓
Vendor APIs, Google/GitHub OAuth, Paystack, SMTP
```

Details: [`docs/architecture/OVERVIEW.md`](docs/architecture/OVERVIEW.md).

The frontend currently talks to the deployed API at `https://reliastra-backend.zevcloud.app`. Moving the code into this repository does not change API paths, auth, or schemas.

## Frontend development

Requires Node.js 20+ (the app also has a `bun.lock`; Bun works if you prefer it).

```bash
cd frontend
cp .env.example .env
npm install
npx prisma generate
npm run dev
```

This starts Next.js on port 3000 (`next dev -p 3000`).

Other scripts from `frontend/package.json`:

| Script | Command |
|--------|---------|
| `npm run dev` | Next.js dev server on :3000 |
| `npm run build` | Production build (standalone) |
| `npm run start` | Serve standalone build via Bun |
| `npm run lint` | ESLint |
| `npm run db:generate` | `prisma generate` |
| `npm run db:push` | `prisma db push` |
| `npm run db:migrate` | `prisma migrate dev` |
| `npm run db:reset` | `prisma migrate reset` |

There is no frontend unit-test script in `package.json`.

## Backend development

Requires Python 3.11+, PostgreSQL 15+, and Redis 7+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL, REDIS_URL, and SECRET_KEY at minimum
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Docker Compose (from `backend/`):

```bash
cd backend
docker-compose up -d --build
```

That starts PostgreSQL, Redis, MailHog, the API, and Celery workers. Object storage is **Supabase Storage (S3) only** — set `SUPABASE_S3_*` in `backend/.env` before compose (see `backend/.env.example`).

Health check: `GET http://localhost:8000/health`

API docs: `http://localhost:8000/docs`

## Environment variables

Do not commit `.env` files.

| App | Template | Purpose |
|-----|----------|---------|
| Frontend | `frontend/.env.example` | Prisma `DATABASE_URL` (local SQLite) |
| Backend | `backend/.env.example` | Postgres, Redis, JWT `SECRET_KEY`, CORS, OAuth, Paystack, Supabase S3, SMTP, partner program |

Backend required for a real run: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`. Production also needs `ENVIRONMENT=production`, `CORS_ORIGINS`, and the `SUPABASE_S3_*` keys for evidence storage.

## Testing

```bash
# Backend (from backend/; uses embedded PostgreSQL + FakeRedis)
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock fakeredis pgserver moto
pytest -v
pytest tests/unit -v
pytest tests/integration -v
pytest tests/e2e -v

# Frontend lint
cd frontend
npm install
npm run lint
```

Or from the repo root: `make test` (backend pytest) and `make lint`.

## Production architecture

Frontend and backend deploy independently. This monorepo does not force a combined release.

- **Frontend:** Next.js `output: "standalone"` (`frontend/next.config.ts`). Host with your existing frontend platform.
- **Backend:** Docker image (GHCR) and/or Nixpacks. GitHub Actions CD builds `backend/` and deploys the API container to the existing VPS. Compose file: `backend/docker-compose.production.yml`.
- **PaaS root directory** for backend-only hosts (Railway, Render, Nixpacks) must be `backend/`.

CI is path-aware: changes under `frontend/**` run frontend checks; changes under `backend/**` run backend lint/import/security/tests.

## License

Proprietary — All rights reserved.
