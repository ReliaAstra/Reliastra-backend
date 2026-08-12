import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_integration.models import AiProvider


class AiProviderRepository:
    @staticmethod
    async def list_for_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[AiProvider]:
        stmt = (
            select(AiProvider)
            .where(AiProvider.org_id == org_id)
            .order_by(AiProvider.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(
        session: AsyncSession, org_id: uuid.UUID, provider_id: uuid.UUID
    ) -> AiProvider | None:
        stmt = select(AiProvider).where(
            AiProvider.id == provider_id, AiProvider.org_id == org_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default(
        session: AsyncSession, org_id: uuid.UUID
    ) -> AiProvider | None:
        stmt = (
            select(AiProvider)
            .where(
                AiProvider.org_id == org_id,
                AiProvider.enabled.is_(True),
            )
            .order_by(AiProvider.is_default.desc(), AiProvider.created_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        org_id: uuid.UUID,
        name: str,
        provider_type: str,
        endpoint_url: str,
        encrypted_api_key: str,
        model_name: str,
        is_default: bool,
        max_tokens: int,
        temperature: float,
        enabled: bool,
    ) -> AiProvider:
        provider = AiProvider(
            org_id=org_id,
            name=name,
            provider_type=provider_type,
            endpoint_url=endpoint_url,
            encrypted_api_key=encrypted_api_key,
            model_name=model_name,
            is_default=is_default,
            max_tokens=max_tokens,
            temperature=temperature,
            enabled=enabled,
        )
        session.add(provider)
        await session.flush()
        return provider

    @staticmethod
    async def update(
        session: AsyncSession, provider: AiProvider, **kwargs: Any
    ) -> AiProvider:
        for key, value in kwargs.items():
            if value is not None and hasattr(provider, key):
                setattr(provider, key, value)
        session.add(provider)
        await session.flush()
        return provider

    @staticmethod
    async def delete(session: AsyncSession, provider: AiProvider) -> None:
        await session.delete(provider)
        await session.flush()
