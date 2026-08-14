import logging
from collections.abc import AsyncGenerator
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


def _build_connect_args() -> dict:
    """Build asyncpg connect_args with SSL configuration when needed.

    asyncpg uses an ``ssl`` key in connect_args (not sslmode in the URL).
    We inspect the DATABASE_URL (or the resolved database_url_with_ssl) to
    determine whether the user wants SSL, then create the appropriate
    ``ssl`` kwarg for asyncpg.
    """
    ssl_mode = settings.DATABASE_SSL_MODE
    if not ssl_mode:
        # Also check if sslmode is already in the raw DATABASE_URL query string
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(settings.DATABASE_URL)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" in qs:
            ssl_mode = qs["sslmode"][0]

    if not ssl_mode:
        return {}

    import ssl as _ssl

    if ssl_mode in ("require", "verify-ca", "verify-full"):
        # Create an SSL context that requires the connection to be encrypted
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
        return {"ssl": ctx}

    # For "prefer" or other modes, create a lenient context
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    return {"ssl": ctx}


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = settings.database_url_with_ssl
        connect_args = _build_connect_args()
        logger.info(
            "Creating async engine — pool_size=10, max_overflow=20, ssl=%s",
            bool(connect_args.get("ssl")),
        )
        _engine = create_async_engine(
            db_url,
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
