import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_org, require_admin
from app.modules.agencies.schemas import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ClientCreateRequest,
    ClientResponse,
)
from app.modules.agencies.service import AgencyService, agency_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1", tags=["Agency"])


def get_agency_service() -> AgencyService:
    return agency_service


@router.get("/clients", response_model=list[ClientResponse])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> list[ClientResponse]:
    return await service.list_clients(db, current_org.id)


@router.post(
    "/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_client(
    request: ClientCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ClientResponse:
    return await service.create_client(db, current_org.id, request)


@router.get(
    "/clients/{client_id}/applications",
    response_model=list[ApplicationResponse],
)
async def list_applications(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> list[ApplicationResponse]:
    return await service.list_applications(db, current_org.id, client_id)


@router.post(
    "/clients/{client_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_application(
    client_id: uuid.UUID,
    request: ApplicationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ApplicationResponse:
    return await service.create_application(db, current_org.id, client_id, request)
