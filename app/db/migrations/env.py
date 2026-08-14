import asyncio
import ssl as _ssl
from logging.config import fileConfig
from urllib.parse import urlparse, parse_qs
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

# Use the SSL-aware database URL for migrations
db_url = settings.database_url_with_ssl


def _build_ssl_connect_args() -> dict:
    """Build asyncpg-compatible SSL connect args from DATABASE_SSL_MODE or URL query."""
    ssl_mode = settings.DATABASE_SSL_MODE
    if not ssl_mode:
        parsed = urlparse(db_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" in qs:
            ssl_mode = qs["sslmode"][0]
    if not ssl_mode:
        return {}

    ctx = _ssl.create_default_context()
    if ssl_mode == "require":
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
    elif ssl_mode == "verify-ca":
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_REQUIRED
    elif ssl_mode == "verify-full":
        ctx.check_hostname = True
        ctx.verify_mode = _ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
    return {"ssl": ctx}


# Set URL without sslmode in query (asyncpg doesn't accept sslmode kwarg)
parsed = urlparse(db_url)
qs = parse_qs(parsed.query, keep_blank_values=True)
qs.pop("sslmode", None)
from urllib.parse import urlencode, urlunparse
clean_url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True) if qs else ""))
config.set_main_option("sqlalchemy.url", clean_url)


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


async def run_async_migrations() -> None:
    connect_args = _build_ssl_connect_args()
    engine = create_async_engine(
        clean_url,
        poolclass=pool.NullPool,
        connect_args=connect_args if connect_args else None,
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
