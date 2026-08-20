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

# ── Local cluster TLS (idempotent; works for fresh AND reused volumes) ──
# The platform may inject DATABASE_SSL_MODE=require (README lists it as a
# required var). Because DATABASE_URL below is overridden to THIS cluster,
# give it a self-signed certificate and enable SSL so strict client modes
# keep working. In-container processes still run with DATABASE_SSL_MODE=
# 'prefer', so boot never depends on the local TLS setup.
PG_CERT_DIR="/var/lib/postgresql/certs"
PG_CERT="$PG_CERT_DIR/server.crt"
PG_KEY="$PG_CERT_DIR/server.key"

# Detect whether the bundled PostgreSQL was built with OpenSSL.  A build
# without SSL support refuses to start when ssl=on is set, so only enable
# TLS when the server binary actually links libssl/libcrypto (Debian's
# PostgreSQL does; stripped-down embedded builds may not).
PG_SSL_SUPPORTED=0
if [ -n "${PG_BIN:-}" ] && [ -x "$PG_BIN/postgres" ] \
    && ldd "$PG_BIN/postgres" 2>/dev/null | grep -qiE "libssl|libcrypto"; then
    PG_SSL_SUPPORTED=1
fi

if [ "$PG_SSL_SUPPORTED" = "1" ] && { [ ! -f "$PG_KEY" ] || [ ! -f "$PG_CERT" ]; }; then
    mkdir -p "$PG_CERT_DIR"
    if /opt/venv/bin/python - "$PG_KEY" "$PG_CERT" <<'PYEOF'
import datetime
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

key_path, cert_path = sys.argv[1], sys.argv[2]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name(
    [
        x509.NameAttribute(NameOID.COMMON_NAME, "reliastra-local-postgres"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Reliastra (container-local)"),
    ]
)
now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=3650))
    .add_extension(
        x509.SubjectAlternativeName(
            [
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.IPAddress(ipaddress.ip_address("::1")),
            ]
        ),
        critical=False,
    )
    .add_extension(
        x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
    )
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(key, hashes.SHA256())
)
Path(key_path).write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
)
Path(cert_path).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
PYEOF
    then
        chown postgres:postgres "$PG_CERT_DIR" "$PG_KEY" "$PG_CERT"
        chmod 700 "$PG_CERT_DIR"
        chmod 600 "$PG_KEY"
        chmod 644 "$PG_CERT"
        echo "[init] Generated self-signed TLS certificate for local PostgreSQL."
    else
        echo "[init] WARNING: certificate generation failed; local PostgreSQL will run without SSL." >&2
    fi
fi

# Drop exactly the three ssl lines this script manages (never other settings).
remove_managed_ssl_lines() {
    sed -i \
        -e '/^ssl_cert_file[[:space:]]*=/d' \
        -e '/^ssl_key_file[[:space:]]*=/d' \
        -e '/^ssl[[:space:]]*=[[:space:]]*on[[:space:]]*$/d' \
        "$PGDATA/postgresql.auto.conf"
    chown postgres:postgres "$PGDATA/postgresql.auto.conf"
}

PG_NEW_SSL_LINES=0
if [ "$PG_SSL_SUPPORTED" = "1" ] && [ -f "$PG_KEY" ] && [ -f "$PG_CERT" ]; then
    touch "$PGDATA/postgresql.auto.conf"
    for setting in \
        "ssl = on" \
        "ssl_cert_file = '$PG_CERT'" \
        "ssl_key_file = '$PG_KEY'"; do
        key="${setting%% =*}"
        if ! grep -q "^${key}[[:space:]]*=" "$PGDATA/postgresql.auto.conf" 2>/dev/null; then
            echo "$setting" >> "$PGDATA/postgresql.auto.conf"
            PG_NEW_SSL_LINES=1
        fi
    done
    chown postgres:postgres "$PGDATA/postgresql.auto.conf"
    echo "[init] Local PostgreSQL TLS enabled (ssl=on)."
else
    if [ "$PG_SSL_SUPPORTED" != "1" ]; then
        echo "[init] PostgreSQL build has no SSL support; running plaintext (DATABASE_SSL_MODE=prefer keeps boot safe)."
    else
        echo "[init] WARNING: local TLS certificates missing; running plaintext (DATABASE_SSL_MODE=prefer keeps boot safe)." >&2
    fi
    # Never leave stale ssl=on from an earlier boot when we cannot honor it
    # this boot — the server would refuse to start.
    if grep -qE '^ssl(_cert_file|_key_file)?[[:space:]]*=' "$PGDATA/postgresql.auto.conf" 2>/dev/null; then
        remove_managed_ssl_lines
        echo "[init] Removed stale ssl settings from postgresql.auto.conf."
    fi
fi

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
elif [ "$PG_NEW_SSL_LINES" = "1" ]; then
    # We enabled ssl=on ourselves this boot and the server refused to start
    # (e.g. an unexpected build/cert problem). Never let the local TLS setup
    # block container boot: drop our three ssl lines and retry plaintext.
    # DATABASE_SSL_MODE below is forced to 'prefer', so plaintext is fine.
    echo "[init] WARNING: PostgreSQL failed to start with ssl=on; retrying without SSL." >&2
    tail -20 "$PGBOOTLOG" >&2 || true
    remove_managed_ssl_lines
    : > "$PGBOOTLOG"
    chown postgres:postgres "$PGBOOTLOG"
    if gosu postgres pg_ctl start -w -t 120 -D "$PGDATA" -l "$PGBOOTLOG" \
            -o "-c listen_addresses='*' -p 5432 -c unix_socket_directories='$PGRUN'"; then
        echo "[init] pg_ctl start finished (plaintext fallback)"
    else
        echo "[init] FATAL: pg_ctl start failed; bootstrap log follows:" >&2
        tail -50 "$PGBOOTLOG" >&2 || true
        exit 1
    fi
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

# The PaaS DATABASE_SSL_MODE (e.g. 'require') targets external managed
# databases, not this container-local cluster whose certificate is
# self-signed. Use advisory 'prefer': TLS is still negotiated (the local
# cluster has ssl=on), but certificate/hostname verification can never
# block container boot. Note: 'prefer' also survives a missing local cert.
export DATABASE_SSL_MODE="prefer"

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
