import asyncio
from logging.config import fileConfig
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from app.config import settings
from app.db.base import Base, import_all_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import_all_models()
target_metadata = Base.metadata


def _build_ssl_connect_args(db_url: str, pooler_compat: bool = False) -> dict:
    """Build asyncpg-compatible SSL connect args from DATABASE_SSL_MODE or URL query.

    Only returns args for PostgreSQL URLs; all other drivers return an empty dict.
    When *pooler_compat* is True, also disables statement caching for PgBouncer.

    The sslmode → connect_args translation lives in
    :mod:`app.db.connect_args`; see there for why ``disable``/``prefer`` must
    not be turned into a hard SSL requirement (asyncpg answers a plaintext
    server's ``N`` to the SSLRequest with "rejected SSL upgrade").
    """
    if not db_url.startswith("postgresql"):
        return {}

    ssl_mode = settings.DATABASE_SSL_MODE
    if not ssl_mode:
        parsed = urlparse(db_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" in qs:
            ssl_mode = qs["sslmode"][0]

    from app.db.connect_args import build_ssl_connect_args

    return build_ssl_connect_args(ssl_mode, pooler_compat=pooler_compat)


# Use the SSL-aware database URL for migrations (only appends sslmode for PostgreSQL)
db_url = settings.database_url_with_ssl

# Strip sslmode from URL query string (asyncpg doesn't accept it as a URL param)
parsed = urlparse(db_url)
qs = parse_qs(parsed.query, keep_blank_values=True)
qs.pop("sslmode", None)
clean_url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True) if qs else ""))
# Alembic stores this in a ConfigParser, which treats '%' as interpolation
# syntax. Percent-encoded URLs (e.g. a unix socket host=%2Ftmp%2F...) must be
# escaped as '%%' or Alembic raises "invalid interpolation syntax".
config.set_main_option("sqlalchemy.url", clean_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def _needs_pooler_compat(url: str) -> bool:
    """True when the URL targets a PgBouncer / Supabase pooler."""
    return "pooler.supabase" in url or "pgbouncer" in url


async def run_async_migrations() -> None:
    pooler_compat = _needs_pooler_compat(clean_url)
    connect_args = _build_ssl_connect_args(clean_url, pooler_compat=pooler_compat)

    engine = create_async_engine(
        clean_url,
        poolclass=pool.NullPool,
        connect_args=connect_args or {},
    )

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
