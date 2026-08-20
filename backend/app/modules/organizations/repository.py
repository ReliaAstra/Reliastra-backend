import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.organizations.models import Organization, OrganizationMember


class OrganizationRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, org_id: uuid.UUID
    ) -> Organization | None:
        query = select(Organization).where(Organization.id == org_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(
        session: AsyncSession, slug: str
    ) -> Organization | None:
        query = select(Organization).where(Organization.slug == slug.lower())
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> list[Organization]:
        query = (
            select(Organization)
            .join(
                OrganizationMember,
                OrganizationMember.org_id == Organization.id,
            )
            .where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_deleted == False,  # noqa: E712
            )
            .order_by(Organization.created_at.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        slug: str,
        plan: str = "free",
    ) -> Organization:
        org = Organization(
            name=name,
            slug=slug.lower(),
            plan=plan,
        )
        session.add(org)
        await session.flush()
        return org

    @staticmethod
    async def update(
        session: AsyncSession, org: Organization, **kwargs: Any
    ) -> Organization:
        for key, value in kwargs.items():
            if value is not None and hasattr(org, key):
                setattr(org, key, value)
        session.add(org)
        await session.flush()
        return org

    @staticmethod
    async def get_member(
        session: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> OrganizationMember | None:
        query = select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
        )
        if not include_deleted:
            query = query.where(OrganizationMember.is_deleted == False)  # noqa: E712
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_member_by_id(
        session: AsyncSession,
        member_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> OrganizationMember | None:
        query = select(OrganizationMember).where(
            OrganizationMember.id == member_id
        )
        if not include_deleted:
            query = query.where(OrganizationMember.is_deleted == False)  # noqa: E712
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_members(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int | None = None,
        cursor: uuid.UUID | None = None,
    ) -> list[OrganizationMember]:
        query = (
            select(OrganizationMember)
            .where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.is_deleted == False,  # noqa: E712
            )
            .order_by(
                OrganizationMember.joined_at.asc(),
                OrganizationMember.id.asc(),
            )
        )
        if cursor:
            cursor_member = await session.get(OrganizationMember, cursor)
            if cursor_member is not None:
                query = query.where(
                    (OrganizationMember.joined_at > cursor_member.joined_at)
                    | (
                        (OrganizationMember.joined_at == cursor_member.joined_at)
                        & (OrganizationMember.id > cursor_member.id)
                    )
                )
        if limit is not None:
            query = query.limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def add_member(
        session: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
    ) -> OrganizationMember:
        member = OrganizationMember(
            org_id=org_id,
            user_id=user_id,
            role=role,
        )
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def update_member_role(
        session: AsyncSession, member: OrganizationMember, role: str
    ) -> OrganizationMember:
        member.role = role
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def restore_member(
        session: AsyncSession, member: OrganizationMember, role: str
    ) -> OrganizationMember:
        member.is_deleted = False
        member.deleted_at = None
        member.role = role
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def remove_member(
        session: AsyncSession, member: OrganizationMember
    ) -> None:
        member.is_deleted = True
        member.deleted_at = datetime.now(timezone.utc)
        session.add(member)
        await session.flush()
