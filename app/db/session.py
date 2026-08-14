import logging
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
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
    return urlunparse(parsed._replace(query=urlencode(qs, doseq=True) if qs else ""))


def _build_connect_args() -> dict:
    """Build asyncpg ``connect_args`` with a proper ``ssl`` key.

    asyncpg expects an ``ssl.SSLContext`` object — it does **not** read
    ``sslmode`` from the connection URL.  We detect the desired mode from
    the ``DATABASE_SSL_MODE`` setting (or from the raw URL query string as
    a fallback) and translate it into an appropriate Python SSL context.
    """
    ssl_mode = settings.DATABASE_SSL_MODE
    if not ssl_mode:
        parsed = urlparse(settings.DATABASE_URL)
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

        # PgBouncer/Supabase pooler needs prepared-statement workaround
        if _needs_pooler_compat(clean_url):
            (connect_args or {}).update({"prepare_statement_cache_size": 0})
            if not connect_args:
                connect_args = {"prepare_statement_cache_size": 0}

        logger.info(
            "Creating async engine — pool_size=10, max_overflow=20, ssl=%s, pooler_compat=%s",
            bool(connect_args and connect_args.get("ssl")),
            _needs_pooler_compat(clean_url),
        )
        _engine = create_async_engine(
            clean_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            future=True,
            connect_args=connect_args if connect_args else None,
        )
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
