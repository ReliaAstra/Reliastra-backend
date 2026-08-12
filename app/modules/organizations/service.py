import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationMemberInviteRequest,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.modules.users.repository import UserRepository


class OrganizationService:
    def __init__(
        self,
        org_repository: OrganizationRepository = OrganizationRepository(),
        user_repository: UserRepository = UserRepository(),
    ) -> None:
        self.org_repository = org_repository
        self.user_repository = user_repository

    async def list_my_orgs(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[OrganizationResponse]:
        orgs = await self.org_repository.list_for_user(session, user_id)
        return [OrganizationResponse.model_validate(org) for org in orgs]

    async def create_org(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        request: OrganizationCreateRequest,
    ) -> OrganizationResponse:
        slug = request.slug
        if not slug:
            slug = re.sub(r"[^a-z0-9-]+", "-", request.name.lower()).strip("-")
            if not slug:
                slug = f"org-{uuid.uuid4().hex[:8]}"

        existing = await self.org_repository.get_by_slug(session, slug)
        if existing:
            raise ConflictException(f"Organization slug '{slug}' is already in use")

        org = await self.org_repository.create(
            session,
            name=request.name,
            slug=slug,
            plan="free",
        )
        await self.org_repository.add_member(
            session,
            org_id=org.id,
            user_id=user_id,
            role=Role.OWNER.value,
        )
        return OrganizationResponse.model_validate(org)

    async def get_org(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> OrganizationResponse:
        org = await self.org_repository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        return OrganizationResponse.model_validate(org)

    async def update_org(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: OrganizationUpdateRequest,
    ) -> OrganizationResponse:
        org = await self.org_repository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        update_kwargs = {}
        if request.name is not None:
            update_kwargs["name"] = request.name
        if request.plan is not None:
            update_kwargs["plan"] = request.plan.value

        updated = await self.org_repository.update(session, org, **update_kwargs)
        return OrganizationResponse.model_validate(updated)

    async def list_members(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[OrganizationMemberResponse]:
        members = await self.org_repository.list_members(session, org_id)
        return [OrganizationMemberResponse.model_validate(m) for m in members]

    async def invite_member(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: OrganizationMemberInviteRequest,
    ) -> OrganizationMemberResponse:
        user = await self.user_repository.get_by_email(session, request.email)
        if not user:
            raise ResourceNotFoundException(
                f"User with email '{request.email}' not found"
            )

        existing_member = await self.org_repository.get_member(
            session, org_id, user.id
        )
        if existing_member:
            raise ConflictException("User is already a member of this organization")

        member = await self.org_repository.add_member(
            session,
            org_id=org_id,
            user_id=user.id,
            role=request.role.value,
        )
        return OrganizationMemberResponse.model_validate(member)

    async def change_member_role(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        request: OrganizationMemberRoleUpdateRequest,
    ) -> OrganizationMemberResponse:
        member = await self.org_repository.get_member_by_id(session, member_id)
        if not member or member.org_id != org_id:
            raise ResourceNotFoundException("Organization member not found")

        updated_member = await self.org_repository.update_member_role(
            session, member, request.role.value
        )
        return OrganizationMemberResponse.model_validate(updated_member)

    async def remove_member(
        self, session: AsyncSession, org_id: uuid.UUID, member_id: uuid.UUID
    ) -> None:
        member = await self.org_repository.get_member_by_id(session, member_id)
        if not member or member.org_id != org_id:
            raise ResourceNotFoundException("Organization member not found")

        # Prevent removing the last owner of the organization
        if member.role == Role.OWNER.value:
            members = await self.org_repository.list_members(session, org_id)
            owners = [m for m in members if m.role == Role.OWNER.value]
            if len(owners) <= 1:
                raise ForbiddenException(
                    "Cannot remove the last owner of the organization. "
                    "Transfer ownership to another member first."
                )

        await self.org_repository.remove_member(session, member)


org_service = OrganizationService()
