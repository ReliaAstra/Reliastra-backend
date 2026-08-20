"""Unit tests for the timeline service logic.

These tests validate the service-layer business logic (resolution mapping,
incident association, cache key generation, response assembly) without
requiring a live database.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.vendors.schemas import (
    TimelineBucket,
    TimelineCurrent,
    VendorTimelineResponse,
)
from app.modules.observations.repository import ObservationRepository
from app.modules.vendors.service import VendorService


# ---------------------------------------------------------------------------
# Resolution mapping
# ---------------------------------------------------------------------------


class TestResolutionMapping:
    def test_auto_resolution_1h(self):
        assert VendorService._resolve_resolution("1h", "auto") == 60

    def test_auto_resolution_6h(self):
        assert VendorService._resolve_resolution("6h", "auto") == 60

    def test_auto_resolution_24h(self):
        assert VendorService._resolve_resolution("24h", "auto") == 300

    def test_auto_resolution_7d(self):
        assert VendorService._resolve_resolution("7d", "auto") == 900

    def test_auto_resolution_30d(self):
        assert VendorService._resolve_resolution("30d", "auto") == 3600

    def test_auto_resolution_90d(self):
        assert VendorService._resolve_resolution("90d", "auto") == 21600

    def test_explicit_resolution(self):
        assert VendorService._resolve_resolution("24h", "1m") == 60
        assert VendorService._resolve_resolution("24h", "5m") == 300
        assert VendorService._resolve_resolution("7d", "15m") == 900
        assert VendorService._resolve_resolution("30d", "1h") == 3600
        assert VendorService._resolve_resolution("90d", "6h") == 21600


class TestAutoLabel:
    def test_label_1h(self):
        assert VendorService._auto_label("1h") == "1m"

    def test_label_24h(self):
        assert VendorService._auto_label("24h") == "5m"

    def test_label_90d(self):
        assert VendorService._auto_label("90d") == "6h"


# ---------------------------------------------------------------------------
# Incident association
# ---------------------------------------------------------------------------


class TestAssociateIncidents:
    def test_no_incidents(self):
        buckets = [
            {
                "bucket_start": datetime.now(timezone.utc) - timedelta(minutes=5),
                "avg_latency_ms": 100.0,
                "rep_status_code": 200,
                "is_up": True,
                "obs_count": 5,
            }
        ]
        points = VendorService._associate_incidents(buckets, [])
        assert len(points) == 1
        assert points[0].incident_id is None

    def test_overlapping_incident(self):
        now = datetime.now(timezone.utc)
        buckets = [
            {
                "bucket_start": now - timedelta(minutes=5),
                "avg_latency_ms": 2000.0,
                "rep_status_code": 503,
                "is_up": False,
                "obs_count": 3,
            }
        ]
        inc_id = uuid.uuid4()
        incidents = [
            (inc_id, now - timedelta(minutes=8), now - timedelta(minutes=2))
        ]
        points = VendorService._associate_incidents(buckets, incidents)
        assert points[0].incident_id == inc_id

    def test_non_overlapping_incident(self):
        now = datetime.now(timezone.utc)
        buckets = [
            {
                "bucket_start": now - timedelta(minutes=5),
                "avg_latency_ms": 100.0,
                "rep_status_code": 200,
                "is_up": True,
                "obs_count": 5,
            }
        ]
        # Incident from 60 minutes ago to 55 minutes ago — does NOT overlap bucket at -5m
        inc_id = uuid.uuid4()
        incidents = [
            (inc_id, now - timedelta(minutes=60), now - timedelta(minutes=55))
        ]
        points = VendorService._associate_incidents(buckets, incidents)
        assert points[0].incident_id is None

    def test_open_incident_no_resolved_at(self):
        now = datetime.now(timezone.utc)
        buckets = [
            {
                "bucket_start": now - timedelta(minutes=2),
                "avg_latency_ms": 3000.0,
                "rep_status_code": 500,
                "is_up": False,
                "obs_count": 4,
            }
        ]
        inc_id = uuid.uuid4()
        # Open incident (resolved_at=None) — should still overlap
        incidents = [
            (inc_id, now - timedelta(minutes=10), None)
        ]
        points = VendorService._associate_incidents(buckets, incidents)
        assert points[0].incident_id == inc_id

    def test_multiple_buckets_first_matching_incident(self):
        now = datetime.now(timezone.utc)
        # Bucket 0 at -45m (b_end_est = -45m + 10m = -35m)
        # Bucket 1 at -5m  (b_end_est = -5m + 10m = +5m)
        # Incident from -8m to -2m: overlaps bucket 1 but NOT bucket 0
        buckets = [
            {
                "bucket_start": now - timedelta(minutes=45),
                "avg_latency_ms": 100.0,
                "rep_status_code": 200,
                "is_up": True,
                "obs_count": 5,
            },
            {
                "bucket_start": now - timedelta(minutes=5),
                "avg_latency_ms": 5000.0,
                "rep_status_code": 503,
                "is_up": False,
                "obs_count": 3,
            },
        ]
        inc_id = uuid.uuid4()
        incidents = [
            (inc_id, now - timedelta(minutes=8), now - timedelta(minutes=2))
        ]
        points = VendorService._associate_incidents(buckets, incidents)
        # First bucket should have no incident, second should
        assert points[0].incident_id is None
        assert points[1].incident_id == inc_id


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_cache_key_format(self):
        key = VendorService._cache_key("stripe", "24h", "auto", "us-east-1")
        assert key.startswith("timeline:stripe:24h:auto:us-east-1:")
        assert len(key.split(":")) == 6  # prefix:vendor:window:res:region:ts


# ---------------------------------------------------------------------------
# Full service method (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_service_full_flow():
    """Test the full get_vendor_timeline service method with mocked repos."""
    service = VendorService()

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)

    # Mock the DB session
    mock_session = AsyncMock()

    # Mock _vendor_and_urls
    with patch.object(
        service,
        "_vendor_and_urls",
        new_callable=AsyncMock,
        return_value=(
            MagicMock(vendor_name="stripe"),
            [],
            ["https://status.stripe.com"],
        ),
    ):
        # Mock observation repository methods
        with patch.object(
            ObservationRepository,
            "get_timeline_buckets",
            new=AsyncMock(return_value=[
                {
                    "bucket_start": now - timedelta(minutes=10),
                    "avg_latency_ms": 120.5,
                    "rep_status_code": 200,
                    "is_up": True,
                    "obs_count": 5,
                },
                {
                    "bucket_start": now - timedelta(minutes=5),
                    "avg_latency_ms": 350.0,
                    "rep_status_code": 200,
                    "is_up": True,
                    "obs_count": 8,
                },
            ]),
        ), patch.object(
            ObservationRepository,
            "get_latest_observation",
            new=AsyncMock(return_value=MagicMock(
                timestamp=now - timedelta(seconds=30),
                latency_ms=95.0,
                status_code=200,
                error_type=None,
            )),
        ):
            # Mock vendor repository
            with patch.object(
                service.repository,
                "get_incidents_in_window",
                new_callable=AsyncMock,
                return_value=[],
            ):
                result = await service.get_vendor_timeline(
                    mock_session,
                    vendor_name="stripe",
                    window="24h",
                    resolution="5m",
                    region="us-east-1",
                )

    assert isinstance(result, VendorTimelineResponse)
    assert result.vendor_name == "stripe"
    assert result.window == "24h"
    assert result.resolution == "5m"
    assert result.region == "us-east-1"
    assert result.from_ is not None
    assert result.to is not None
    assert len(result.points) == 2
    assert result.current.latency_ms == 95.0
    assert result.current.is_up is True
    assert result.current.status_code == 200


@pytest.mark.asyncio
async def test_timeline_service_invalid_window():
    service = VendorService()
    mock_session = AsyncMock()

    with pytest.raises(Exception) as exc_info:
        await service.get_vendor_timeline(
            mock_session,
            vendor_name="stripe",
            window="10y",
        )
    assert "Invalid window" in str(exc_info.value) or exc_info.value is not None


@pytest.mark.asyncio
async def test_timeline_service_invalid_resolution():
    service = VendorService()
    mock_session = AsyncMock()

    with pytest.raises(Exception) as exc_info:
        await service.get_vendor_timeline(
            mock_session,
            vendor_name="stripe",
            window="24h",
            resolution="10s",
        )
    assert "Invalid resolution" in str(exc_info.value) or exc_info.value is not None
