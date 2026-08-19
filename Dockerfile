# Dockerfile for Reliastra-backend
# Self-contained: PostgreSQL + Redis + Celery worker/beat + API in one container.
# For single-container PaaS platforms (ZevCloud, Railway, Render, etc.)
# ---------------------------------------------------------------------------

# ── Stage 1: Build Python venv ───────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN python -m venv --copies /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools build && \
    pip install .

# ── Stage 2: Runtime image with all services ─────────────────────────────
FROM python:3.12-slim

# Install PostgreSQL, Redis, supervisord, and utilities
# Debian Trixie ships PostgreSQL 17; gosu replaces Alpine's su-exec
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql \
    redis-server \
    supervisor \
    gosu \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY . .

# Install Playwright Chromium for evidence generation tasks
RUN playwright install --with-deps chromium 2>/dev/null || true

# Create required directories
RUN mkdir -p /app/templates /var/lib/postgresql/data /var/run/postgresql /var/log/supervisor

# Copy supervisord config and entrypoint
COPY supervisord.conf /app/supervisord.conf
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

# Expose the API port
EXPOSE 8000

# Health check for the container orchestrator
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8000/health/live || exit 1

# The entrypoint bootstraps Postgres, runs migrations, then hands off to supervisord
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
