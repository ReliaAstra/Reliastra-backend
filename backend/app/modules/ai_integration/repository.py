import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_integration.models import AIProvider


class AIProviderRepository:
    @staticmethod
    async def list_for_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[AIProvider]:
        result = await session.execute(
            select(AIProvider)
            .where(AIProvider.organization_id == org_id)
            .order_by(AIProvider.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(
        session: AsyncSession, provider_id: uuid.UUID
    ) -> AIProvider | None:
        result = await session.execute(
            select(AIProvider).where(AIProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_default(
        session: AsyncSession, org_id: uuid.UUID
    ) -> AIProvider | None:
        result = await session.execute(
            select(AIProvider)
            .where(
                AIProvider.organization_id == org_id,
                AIProvider.is_default.is_(True),
                AIProvider.enabled.is_(True),
            )
            .order_by(AIProvider.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def clear_defaults(
        session: AsyncSession,
        org_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = update(AIProvider).where(
            AIProvider.organization_id == org_id,
            AIProvider.is_default.is_(True),
        )
        if exclude_id:
            statement = statement.where(AIProvider.id != exclude_id)
        await session.execute(statement.values(is_default=False))

    @staticmethod
    async def create(
        session: AsyncSession, **values: Any
    ) -> AIProvider:
        provider = AIProvider(**values)
        session.add(provider)
        await session.flush()
        return provider

    @staticmethod
    async def update(
        session: AsyncSession, provider: AIProvider, **values: Any
    ) -> AIProvider:
        for key, value in values.items():
            if hasattr(provider, key):
                setattr(provider, key, value)
        session.add(provider)
        await session.flush()
        return provider

    @staticmethod
    async def delete(
        session: AsyncSession, provider: AIProvider
    ) -> None:
        await session.delete(provider)
        await session.flush()
