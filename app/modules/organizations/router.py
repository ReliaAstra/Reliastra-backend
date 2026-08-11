import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import (
    get_current_org,
    get_current_user,
    require_admin,
    require_owner,
)
from app.db.session import get_db
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationMemberInviteRequest,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.modules.organizations.service import OrganizationService, org_service
from app.modules.users.models import User

router = APIRouter(prefix="/v1/orgs", tags=["Organizations"])


def get_org_service() -> OrganizationService:
    return org_service


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: OrganizationService = Depends(get_org_service),
) -> list[OrganizationResponse]:
    return await service.list_my_orgs(db, current_user.id)


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.create_org(db, current_user.id, request)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.get_org(db, org_id)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_admin)],
)
async def update_organization(
    org_id: uuid.UUID,
    request: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.update_org(db, org_id, request)


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_organization_members(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> list[OrganizationMemberResponse]:
    return await service.list_members(db, org_id)


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def invite_organization_member(
    org_id: uuid.UUID,
    request: OrganizationMemberInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationMemberResponse:
    return await service.invite_member(db, org_id, request)


@router.patch(
    "/{org_id}/members/{member_id}",
    response_model=OrganizationMemberResponse,
    dependencies=[Depends(require_owner)],
)
async def change_organization_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    request: OrganizationMemberRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationMemberResponse:
    return await service.change_member_role(db, org_id, member_id, request)


@router.delete(
    "/{org_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def remove_organization_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> None:
    await service.remove_member(db, org_id, member_id)
