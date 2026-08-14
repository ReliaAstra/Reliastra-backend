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


def _build_connect_args() -> dict:
    """Build asyncpg ``connect_args`` with a proper ``ssl`` key.

    asyncpg expects an ``ssl.SSLContext`` object — it does **not** read
    ``sslmode`` from the connection URL.  We detect the desired mode from
    the ``DATABASE_SSL_MODE`` setting (or from the raw URL query string as
    a fallback) and translate it into an appropriate Python SSL context.

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

    if not ssl_mode:
        return {}

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
    return {"ssl": ctx}


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
        clean_url = _strip_sslmode_from_url(raw_url)
        connect_args = _build_connect_args()

        # PgBouncer/Supabase pooler needs prepared-statement workaround.
        # asyncpg >= 0.30 removed prepare_statement_cache_size from connect()
        # and SQLAlchemy 2.0.36+ handles this via the pooler_compat flag or
        # server-side settings.  We set it via server_settings instead.
        pooler_compat = _needs_pooler_compat(clean_url)
        if pooler_compat:
            if connect_args:
                connect_args["server_settings"] = {
                    "prepare_statement_cache_size": "0",
                }
            else:
                connect_args = {
                    "server_settings": {"prepare_statement_cache_size": "0"},
                }

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
