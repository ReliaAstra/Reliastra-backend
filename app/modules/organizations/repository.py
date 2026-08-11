"""Tenant and membership persistence."""

from __future__ import annotations

import re
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.constants import MemberRole
from app.modules.organizations.models import Organization, OrganizationMember


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def unique_slug(self, requested: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", requested.lower()).strip("-")[:90] or "organization"
        candidate = base
        suffix = 1
        while await self.session.scalar(
            select(Organization.id).where(Organization.slug == candidate)
        ):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    async def create(self, values: dict[str, object], owner_id: UUID) -> Organization:
        organization = Organization(**values)
        self.session.add(organization)
        await self.session.flush()
        self.session.add(
            OrganizationMember(org_id=organization.id, user_id=owner_id, role=MemberRole.OWNER)
        )
        await self.session.flush()
        return organization

    async def get(self, org_id: UUID) -> Organization | None:
        return await self.session.get(Organization, org_id)

    async def list_for_user(self, user_id: UUID) -> list[Organization]:
        statement = (
            select(Organization)
            .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at)
        )
        return list((await self.session.scalars(statement)).all())

    async def membership(self, org_id: UUID, user_id: UUID) -> OrganizationMember | None:
        return cast(
            OrganizationMember | None,
            await self.session.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.org_id == org_id, OrganizationMember.user_id == user_id
                )
            ),
        )

    async def list_members(self, org_id: UUID) -> list[OrganizationMember]:
        statement = (
            select(OrganizationMember)
            .where(OrganizationMember.org_id == org_id)
            .order_by(OrganizationMember.joined_at)
        )
        return list((await self.session.scalars(statement)).all())

    async def add_member(self, org_id: UUID, user_id: UUID, role: MemberRole) -> OrganizationMember:
        member = OrganizationMember(org_id=org_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_member(self, org_id: UUID, member_id: UUID) -> OrganizationMember | None:
        return cast(
            OrganizationMember | None,
            await self.session.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.org_id == org_id, OrganizationMember.id == member_id
                )
            ),
        )

    async def update(
        self, model: Organization | OrganizationMember, values: dict[str, object]
    ) -> Organization | OrganizationMember:
        for field, value in values.items():
            setattr(model, field, value)
        await self.session.flush()
        return model

    async def remove_member(self, member: OrganizationMember) -> None:
        await self.session.delete(member)
        await self.session.flush()
