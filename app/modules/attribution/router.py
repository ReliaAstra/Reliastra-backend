import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.attribution.schemas import AttributionResultResponse
from app.modules.attribution.service import AttributionService, attribution_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1", tags=["Attribution"])


def get_attribution_service() -> AttributionService:
    return attribution_service


@router.post(
    "/orgs/{org_id}/incidents/{incident_id}/attribution",
    response_model=AttributionResultResponse,
    dependencies=[Depends(require_member)],
)
async def compute_incident_attribution(
    org_id: uuid.UUID,
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AttributionService = Depends(get_attribution_service),
) -> AttributionResultResponse:
    return await service.compute_for_incident(db, incident_id)


@router.get(
    "/orgs/{org_id}/incidents/{incident_id}/attribution",
    response_model=AttributionResultResponse,
    dependencies=[Depends(require_member)],
)
async def get_incident_attribution(
    org_id: uuid.UUID,
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AttributionService = Depends(get_attribution_service),
) -> AttributionResultResponse:
    return await service.get_for_incident(db, incident_id)


@router.get(
    "/attributions/{attribution_id}",
    response_model=AttributionResultResponse,
    dependencies=[Depends(get_current_org)],
)
async def get_attribution(
    attribution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AttributionService = Depends(get_attribution_service),
) -> AttributionResultResponse:
    return await service.get(db, attribution_id)
