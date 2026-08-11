"""Organization and membership routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.permissions import Role
from app.dependencies import (
    OrgContext,
    Principal,
    get_current_principal,
    get_org_service,
    org_context,
)
from app.modules.organizations.schemas import (
    MemberInviteRequest,
    MemberResponse,
    MemberRoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.modules.organizations.service import OrganizationService

router = APIRouter(prefix="/v1/orgs", tags=["organizations"])


@router.get("/", response_model=list[OrganizationResponse])
async def list_orgs(
    principal: Principal = Depends(get_current_principal),
    service: OrganizationService = Depends(get_org_service),
) -> list[OrganizationResponse]:
    return await service.list_for_user(principal.require_user_id())


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_org(
    payload: OrganizationCreateRequest,
    principal: Principal = Depends(get_current_principal),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.create(principal.require_user_id(), payload)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_org(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.get(org_id)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_org(
    org_id: UUID,
    payload: OrganizationUpdateRequest,
    _context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: OrganizationService = Depends(get_org_service),
) -> OrganizationResponse:
    return await service.update(org_id, payload)


@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: OrganizationService = Depends(get_org_service),
) -> list[MemberResponse]:
    return await service.list_members(org_id)


@router.post("/{org_id}/members", response_model=MemberResponse, status_code=201)
async def invite_member(
    org_id: UUID,
    payload: MemberInviteRequest,
    _context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: OrganizationService = Depends(get_org_service),
) -> MemberResponse:
    return await service.invite(org_id, payload)


@router.patch("/{org_id}/members/{member_id}", response_model=MemberResponse)
async def update_member(
    org_id: UUID,
    member_id: UUID,
    payload: MemberRoleUpdateRequest,
    _context: OrgContext = Depends(org_context(Role.OWNER)),
    service: OrganizationService = Depends(get_org_service),
) -> MemberResponse:
    return await service.change_role(org_id, member_id, payload)


@router.delete("/{org_id}/members/{member_id}", status_code=204)
async def delete_member(
    org_id: UUID,
    member_id: UUID,
    context: OrgContext = Depends(org_context(Role.ADMIN)),
    service: OrganizationService = Depends(get_org_service),
) -> Response:
    await service.remove(org_id, member_id, context.principal.require_user_id())
    return Response(status_code=204)
