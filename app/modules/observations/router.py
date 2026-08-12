import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.observations.schemas import (
    ObservationCreate,
    ObservationResponse,
)
from app.modules.observations.service import ObservationService, observation_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1", tags=["Observations"])


def get_obs_service() -> ObservationService:
    return observation_service


@router.get(
    "/orgs/{org_id}/dependencies/{dep_id}/observations",
    response_model=list[ObservationResponse],
    dependencies=[Depends(require_member)],
)
async def list_dependency_observations(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    hours: int | None = Query(default=None, ge=1, le=24 * 30),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: ObservationService = Depends(get_obs_service),
) -> list[ObservationResponse]:
    return await service.list_for_dependency(db, dep_id, limit=limit, hours=hours)


@router.get(
    "/observations/{obs_id}",
    response_model=ObservationResponse,
    dependencies=[Depends(get_current_org)],
)
async def get_observation(
    obs_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: ObservationService = Depends(get_obs_service),
) -> ObservationResponse:
    return await service.get(db, obs_id)
