import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.organizations.agency_schemas import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
    ClientCreateRequest,
    ClientResponse,
    ClientUpdateRequest,
)
from app.modules.organizations.agency_service import AgencyService, agency_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}", tags=["Agency Management"])


def get_agency_service() -> AgencyService:
    return agency_service


@router.get(
    "/clients",
    response_model=list[ClientResponse],
    dependencies=[Depends(require_member)],
)
async def list_clients(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> list[ClientResponse]:
    return await service.list_clients(db, org_id)


@router.post(
    "/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_client(
    org_id: uuid.UUID,
    request: ClientCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ClientResponse:
    return await service.create_client(db, org_id, request)


@router.get(
    "/clients/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_member)],
)
async def get_client(
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ClientResponse:
    return await service.get_client(db, org_id, client_id)


@router.patch(
    "/clients/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_member)],
)
async def update_client(
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    request: ClientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ClientResponse:
    return await service.update_client(db, org_id, client_id, request)


@router.delete(
    "/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_member)],
)
async def delete_client(
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> None:
    await service.delete_client(db, org_id, client_id)


@router.get(
    "/clients/{client_id}/applications",
    response_model=list[ApplicationResponse],
    dependencies=[Depends(require_member)],
)
async def list_client_applications(
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> list[ApplicationResponse]:
    return await service.list_applications(db, org_id, client_id=client_id)


@router.post(
    "/clients/{client_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_client_application(
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    request: ApplicationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ApplicationResponse:
    request.client_id = client_id
    return await service.create_application(db, org_id, request)


@router.get(
    "/applications",
    response_model=list[ApplicationResponse],
    dependencies=[Depends(require_member)],
)
async def list_org_applications(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> list[ApplicationResponse]:
    return await service.list_applications(db, org_id)


@router.patch(
    "/applications/{app_id}",
    response_model=ApplicationResponse,
    dependencies=[Depends(require_member)],
)
async def update_application(
    org_id: uuid.UUID,
    app_id: uuid.UUID,
    request: ApplicationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> ApplicationResponse:
    return await service.update_application(db, org_id, app_id, request)


@router.delete(
    "/applications/{app_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_member)],
)
async def delete_application(
    org_id: uuid.UUID,
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AgencyService = Depends(get_agency_service),
) -> None:
    await service.delete_application(db, org_id, app_id)
