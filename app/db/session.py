import logging
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event, pool
from app.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

_WRITE_FLAG = "_reliastra_writes"


def _install_write_tracking() -> None:
    """Track uncommitted writes per-session via SQLAlchemy events.

    ``Session.new/dirty/deleted`` do NOT capture objects that were already
    flushed (a flushed INSERT leaves ``new``), so request sessions that write
    then flush would be mistaken for read-only. Every explicit flush and
    every non-SELECT statement executed through a session sets a flag in
    ``session.info``; ``get_db`` consults it to decide commit vs rollback.

    Events are registered on the sync ``Session`` class — ``AsyncSession``
    wraps a sync session and forwards these ORM events.
    """

    from sqlalchemy.orm import Session as _SyncSession

    @event.listens_for(_SyncSession, "after_flush")
    def _mark_flushed(session: Any, flush_context: Any) -> None:
        session.info[_WRITE_FLAG] = True

    @event.listens_for(_SyncSession, "do_orm_execute")
    def _mark_dml(orm_execute_state: Any) -> None:
        statement = orm_execute_state.statement
        if not getattr(statement, "is_select", False):
            orm_execute_state.session.info[_WRITE_FLAG] = True


_install_write_tracking()


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


def build_engine() -> AsyncEngine:
    """Create a new async engine from the current settings (no caching)."""
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
    return create_async_engine(clean_url, **engine_kwargs)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine()
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
    """FastAPI dependency yielding a request-scoped session.

    FIX 38: a COMMIT is only issued when the session actually modified data
    (ORM unit-of-work: new/deleted/dirty). Read-only GET requests instead end
    their implicit transaction with a cheap ROLLBACK, which releases the
    pooled connection without any write to the WAL or the commit
    round-trip semantics on hot probe-heavy paths.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            if session.is_active:
                dirty = bool(
                    session.info.get(_WRITE_FLAG)
                    or session.new
                    or session.deleted
                    or session.dirty
                )
                if dirty:
                    await session.commit()
                else:
                    await session.rollback()
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
