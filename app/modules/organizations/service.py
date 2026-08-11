"""Organization lifecycle and membership policy."""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.modules.organizations.constants import MemberRole
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    MemberInviteRequest,
    MemberResponse,
    MemberRoleUpdateRequest,
    MembershipDTO,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.modules.users.service import UserService


class OrganizationService:
    def __init__(self, repository: OrganizationRepository, users: UserService) -> None:
        self.repository = repository
        self.users = users

    async def create_personal(
        self, user_id: UUID, full_name: str, email: str
    ) -> OrganizationResponse:
        name = f"{full_name}'s Organization"
        slug = await self.repository.unique_slug(full_name)
        model = await self.repository.create(
            {"name": name, "slug": slug, "billing_email": email}, user_id
        )
        return OrganizationResponse.model_validate(model)

    async def create(
        self, user_id: UUID, request: OrganizationCreateRequest
    ) -> OrganizationResponse:
        values = request.model_dump(exclude_none=True)
        values["slug"] = await self.repository.unique_slug(request.slug or request.name)
        return OrganizationResponse.model_validate(await self.repository.create(values, user_id))

    async def list_for_user(self, user_id: UUID) -> list[OrganizationResponse]:
        return [
            OrganizationResponse.model_validate(item)
            for item in await self.repository.list_for_user(user_id)
        ]

    async def get(self, org_id: UUID) -> OrganizationResponse:
        model = await self.repository.get(org_id)
        if model is None:
            raise NotFoundError("Organization not found")
        return OrganizationResponse.model_validate(model)

    async def update(
        self, org_id: UUID, request: OrganizationUpdateRequest
    ) -> OrganizationResponse:
        model = await self.repository.get(org_id)
        if model is None:
            raise NotFoundError("Organization not found")
        values = request.model_dump(exclude_unset=True)
        return OrganizationResponse.model_validate(await self.repository.update(model, values))

    async def membership(self, org_id: UUID, user_id: UUID) -> MembershipDTO | None:
        model = await self.repository.membership(org_id, user_id)
        return MembershipDTO.model_validate(model, from_attributes=True) if model else None

    async def list_members(self, org_id: UUID) -> list[MemberResponse]:
        members = await self.repository.list_members(org_id)
        result: list[MemberResponse] = []
        for member in members:
            user = await self.users.get(member.user_id)
            result.append(
                MemberResponse(
                    id=member.id,
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=member.role,
                    joined_at=member.joined_at,
                )
            )
        return result

    async def invite(self, org_id: UUID, request: MemberInviteRequest) -> MemberResponse:
        user = await self.users.auth_record(str(request.email))
        if user is None:
            raise NotFoundError("The invited user must register before being added")
        if await self.repository.membership(org_id, user.id):
            raise ConflictError("User is already an organization member")
        member = await self.repository.add_member(org_id, user.id, request.role)
        return MemberResponse(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            joined_at=member.joined_at,
        )

    async def change_role(
        self, org_id: UUID, member_id: UUID, request: MemberRoleUpdateRequest
    ) -> MemberResponse:
        member = await self.repository.get_member(org_id, member_id)
        if member is None:
            raise NotFoundError("Organization member not found")
        if member.role == MemberRole.OWNER and request.role != MemberRole.OWNER:
            owners = [m for m in await self.list_members(org_id) if m.role == MemberRole.OWNER]
            if len(owners) == 1:
                raise ConflictError("An organization must have at least one owner")
        await self.repository.update(member, {"role": request.role})
        user = await self.users.get(member.user_id)
        return MemberResponse(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            joined_at=member.joined_at,
        )

    async def remove(self, org_id: UUID, member_id: UUID, actor_id: UUID) -> None:
        member = await self.repository.get_member(org_id, member_id)
        if member is None:
            raise NotFoundError("Organization member not found")
        if member.user_id == actor_id:
            raise ForbiddenError("Use an ownership transfer flow before removing yourself")
        if member.role == MemberRole.OWNER:
            raise ForbiddenError("Owners cannot be removed")
        await self.repository.remove_member(member)
