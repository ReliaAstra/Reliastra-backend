import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.modules.observations.constants import ErrorType, ObservationSourceType
from app.modules.observations.models import Observation
from app.modules.observations.repository import ObservationRepository
from app.modules.observations.schemas import ObservationCreate, ObservationResponse

logger = logging.getLogger(__name__)


class ObservationService:
    def __init__(
        self, repository: ObservationRepository = ObservationRepository()
    ) -> None:
        self.repository = repository

    async def record(
        self, session: AsyncSession, request: ObservationCreate
    ) -> ObservationResponse:
        obs = await self.repository.create(
            session=session,
            source_type=request.source_type.value,
            source_id=request.source_id,
            org_id=request.org_id,
            region=request.region,
            endpoint_url=request.endpoint_url,
            latency_ms=request.latency_ms,
            status_code=request.status_code,
            response_time_ms=request.response_time_ms,
            tls_version=request.tls_version,
            tls_certificate_issuer=request.tls_certificate_issuer,
            tls_certificate_expiry=request.tls_certificate_expiry,
            error_type=request.error_type.value,
            error_message=request.error_message,
            extra_data=request.extra_data,
        )
        return ObservationResponse.model_validate(obs)

    async def get(self, session: AsyncSession, obs_id: uuid.UUID) -> ObservationResponse:
        obs = await self.repository.get_by_id(session, obs_id)
        if not obs:
            raise ResourceNotFoundException("Observation not found")
        return ObservationResponse.model_validate(obs)

    async def list_for_dependency(
        self,
        session: AsyncSession,
        dependency_id: uuid.UUID,
        limit: int = 50,
        hours: int | None = None,
    ) -> list[ObservationResponse]:
        since = None
        if hours:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
        observations = await self.repository.list_for_dependency(
            session, dependency_id, limit=limit, since=since
        )
        return [ObservationResponse.model_validate(o) for o in observations]


observation_service = ObservationService()
