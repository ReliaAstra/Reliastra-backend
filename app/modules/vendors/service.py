import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.modules.checks.repository import CheckRepository
from app.modules.observations.repository import ObservationRepository
from app.modules.vendors.constants import SEED_VENDORS
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import (
    TimelineBucket,
    TimelineCurrent,
    VendorDetailResponse,
    VendorEndpointResponse,
    VendorHistoryResponse,
    VendorIncidentResponse,
    VendorIncidentsResponse,
    VendorMetricsResponse,
    VendorResponse,
    VendorTimelineResponse,
    VendorWindowMetrics,
)

logger = logging.getLogger(__name__)

_WINDOW_HOURS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720, "90d": 2160}

# Default resolution (seconds) when resolution=auto
_AUTO_RESOLUTION: dict[str, int] = {
    "1h": 60,       # 1 minute
    "6h": 60,       # 1 minute
    "24h": 300,     # 5 minutes
    "7d": 900,      # 15 minutes
    "30d": 3600,    # 1 hour
    "90d": 21600,   # 6 hours
}

_RESOLUTION_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
}

# Cache TTL (seconds) keyed by window — shorter for recent data
_CACHE_TTL: dict[str, int] = {
    "1h": 10,
    "6h": 15,
    "24h": 30,
    "7d": 120,
    "30d": 300,
    "90d": 600,
}

_DEFAULT_REGION = "us-east-1"


class VendorService:
    def __init__(
        self, repository: VendorRepository = VendorRepository()
    ) -> None:
        self.repository = repository

    async def seed_vendors(self, session: AsyncSession) -> int:
        seeded_count = 0
        for item in SEED_VENDORS:
            existing = await self.repository.get_by_name(
                session, item["vendor_name"]
            )
            if not existing:
                await self.repository.create(
                    session=session,
                    vendor_name=item["vendor_name"],
                    display_name=item["display_name"],
                    endpoint_url=item["endpoint_url"],
                    category=item["category"],
                )
                seeded_count += 1
        return seeded_count

    async def list_public_vendors(
        self, session: AsyncSession
    ) -> list[VendorResponse]:
        vendors = await self.repository.list_public(session)
        return [VendorResponse.model_validate(vendor) for vendor in vendors]

    async def _vendor_and_urls(self, session: AsyncSession, vendor_name: str):
        vendor = await self.repository.get_by_name(session, vendor_name)
        if not vendor or not vendor.is_public:
            raise ResourceNotFoundException(
                f"Vendor '{vendor_name}' not found"
            )
        endpoints = await self.repository.list_vendor_endpoints(
            session, vendor.vendor_name
        )
        urls = list(
            dict.fromkeys(
                [vendor.endpoint_url]
                + [endpoint.endpoint_url for endpoint in endpoints]
            )
        )
        return vendor, endpoints, urls

    async def get_vendor_detail(
        self, session: AsyncSession, vendor_name: str
    ) -> VendorDetailResponse:
        vendor, endpoints, urls = await self._vendor_and_urls(
            session, vendor_name
        )
        data = VendorResponse.model_validate(vendor).model_dump()
        observations = await ObservationRepository.list_for_endpoints(
            session, urls, limit=5
        )
        if observations:
            data["recent_status"] = (
                "degraded"
                if any(item.error_type or item.status_code is None for item in observations)
                else "operational"
            )
        else:
            # During dual-write rollout, preserve status visibility for legacy rows.
            legacy = await CheckRepository.get_vendor_recent_status(
                session, vendor.endpoint_url, limit=5
            )
            data["recent_status"] = (
                "operational"
                if legacy and all(item.is_up for item in legacy)
                else "degraded" if legacy else "unknown"
            )
        data["endpoints"] = [
            VendorEndpointResponse.model_validate(endpoint)
            for endpoint in endpoints
        ]
        return VendorDetailResponse.model_validate(data)

    async def get_vendor_history(
        self, session: AsyncSession, vendor_name: str
    ) -> VendorHistoryResponse:
        vendor, _, urls = await self._vendor_and_urls(session, vendor_name)
        stats = await ObservationRepository.get_endpoint_stats(
            session, urls, window_hours=24
        )
        if stats["total"] == 0:
            legacy = await CheckRepository.get_vendor_aggregated_stats(
                session, vendor.endpoint_url, window_hours=24
            )
            return VendorHistoryResponse(
                vendor_name=vendor.vendor_name,
                uptime_percentage_24h=legacy["uptime_percentage"],
                avg_latency_ms_24h=legacy["avg_latency_ms"],
                recent_checks_count=legacy["total_checks"],
            )
        return VendorHistoryResponse(
            vendor_name=vendor.vendor_name,
            uptime_percentage_24h=stats["uptime_percentage"],
            avg_latency_ms_24h=stats["avg_latency_ms"],
            recent_checks_count=stats["total"],
        )

    async def get_vendor_metrics(
        self,
        session: AsyncSession,
        vendor_name: str,
        window: str | None = None,
    ) -> VendorMetricsResponse:
        vendor, _, urls = await self._vendor_and_urls(session, vendor_name)
        if window and window not in _WINDOW_HOURS:
            raise ValidationException(
                f"Invalid window '{window}'. Expected one of: {', '.join(_WINDOW_HOURS)}"
            )
        windows = [window] if window else list(_WINDOW_HOURS)
        metrics: dict[str, VendorWindowMetrics] = {}
        for label in windows:
            stats = await ObservationRepository.get_endpoint_stats(
                session, urls, _WINDOW_HOURS[label]
            )
            metrics[label] = VendorWindowMetrics(
                window=label,
                total_observations=stats["total"],
                uptime_percentage=stats["uptime_percentage"],
                avg_latency_ms=stats["avg_latency_ms"],
                p95_latency_ms=stats["p95_latency_ms"],
            )
        return VendorMetricsResponse(
            vendor_name=vendor.vendor_name, metrics=metrics
        )

    async def get_vendor_incidents(
        self,
        session: AsyncSession,
        vendor_name: str,
        limit: int = 50,
    ) -> VendorIncidentsResponse:
        vendor, _, urls = await self._vendor_and_urls(session, vendor_name)
        rows = await self.repository.list_incidents_for_endpoints(
            session, urls, limit=limit
        )
        incidents = []
        now = datetime.now(timezone.utc)
        for incident, dependency in rows:
            end = incident.resolved_at or now
            duration = max(0.0, (end - incident.started_at).total_seconds())
            incidents.append(
                VendorIncidentResponse(
                    incident_id=incident.id,
                    dependency_name=dependency.name,
                    started_at=incident.started_at,
                    resolved_at=incident.resolved_at,
                    severity=incident.severity,
                    status=incident.status,
                    duration_seconds=round(duration, 2),
                )
            )
        return VendorIncidentsResponse(
            vendor_name=vendor.vendor_name, incidents=incidents
        )

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    async def get_vendor_timeline(
        self,
        session: AsyncSession,
        vendor_name: str,
        window: str = "24h",
        resolution: str = "auto",
        region: str | None = None,
    ) -> VendorTimelineResponse:
        """Build the aggregated timeline for a public vendor.

        Steps:
        1. Validate window / resolution parameters.
        2. Check Redis cache; return cached response if fresh.
        3. Fetch aggregated buckets from PostgreSQL.
        4. Fetch overlapping incidents.
        5. Build current observation snapshot.
        6. Assemble response and cache it.
        """
        # --- 1. Validate ------------------------------------------------
        if window not in _WINDOW_HOURS:
            raise ValidationException(
                f"Invalid window '{window}'. "
                f"Supported: {', '.join(_WINDOW_HOURS)}"
            )

        if resolution != "auto" and resolution not in _RESOLUTION_SECONDS:
            raise ValidationException(
                f"Invalid resolution '{resolution}'. "
                f"Supported: auto, {', '.join(_RESOLUTION_SECONDS)}"
            )

        resolved_region = region or _DEFAULT_REGION

        vendor, _, urls = await self._vendor_and_urls(session, vendor_name)

        resolution_seconds = self._resolve_resolution(window, resolution)
        window_seconds = _WINDOW_HOURS[window] * 3600

        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=window_seconds)

        # --- 2. Cache check ---------------------------------------------
        cache_key = self._cache_key(
            vendor_name, window, resolution, resolved_region
        )
        cached = await self._get_cache(cache_key)
        if cached is not None:
            return cached

        # --- 3. Fetch aggregated buckets --------------------------------
        buckets = await ObservationRepository.get_timeline_buckets(
            session,
            endpoint_urls=urls,
            since=since,
            until=now,
            resolution_seconds=resolution_seconds,
            region=resolved_region,
        )

        # --- 4. Fetch overlapping incidents -------------------------------
        incidents = await self.repository.get_incidents_in_window(
            session, urls, since, now
        )

        # --- 5. Attach incident ids to buckets ---------------------------
        points = self._associate_incidents(buckets, incidents)

        # --- 6. Build current observation ---------------------------------
        latest = await ObservationRepository.get_latest_observation(
            session, urls, region=resolved_region
        )
        current = TimelineCurrent(
            timestamp=latest.timestamp if latest else None,
            latency_ms=round(latest.latency_ms, 2) if latest else None,
            status_code=latest.status_code if latest else None,
            is_up=(
                bool(latest.status_code is not None and latest.error_type is None)
                if latest
                else None
            ),
        )

        response = VendorTimelineResponse(
            vendor_name=vendor.vendor_name,
            window=window,
            resolution=resolution if resolution != "auto" else self._auto_label(window),
            region=resolved_region,
            from_=since,
            to=now,
            current=current,
            points=points,
        )

        # --- 7. Cache ---------------------------------------------------
        await self._set_cache(cache_key, response, _CACHE_TTL.get(window, 30))

        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_resolution(window: str, resolution: str) -> int:
        """Map ``resolution`` parameter to seconds."""
        if resolution == "auto":
            return _AUTO_RESOLUTION[window]
        return _RESOLUTION_SECONDS[resolution]

    @staticmethod
    def _auto_label(window: str) -> str:
        """Return a human-readable label for the auto-resolved resolution."""
        seconds = _AUTO_RESOLUTION[window]
        reverse = {v: k for k, v in _RESOLUTION_SECONDS.items()}
        return reverse.get(seconds, f"{seconds}s")

    @staticmethod
    def _associate_incidents(
        buckets: list[dict],
        incidents: list[tuple],
    ) -> list[TimelineBucket]:
        """Attach the first overlapping ``incident_id`` to each bucket.

        A bucket's time period is ``[bucket_start, bucket_start + resolution)``.
        An incident overlaps if its active period intersects this range.
        """
        if not incidents:
            return [
                TimelineBucket(
                    timestamp=b["bucket_start"],
                    avg_latency_ms=b["avg_latency_ms"],
                    status_code=b["rep_status_code"],
                    is_up=b["is_up"],
                    observation_count=b["obs_count"],
                    incident_id=None,
                )
                for b in buckets
            ]

        points: list[TimelineBucket] = []
        for b in buckets:
            incident_id = None
            b_start = b["bucket_start"]
            # Assume bucket duration = difference to next bucket, or 300s fallback
            # This is a safe upper bound for incident overlap check.
            b_end_est = b_start + timedelta(seconds=600)
            for inc_id, inc_start, inc_resolved in incidents:
                inc_end = inc_resolved or datetime.now(timezone.utc)
                # Overlap: intervals [b_start, b_end) and [inc_start, inc_end)
                if b_start < inc_end and inc_start < b_end_est:
                    incident_id = inc_id
                    break
            points.append(
                TimelineBucket(
                    timestamp=b["bucket_start"],
                    avg_latency_ms=b["avg_latency_ms"],
                    status_code=b["rep_status_code"],
                    is_up=b["is_up"],
                    observation_count=b["obs_count"],
                    incident_id=incident_id,
                )
            )
        return points

    @staticmethod
    def _cache_key(
        vendor_name: str, window: str, resolution: str, region: str
    ) -> str:
        ts_minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        return f"timeline:{vendor_name}:{window}:{resolution}:{region}:{ts_minute}"

    @staticmethod
    async def _get_cache(key: str) -> VendorTimelineResponse | None:
        """Fetch cached timeline from Redis. Returns None on any failure."""
        try:
            from app.infrastructure.redis_client import safe_redis_get

            raw = await safe_redis_get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            return VendorTimelineResponse.model_validate(data)
        except Exception:
            logger.debug("Timeline cache miss (parse error)", exc_info=True)
            return None

    @staticmethod
    async def _set_cache(
        key: str, response: VendorTimelineResponse, ttl: int
    ) -> None:
        """Cache timeline response in Redis. Silent failure."""
        try:
            from app.infrastructure.redis_client import safe_redis_set

            await safe_redis_set(key, response.model_dump_json(mode="json"), ex=ttl)
        except Exception:
            logger.debug("Timeline cache set failed", exc_info=True)


vendor_service = VendorService()
