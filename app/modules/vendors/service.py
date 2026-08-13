import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.modules.checks.repository import CheckRepository
from app.modules.observations.repository import ObservationRepository
from app.modules.vendors.constants import SEED_VENDORS
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import (
    VendorDetailResponse,
    VendorEndpointResponse,
    VendorHistoryResponse,
    VendorIncidentResponse,
    VendorIncidentsResponse,
    VendorMetricsResponse,
    VendorResponse,
    VendorWindowMetrics,
)

logger = logging.getLogger(__name__)

_WINDOW_HOURS = {"1h": 1, "24h": 24, "7d": 168, "30d": 720, "90d": 2160}


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


vendor_service = VendorService()
