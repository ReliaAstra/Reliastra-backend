#!/usr/bin/env bash
set -euo pipefail

echo "=== Reliastra standalone entrypoint ==="

# ── 1. Boot PostgreSQL ──────────────────────────────────────────────────
PGDATA="/var/lib/postgresql/data"
PGRUN="/var/run/postgresql"

if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "[init] Initializing PostgreSQL database cluster..."
    mkdir -p "$PGDATA" "$PGRUN"
    chown -R postgres:postgres "$PGDATA" "$PGRUN"
    gosu postgres initdb --auth=trust --username=postgres
    # Configure pg_hba.conf for local trust auth
    echo "local all all trust" > "$PGDATA/pg_hba.conf"
    echo "host  all all 127.0.0.1/32 trust" >> "$PGDATA/pg_hba.conf"
    echo "host  all all ::1/128 trust" >> "$PGDATA/pg_hba.conf"
    echo "host  all all 0.0.0.0/0 trust" >> "$PGDATA/pg_hba.conf"
    # Tune for small container
    cat >> "$PGDATA/postgresql.auto.conf" <<'PGCONF'
listen_addresses = '*'
max_connections = 100
shared_buffers = 128MB
effective_cache_size = 256MB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 4MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 100MB
max_wal_size = 2GB
PGCONF
fi

# Ensure runtime dirs exist with correct ownership
mkdir -p "$PGDATA" "$PGRUN"
chown -R postgres:postgres "$PGDATA" "$PGRUN"
chmod 0777 "$PGRUN"

# Start PostgreSQL in background for init/migrations
echo "[init] Starting PostgreSQL for migrations..."
gosu postgres pg_ctl start -w -D "$PGDATA" -o "-c listen_addresses='*' -p 5432" 2>&1 | tail -3

# Wait for Postgres to be ready
for i in $(seq 1 30); do
    if gosu postgres psql -h 127.0.0.1 -U postgres -c "SELECT 1" &>/dev/null; then
        echo "[init] PostgreSQL is ready."
        break
    fi
    echo "[init] Waiting for PostgreSQL... ($i/30)"
    sleep 1
done

# Create the database if it doesn't exist
gosu postgres psql -h 127.0.0.1 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='reliastra'" | grep -q 1 || \
    gosu postgres psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE reliastra"
echo "[init] Database 'reliastra' is available."

# Stop PostgreSQL (supervisord will start it)
echo "[init] Stopping PostgreSQL (supervisord will manage it)..."
gosu postgres pg_ctl stop -D "$PGDATA" -m fast 2>/dev/null || true

# ── 2. Redis is stateless — supervisord handles it ─────────────────────
echo "[init] Redis will be started by supervisord."

# ── 3. Override connection URLs for local services ────────────────────────
export DATABASE_URL="postgresql+asyncpg://postgres@127.0.0.1:5432/reliastra"
export REDIS_URL="redis://127.0.0.1:6379/0"
export MINIO_ENDPOINT="127.0.0.1:9000"

# Ensure dev environment unless explicitly set (production rejects default SECRET_KEY)
export ENVIRONMENT="${ENVIRONMENT:-development}"

# ── 4. Start all services via supervisord ──────────────────────────────
echo "=== Starting supervisord (postgres → redis → celery → api) ==="

# Wait for postgres to be ready again under supervisord
sleep 3
for i in $(seq 1 30); do
    if gosu postgres psql -h 127.0.0.1 -U postgres -c "SELECT 1" &>/dev/null; then
        echo "[init] PostgreSQL (supervisord) is ready."
        break
    fi
    echo "[init] Waiting for PostgreSQL (supervisord)... ($i/30)"
    sleep 1
done

# Wait for Redis
for i in $(seq 1 15); do
    if redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; then
        echo "[init] Redis is ready."
        break
    fi
    echo "[init] Waiting for Redis... ($i/15)"
    sleep 1
done

# ── 5. Run database migrations ─────────────────────────────────────────
echo "[init] Running Alembic migrations..."
/opt/venv/bin/alembic upgrade head 2>&1
echo "[init] Migrations complete."

# ── 6. Hand off to supervisord (runs in foreground) ────────────────────
exec /usr/local/bin/supervisord -c /app/supervisord.conf
