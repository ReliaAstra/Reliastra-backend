import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observations.repository import ObservationRepository
from app.modules.observations.schemas import (
    ObservationCreateDTO,
    ObservationResponse,
    ObservationSummaryResponse,
)


class ObservationService:
    def __init__(
        self, repository: ObservationRepository = ObservationRepository()
    ) -> None:
        self.repository = repository

    async def record_observation(
        self, session: AsyncSession, dto: ObservationCreateDTO
    ) -> ObservationResponse:
        observation = await self.repository.create(session, dto)
        return ObservationResponse.model_validate(observation)

    async def list_observations(
        self,
        session: AsyncSession,
        source_id: uuid.UUID,
        limit: int = 50,
        hours: int | None = None,
    ) -> list[ObservationResponse]:
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
            if hours
            else None
        )
        observations = await self.repository.list_for_source(
            session, source_id, limit=limit, since=since
        )
        return [ObservationResponse.model_validate(item) for item in observations]

    async def get_summary(
        self,
        session: AsyncSession,
        source_id: uuid.UUID,
        hours: int = 24,
    ) -> ObservationSummaryResponse:
        stats = await self.repository.get_aggregated_stats(
            session, source_id, hours
        )
        return ObservationSummaryResponse(
            source_type=stats["source_type"],
            source_id=source_id,
            endpoint_url=stats["endpoint_url"],
            total_observations=stats["total"],
            uptime_percentage=stats["uptime_pct"],
            avg_latency_ms=stats["avg_latency"],
            p95_latency_ms=stats["p95"],
            period_hours=hours,
        )


observation_service = ObservationService()
