#!/usr/bin/env bash
set -euo pipefail

echo "=== Reliastra standalone entrypoint ==="

# Debian puts PG binaries in /usr/lib/postgresql/<ver>/bin — not on default PATH.
PG_BIN=$(pg_config --bindir 2>/dev/null || true)
if [ -z "${PG_BIN:-}" ] || [ ! -d "$PG_BIN" ]; then
    PG_BIN=$(find /usr/lib/postgresql -maxdepth 2 -name initdb -type f 2>/dev/null | head -1 | xargs -r dirname)
fi
if [ -n "${PG_BIN:-}" ] && [ -d "$PG_BIN" ]; then
    export PATH="$PG_BIN:$PATH"
    echo "[init] PostgreSQL bin dir: $PG_BIN"
fi

# Must be exported: initdb/pg_ctl read PGDATA from the environment.
export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
export PGHOST="${PGHOST:-/var/run/postgresql}"
PGRUN="${PGHOST}"
PGLOGDIR="/var/log/postgresql"
PGBOOTLOG="$PGLOGDIR/bootstrap.log"

# ── 1. Boot PostgreSQL ──────────────────────────────────────────────────
if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "[init] Initializing PostgreSQL database cluster at $PGDATA..."
    mkdir -p "$PGDATA" "$PGRUN"
    chown -R postgres:postgres "$PGDATA" "$PGRUN"
    chmod 700 "$PGDATA"
    # -D is required; a local (non-exported) PGDATA is invisible to initdb.
    gosu postgres initdb -D "$PGDATA" --auth=trust --username=postgres
    cat > "$PGDATA/pg_hba.conf" <<'HBA'
local all all trust
host  all all 127.0.0.1/32 trust
host  all all ::1/128 trust
host  all all 0.0.0.0/0 trust
HBA
    chown postgres:postgres "$PGDATA/pg_hba.conf"
    cat >> "$PGDATA/postgresql.auto.conf" <<'PGCONF'
listen_addresses = '*'
unix_socket_directories = '/var/run/postgresql'
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
    chown postgres:postgres "$PGDATA/postgresql.auto.conf"
fi

mkdir -p "$PGDATA" "$PGRUN" "$PGLOGDIR"
chown -R postgres:postgres "$PGDATA" "$PGRUN" "$PGLOGDIR"
chmod 700 "$PGDATA"
chmod 0777 "$PGRUN"

echo "[init] Starting PostgreSQL for migrations..."
# NEVER pipe `pg_ctl -w` (e.g. `| tail -5`): the server inherits the pipe, the
# pipe buffer fills, `tail` blocks waiting for EOF that never comes, and
# `pg_ctl -w` blocks waiting for the server -> container boot deadlocks.
# Use -l so the server writes to a file and pg_ctl owns no pipe at all.
: > "$PGBOOTLOG"
chown postgres:postgres "$PGBOOTLOG"
if gosu postgres pg_ctl start -w -t 120 -D "$PGDATA" -l "$PGBOOTLOG" \
        -o "-c listen_addresses='*' -p 5432 -c unix_socket_directories='$PGRUN'"; then
    echo "[init] pg_ctl start finished"
else
    echo "[init] FATAL: pg_ctl start failed; bootstrap log follows:" >&2
    tail -50 "$PGBOOTLOG" >&2 || true
    exit 1
fi
tail -20 "$PGBOOTLOG" || true

for i in $(seq 1 30); do
    if gosu postgres psql -h 127.0.0.1 -U postgres -c "SELECT 1" &>/dev/null; then
        echo "[init] PostgreSQL is ready."
        break
    fi
    echo "[init] Waiting for PostgreSQL... ($i/30)"
    sleep 1
done

gosu postgres psql -h 127.0.0.1 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='reliastra'" | grep -q 1 || \
    gosu postgres psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE reliastra"
echo "[init] Database 'reliastra' is available."

# Local in-container services (override any PaaS DATABASE_URL pointing elsewhere)
export DATABASE_URL="postgresql+asyncpg://postgres@127.0.0.1:5432/reliastra"
export REDIS_URL="redis://127.0.0.1:6379/0"
export ENVIRONMENT="${ENVIRONMENT:-development}"

echo "[init] Running Alembic migrations..."
/opt/venv/bin/alembic upgrade head
echo "[init] Migrations complete."

echo "[init] Stopping bootstrap PostgreSQL (supervisord will manage it)..."
gosu postgres pg_ctl stop -D "$PGDATA" -m fast 2>/dev/null || true

# ── 2. Launch supervisord ───────────────────────────────────────────────
# Debian installs supervisor at /usr/bin/supervisord (not /usr/local/bin).
SUPERVISORD_BIN="$(command -v supervisord || true)"
if [ -z "$SUPERVISORD_BIN" ]; then
    echo "[init] FATAL: supervisord not found on PATH" >&2
    exit 1
fi

# supervisord `environment=` replaces the process env; inject PATH + PGDATA.
if grep -q '^environment=PGDATA=' /app/supervisord.conf; then
    sed -i "s|^environment=PGDATA=|environment=PATH=${PG_BIN}:/opt/venv/bin:/usr/local/bin:/usr/bin:/bin,PGDATA=|" /app/supervisord.conf
fi

echo "=== Starting supervisord ($SUPERVISORD_BIN) ==="
exec "$SUPERVISORD_BIN" -c /app/supervisord.conf
