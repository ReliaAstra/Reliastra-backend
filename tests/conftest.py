import asyncio
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any
import fakeredis.aioredis
import pgserver
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.session import get_db, set_test_engine
from app.infrastructure.redis_client import set_test_redis
from app.main import app

# Tests run like docker-compose: the standalone scheduler owns the queue, so
# the in-process (PaaS) scheduler must stay off — otherwise background ticks
# would probe test dependencies with real HTTP calls mid-assertion.
settings.RUN_IN_PROCESS_SCHEDULER = False

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db_server() -> Generator[str, None, None]:
    """Start embedded PostgreSQL server for session and apply migrations."""
    tmpdir = tempfile.mkdtemp(prefix="reliastra_test_pg_")
    srv = pgserver.get_server(pgdata=tmpdir, cleanup_mode="delete")
    pg_uri = srv.get_uri("postgres").replace("postgresql://", "postgresql+asyncpg://")
    os.environ["DATABASE_URL"] = pg_uri
    settings.DATABASE_URL = pg_uri

    # Run Alembic migrations
    alembic_cfg = Config("alembic.ini")
    # ConfigParser treats '%' as interpolation syntax. The pgserver URI holds a
    # percent-encoded unix socket path (host=%2Ftmp%2F...), so it must be
    # escaped as '%%' before being handed to Alembic or every test errors with
    # "invalid interpolation syntax".
    alembic_cfg.set_main_option("sqlalchemy.url", pg_uri.replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")

    yield pg_uri


@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_engine(setup_test_db_server: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(setup_test_db_server, echo=False, future=True)
    set_test_engine(engine)

    async with engine.begin() as conn:
        for table in [
            # Partner network. Listed children-first so the FK graph unwinds
            # without needing CASCADE; partner tables come before users and
            # organizations, which they reference.
            "partner_payout_items",
            "partner_commission_events",
            "partner_commissions",
            "partner_settlements",
            "partner_payouts",
            "partner_payout_accounts",
            "partner_fraud_flags",
            "partner_risk_assessments",
            "partner_claim_evidence",
            "partner_deployment_claims",
            "partner_customer_relationships",
            "partner_leads",
            "partner_attributions",
            "partner_click_events",
            "partner_referral_links",
            "partner_campaigns",
            "partner_tier_history",
            "partner_applications",
            "partners",
            "partner_geo_daily",
            "geo_ip_cache",
            "partner_program_content",
            "audit_logs",
            "observation_outbox",
            "refresh_tokens",
            "api_keys",
            "alert_configs",
            "evidence_reports",
            "incident_correlations",
            "incidents",
            "check_results",
            "dependencies",
            "organization_members",
            "organizations",
            "users",
            "observations",
            "vendor_endpoints",
            "vendor_trackings",
        ]:
            await conn.execute(text(f"DELETE FROM {table};"))

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def mock_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    set_test_redis(fake_redis)
    yield fake_redis
    await fake_redis.close()


@pytest_asyncio.fixture(scope="function")
async def fake_redis(mock_redis: fakeredis.aioredis.FakeRedis) -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Alias for the autouse fakeredis fixture (kept for explicit tests)."""
    yield mock_redis


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def async_client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture(scope="function")
def client() -> TestClient:
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def auth_data(async_client: AsyncClient) -> dict[str, Any]:
    register_payload = {
        "email": "owner@reliastra.com",
        "password": "SecurePassword123!",
        "full_name": "Test Owner",
        "org_name": "Reliastra Test Org",
    }
    res = await async_client.post("/v1/auth/register", json=register_payload)
    assert res.status_code == 201, res.text
    body = res.json()
    token_data = body["tokens"]
    user_data = body["user"]
    org = body["organization"]

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "headers": {
            "Authorization": f"Bearer {token_data['access_token']}",
            "X-Organization-ID": org["id"],
        },
        "user_id": user_data["id"],
        "email": register_payload["email"],
        "org_id": org["id"],
        "org_slug": org["slug"],
    }
