import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.pagination import CursorPagination
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


@router.get("/current", response_model=OrganizationResponse)
async def get_organization(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.get_org(db, current_org.id)


@router.patch(
    "/current",
    response_model=OrganizationResponse,
    dependencies=[Depends(require_admin)],
)
async def update_organization(
    request: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.update_org(db, current_org.id, request)


@router.get(
    "/members",
    response_model=CursorPagination[OrganizationMemberResponse],
)
async def list_organization_members(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
    cursor: uuid.UUID | None = Query(
        default=None, description="Member id of the last item on the previous page"
    ),
    limit: int = Query(default=50, ge=1, le=100),
) -> CursorPagination[OrganizationMemberResponse]:
    return await service.list_members(db, current_org.id, limit=limit, cursor=cursor)


@router.post(
    "/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def invite_organization_member(
    request: OrganizationMemberInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationMemberResponse:
    return await service.invite_member(db, current_org.id, request)


@router.patch(
    "/members/{member_id}",
    response_model=OrganizationMemberResponse,
    dependencies=[Depends(require_owner)],
)
async def change_organization_member_role(
    member_id: uuid.UUID,
    request: OrganizationMemberRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationMemberResponse:
    return await service.change_member_role(db, current_org.id, member_id, request)


@router.delete(
    "/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def remove_organization_member(
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: OrganizationService = Depends(get_org_service),
) -> None:
    await service.remove_member(db, current_org.id, member_id)
