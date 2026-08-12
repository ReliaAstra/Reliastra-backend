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

# Use the manual payment provider in tests (no gateway credentials needed).
os.environ.setdefault("PAYMENT_PROVIDER", "manual")

from app.config import settings
from app.db.session import get_db, set_test_engine
from app.infrastructure.redis_client import set_test_redis
from app.main import app

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
    alembic_cfg.set_main_option("sqlalchemy.url", pg_uri)
    command.upgrade(alembic_cfg, "head")

    yield pg_uri


@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_engine(setup_test_db_server: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(setup_test_db_server, echo=False, future=True)
    set_test_engine(engine)

    async with engine.begin() as conn:
        for table in [
            "audit_logs",
            "evidence_snapshots",
            "attribution_results",
            "ai_providers",
            "subscriptions",
            "vendor_incidents",
            "vendor_metrics_daily",
            "probe_configs",
            "vendor_endpoints",
            "vendors",
            "observations",
            "refresh_tokens",
            "api_keys",
            "alert_configs",
            "evidence_reports",
            "incident_correlations",
            "incidents",
            "check_results",
            "applications",
            "clients",
            "dependencies",
            "organization_members",
            "organizations",
            "users",
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
    token_data = res.json()

    # Get user profile
    me_res = await async_client.get(
        "/v1/users/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_res.status_code == 200, me_res.text
    user_data = me_res.json()

    # Get organization
    orgs_res = await async_client.get(
        "/v1/orgs",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert orgs_res.status_code == 200, orgs_res.text
    orgs_data = orgs_res.json()

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
        "user_id": user_data["id"],
        "email": register_payload["email"],
        "org_id": orgs_data[0]["id"],
        "org_slug": orgs_data[0]["slug"],
    }
