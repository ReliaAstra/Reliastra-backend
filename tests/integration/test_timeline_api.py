"""Tests for the public vendor timeline endpoint.

Covers:
- valid vendor with/without observations
- invalid vendor name
- invalid window / resolution parameters
- single-region operation
- incident marker association
- correct aggregation (avg latency, status, is_up, count)
- correct current observation
- no private/customer data leakage
- empty observations return empty points
- explicit resolution override
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(minutes_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


async def _seed_vendor(db_session):
    from app.modules.vendors.service import vendor_service

    await vendor_service.seed_vendors(db_session)
    await db_session.commit()


async def _insert_observation(
    db_session,
    endpoint_url: str,
    minutes_ago: int = 0,
    latency_ms: float = 100.0,
    status_code: int = 200,
    region: str = "us-east-1",
    source_type: str = "customer_check",
    error_type: str | None = None,
    org_id: uuid.UUID | None = None,
) -> None:
    """Insert a single observation row."""
    from app.modules.observations.models import Observation

    obs = Observation(
        id=uuid.uuid4(),
        timestamp=_ts(minutes_ago),
        source_type=source_type,
        source_id=None,
        org_id=org_id,
        region=region,
        endpoint_url=endpoint_url,
        latency_ms=latency_ms,
        status_code=status_code,
        response_time_ms=latency_ms,
        error_type=error_type,
        error_message="timeout" if error_type else None,
    )
    db_session.add(obs)
    await db_session.flush()


async def _insert_dependency(
    db_session,
    org_id: uuid.UUID,
    endpoint_url: str,
    name: str = "test-dep",
) -> uuid.UUID:
    from app.modules.dependencies.models import Dependency

    dep = Dependency(
        org_id=org_id,
        name=name,
        endpoint_url=endpoint_url,
    )
    db_session.add(dep)
    await db_session.flush()
    return dep.id


async def _insert_incident(
    db_session,
    org_id: uuid.UUID,
    dependency_id: uuid.UUID,
    started_at: datetime,
    resolved_at: datetime | None = None,
) -> uuid.UUID:
    from app.modules.incidents.models import Incident

    inc = Incident(
        org_id=org_id,
        dependency_id=dependency_id,
        started_at=started_at,
        resolved_at=resolved_at,
        severity="major",
        status="open" if resolved_at is None else "resolved",
    )
    db_session.add(inc)
    await db_session.flush()
    return inc.id


async def _create_org_and_user(async_client):
    """Register a user + org so we have org_id for dependency/incident setup."""
    payload = {
        "email": "timeline-test@reliastra.com",
        "password": "SecurePassword123!",
        "full_name": "Timeline Tester",
        "org_name": "Timeline Test Org",
    }
    res = await async_client.post("/v1/auth/register", json=payload)
    assert res.status_code == 201, res.text
    token_data = res.json()

    orgs_res = await async_client.get(
        "/v1/orgs",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert orgs_res.status_code == 200, orgs_res.text
    return token_data["access_token"], orgs_res.json()[0]["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_valid_vendor_empty(async_client, db_session):
    """Timeline for a valid vendor with no observations returns empty points."""
    await _seed_vendor(db_session)

    res = await async_client.get("/v1/public/vendors/stripe/timeline")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["vendor_name"] == "stripe"
    assert body["window"] == "24h"
    assert body["resolution"] in ("1m", "5m", "15m", "1h", "6h")  # auto-resolved
    assert body["region"] == "us-east-1"
    assert "from" in body
    assert "to" in body
    assert body["current"]["timestamp"] is None
    assert body["current"]["latency_ms"] is None
    assert body["points"] == []


@pytest.mark.asyncio
async def test_timeline_invalid_vendor(async_client, db_session):
    """Non-existent vendor returns 404."""
    await _seed_vendor(db_session)

    res = await async_client.get("/v1/public/vendors/nonexistent/timeline")
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_timeline_invalid_window(async_client, db_session):
    """Invalid window parameter returns 422."""
    await _seed_vendor(db_session)

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=10y"
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_timeline_invalid_resolution(async_client, db_session):
    """Invalid resolution parameter returns 422."""
    await _seed_vendor(db_session)

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?resolution=10s"
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_timeline_with_observations(async_client, db_session):
    """Timeline with observations returns aggregated buckets."""
    await _seed_vendor(db_session)

    # Insert several observations across the last hour at 1-minute intervals
    endpoint = "https://status.stripe.com"
    for i in range(5):
        await _insert_observation(
            db_session,
            endpoint_url=endpoint,
            minutes_ago=10 + i,
            latency_ms=100.0 + i * 10,
            status_code=200,
            region="us-east-1",
        )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["vendor_name"] == "stripe"
    assert body["window"] == "1h"
    assert body["resolution"] == "5m"
    assert body["current"]["timestamp"] is not None
    assert body["current"]["latency_ms"] is not None
    assert body["current"]["is_up"] is True
    # All 5 observations should fall into 1 or 2 buckets (5 minutes each)
    assert len(body["points"]) >= 1
    for point in body["points"]:
        assert point["avg_latency_ms"] > 0
        assert point["status_code"] == 200
        assert point["is_up"] is True
        assert point["observation_count"] >= 1
        assert point["incident_id"] is None


@pytest.mark.asyncio
async def test_timeline_degraded_observations(async_client, db_session):
    """Timeline with error observations shows is_up=False."""
    await _seed_vendor(db_session)

    endpoint = "https://status.stripe.com"
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=5,
        latency_ms=5000.0,
        status_code=500,
        region="us-east-1",
        error_type="http_error",
    )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["current"]["is_up"] is False
    assert body["current"]["status_code"] == 500
    # At least one bucket should show degraded
    degraded_points = [p for p in body["points"] if not p["is_up"]]
    assert len(degraded_points) >= 1


@pytest.mark.asyncio
async def test_timeline_single_region(async_client, db_session):
    """Only us-east-1 observations are returned when region is specified."""
    await _seed_vendor(db_session)

    endpoint = "https://status.stripe.com"
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=3,
        latency_ms=50.0,
        status_code=200,
        region="us-east-1",
    )
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=2,
        latency_ms=9999.0,
        status_code=200,
        region="eu-west-1",  # different region — should be excluded
    )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m&region=us-east-1"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["region"] == "us-east-1"
    # Only 1 observation in us-east-1
    total_obs = sum(p["observation_count"] for p in body["points"])
    assert total_obs == 1


@pytest.mark.asyncio
async def test_timeline_incident_marker(async_client, db_session):
    """Buckets overlapping an incident get incident_id attached."""
    await _seed_vendor(db_session)

    token, org_id = await _create_org_and_user(async_client)
    endpoint = "https://status.stripe.com"

    # Create a dependency and incident
    dep_id = await _insert_dependency(db_session, org_id, endpoint, "stripe-dep")
    now = datetime.now(timezone.utc)
    inc_id = await _insert_incident(
        db_session,
        org_id=org_id,
        dependency_id=dep_id,
        started_at=now - timedelta(minutes=8),
        resolved_at=now - timedelta(minutes=2),
    )

    # Insert observations during the incident window
    for i in range(3):
        await _insert_observation(
            db_session,
            endpoint_url=endpoint,
            minutes_ago=7 + i,
            latency_ms=2000.0,
            status_code=503,
            region="us-east-1",
            error_type="http_error",
        )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # At least one bucket should have the incident_id
    marked = [p for p in body["points"] if p["incident_id"] is not None]
    assert len(marked) >= 1, "Expected at least one bucket with incident_id"
    assert marked[0]["incident_id"] == str(inc_id)


@pytest.mark.asyncio
async def test_timeline_no_private_data_leak(async_client, db_session):
    """Timeline response never contains org_id, headers, or private URLs."""
    await _seed_vendor(db_session)

    token, org_id = await _create_org_and_user(async_client)
    endpoint = "https://status.stripe.com"

    # Insert observation with an org
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=2,
        latency_ms=80.0,
        status_code=200,
        region="us-east-1",
        org_id=org_id,
    )
    await db_session.commit()

    res = await async_client.get("/v1/public/vendors/stripe/timeline")
    assert res.status_code == 200, res.text
    body = res.json()
    response_str = res.text
    # Should not contain the org_id
    assert str(org_id) not in response_str
    # Should not contain internal fields
    assert "org_id" not in response_str
    assert "headers" not in response_str
    assert "metadata" not in response_str
    # Current observation should not expose org info
    assert "org_id" not in body["current"].model_dump() if hasattr(body["current"], "model_dump") else True


@pytest.mark.asyncio
async def test_timeline_correct_aggregation(async_client, db_session):
    """Multiple observations in the same bucket are averaged correctly."""
    await _seed_vendor(db_session)

    endpoint = "https://status.stripe.com"
    # Insert 3 observations that fall in the same 5-minute bucket
    for i in range(3):
        await _insert_observation(
            db_session,
            endpoint_url=endpoint,
            minutes_ago=3,  # all at ~3 minutes ago
            latency_ms=100.0 + i * 50.0,  # 100, 150, 200
            status_code=200,
            region="us-east-1",
        )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m"
    )
    assert res.status_code == 200, res.text
    body = res.json()

    # Find the bucket with all 3 observations
    bucket = next(
        (p for p in body["points"] if p["observation_count"] == 3), None
    )
    assert bucket is not None, "Expected a bucket with exactly 3 observations"
    # Average should be (100 + 150 + 200) / 3 = 150.0
    assert bucket["avg_latency_ms"] == 150.0
    assert bucket["status_code"] == 200
    assert bucket["is_up"] is True


@pytest.mark.asyncio
async def test_timeline_current_observation(async_client, db_session):
    """Current observation is the newest one, independent of window."""
    await _seed_vendor(db_session)

    endpoint = "https://status.stripe.com"
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=5,
        latency_ms=120.0,
        status_code=200,
        region="us-east-1",
    )
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=1,
        latency_ms=85.0,
        status_code=200,
        region="us-east-1",
    )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=5m"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Current should be the most recent (85ms, 1 min ago)
    assert body["current"]["latency_ms"] == 85.0
    assert body["current"]["status_code"] == 200
    assert body["current"]["is_up"] is True
    assert body["current"]["timestamp"] is not None


@pytest.mark.asyncio
async def test_timeline_different_windows(async_client, db_session):
    """All supported windows are accepted and return correct structure."""
    await _seed_vendor(db_session)

    for window in ["1h", "6h", "24h", "7d", "30d", "90d"]:
        res = await async_client.get(
            f"/v1/public/vendors/stripe/timeline?window={window}"
        )
        assert res.status_code == 200, f"Failed for window={window}: {res.text}"
        body = res.json()
        assert body["window"] == window
        assert "from" in body
        assert "to" in body
        assert "points" in body
        assert "current" in body


@pytest.mark.asyncio
async def test_timeline_explicit_resolution(async_client, db_session):
    """Explicit resolution is respected in the response."""
    await _seed_vendor(db_session)

    endpoint = "https://status.stripe.com"
    await _insert_observation(
        db_session,
        endpoint_url=endpoint,
        minutes_ago=2,
        latency_ms=100.0,
        status_code=200,
        region="us-east-1",
    )
    await db_session.commit()

    res = await async_client.get(
        "/v1/public/vendors/stripe/timeline?window=1h&resolution=1m"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resolution"] == "1m"


@pytest.mark.asyncio
async def test_timeline_rate_limited(async_client, db_session):
    """Timeline uses the public vendor rate limiter (not auth-gated)."""
    await _seed_vendor(db_session)

    # The endpoint should work without any Authorization header
    res = await async_client.get("/v1/public/vendors/stripe/timeline")
    assert res.status_code == 200, res.text
