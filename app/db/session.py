import asyncio
import logging
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import pool
from app.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ensure_asyncpg_driver(url: str) -> str:
    """Ensure a PostgreSQL URL uses the asyncpg driver.

    ``create_async_engine`` requires the ``postgresql+asyncpg://`` scheme.
    If the caller (or environment variable) omits the driver prefix
    (e.g. ``postgresql://``), SQLAlchemy falls back to ``psycopg2`` which
    is not installed and causes a ``ModuleNotFoundError`` at startup.

    This is a common pitfall on PaaS platforms (Railway, Render, ZevCloud)
    where the dashboard may auto-generate a bare ``postgresql://`` URL.
    """
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _strip_sslmode_from_url(url: str) -> str:
    """Remove sslmode from URL query string.

    asyncpg does not recognise ``sslmode`` as a URL query parameter and
    raises TypeError.  We handle SSL via ``connect_args["ssl"]`` instead,
    so the parameter must be stripped from the URL before it reaches the
    asyncpg dialect.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("sslmode", None)
    new_query = urlencode(qs, doseq=True) if qs else ""
    # Preserve the original URL format: urlunparse may collapse "///" to "/"
    # for SQLite URLs which breaks parsing. Reconstruct carefully.
    if new_query:
        return urlunparse(parsed._replace(query=new_query))
    # No query params — return the original URL unchanged (preserves ///)
    if not parsed.query:
        return url
    return urlunparse(parsed._replace(query=""))


def _build_connect_args(pooler_compat: bool = False) -> dict:
    """Build asyncpg ``connect_args`` with SSL and pooler compatibility.

    asyncpg expects an ``ssl.SSLContext`` object — it does **not** read
    ``sslmode`` from the connection URL.  We detect the desired mode from
    the ``DATABASE_SSL_MODE`` setting (or from the raw URL query string as
    a fallback) and translate it into an appropriate Python SSL context.

    When *pooler_compat* is True (PgBouncer/Supabase pooler), we also set
    ``statement_cache_size=0`` to prevent asyncpg from using named prepared
    statements, which PgBouncer in transaction mode does not support.

    Only applies to PostgreSQL backends; SQLite and others return no args.
    """
    url = settings.DATABASE_URL
    if not url.startswith("postgresql"):
        return {}

    ssl_mode = settings.DATABASE_SSL_MODE
    if not ssl_mode:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" in qs:
            ssl_mode = qs["sslmode"][0]

    args: dict = {}

    if ssl_mode:
        import ssl as _ssl
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
        args["ssl"] = ctx

    if pooler_compat:
        args["statement_cache_size"] = 0

    return args


def _needs_pooler_compat(url: str) -> bool:
    """True when the URL targets a PgBouncer / Supabase pooler.

    PgBouncer in transaction mode does not support prepared statements.
    Setting ``prepare_statement_cache_size=0`` tells asyncpg to avoid
    using named prepared statements.
    """
    return "pooler.supabase" in url or "pgbouncer" in url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # Build clean URL (no sslmode query param) and SSL connect_args separately
        raw_url = settings.database_url_with_ssl
        raw_url = _ensure_asyncpg_driver(raw_url)
        clean_url = _strip_sslmode_from_url(raw_url)

        # PgBouncer/Supabase pooler needs prepared-statement workaround.
        # asyncpg's statement_cache_size=0 prevents named prepared statements
        # which PgBouncer in transaction mode does not support.
        pooler_compat = _needs_pooler_compat(clean_url)
        connect_args = _build_connect_args(pooler_compat=pooler_compat)

        # Determine engine kwargs based on backend
        is_sqlite = clean_url.startswith("sqlite")
        engine_kwargs: dict = dict(
            echo=False,
            future=True,
        )
        if is_sqlite:
            # SQLite: no connection pooling, no connect_args needed
            engine_kwargs["poolclass"] = pool.StaticPool
        else:
            # PostgreSQL: full connection pool
            engine_kwargs.update(
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
            )
            if connect_args:
                engine_kwargs["connect_args"] = connect_args

        logger.info(
            "Creating async engine — backend=%s, ssl=%s, pooler_compat=%s",
            "sqlite" if is_sqlite else "postgresql",
            bool(connect_args and connect_args.get("ssl")) if connect_args else False,
            pooler_compat,
        )
        _engine = create_async_engine(clean_url, **engine_kwargs)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine()
        _sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def set_test_engine(engine: AsyncEngine) -> None:
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def reset_engine() -> None:
    """Drop the cached engine/sessionmaker so the next caller rebuilds them.

    Used by the Celery tasks: each task runs its coroutine in a fresh asyncio
    event loop, but asyncpg connections are bound to the loop that created
    them.  Reusing the module-global engine across loops raises
    "Task got Future attached to a different loop" and silently drops the
    task (measured: schedule_checks returned 0 while the API scheduler did all
    the work).  Resetting per task bounds the leak to one pool per task and
    guarantees loop affinity.
    """
    global _engine, _sessionmaker
    engine = _engine
    _engine = None
    _sessionmaker = None
    if engine is not None:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            logger.debug("engine dispose during reset failed", exc_info=True)
