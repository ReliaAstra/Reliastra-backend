from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.status_pages.models import StatusComponent, StatusPage


class StatusPageRepository:
    """Data access for StatusPage and StatusComponent models."""

    @staticmethod
    async def get_by_org_id(
        session: AsyncSession, org_id: uuid.UUID
    ) -> StatusPage | None:
        result = await session.execute(
            select(StatusPage).where(StatusPage.org_id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(
        session: AsyncSession, slug: str
    ) -> StatusPage | None:
        result = await session.execute(
            select(StatusPage).where(
                StatusPage.slug == slug,
                StatusPage.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        slug: str,
        title: str,
        show_uptime_graph: bool = True,
        show_incident_history: bool = True,
        branding: dict | None = None,
        allowed_domains: list[str] | None = None,
    ) -> StatusPage:
        page = StatusPage(
            org_id=org_id,
            slug=slug,
            title=title,
            show_uptime_graph=show_uptime_graph,
            show_incident_history=show_incident_history,
            branding=branding,
            allowed_domains=allowed_domains,
            is_active=True,
        )
        session.add(page)
        await session.flush()
        return page

    @staticmethod
    async def list_public_components(
        session: AsyncSession,
    ) -> list[StatusComponent]:
        result = await session.execute(
            select(StatusComponent)
            .where(StatusComponent.is_public.is_(True))
            .order_by(StatusComponent.order_index.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_component_by_name(
        session: AsyncSession, name: str
    ) -> StatusComponent | None:
        result = await session.execute(
            select(StatusComponent).where(StatusComponent.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_component(
        session: AsyncSession,
        name: str,
        display_name: str,
        status: str = "operational",
        description: str | None = None,
        order_index: int = 0,
        is_public: bool = True,
        uptime_30d: float = 100.0,
    ) -> StatusComponent:
        existing = await StatusPageRepository.get_component_by_name(session, name)
        if existing:
            existing.display_name = display_name
            existing.status = status
            existing.description = description
            existing.order_index = order_index
            existing.is_public = is_public
            existing.uptime_30d = uptime_30d
            session.add(existing)
            await session.flush()
            return existing

        component = StatusComponent(
            name=name,
            display_name=display_name,
            status=status,
            description=description,
            order_index=order_index,
            is_public=is_public,
            uptime_30d=uptime_30d,
        )
        session.add(component)
        await session.flush()
        return component
