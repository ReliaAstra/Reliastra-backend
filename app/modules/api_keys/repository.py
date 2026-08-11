"""API key persistence and authentication queries."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.api_keys.models import ApiKey


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, values: dict[str, object]) -> ApiKey:
        model = ApiKey(**values)
        self.session.add(model)
        await self.session.flush()
        return model

    async def list(self, org_id: UUID) -> list[ApiKey]:
        return list(
            (
                await self.session.scalars(
                    select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
                )
            ).all()
        )

    async def get(self, org_id: UUID, key_id: UUID) -> ApiKey | None:
        return cast(
            ApiKey | None,
            await self.session.scalar(
                select(ApiKey).where(ApiKey.org_id == org_id, ApiKey.id == key_id)
            ),
        )

    async def by_hash(self, key_hash: str) -> ApiKey | None:
        return cast(
            ApiKey | None,
            await self.session.scalar(select(ApiKey).where(ApiKey.hashed_key == key_hash)),
        )

    async def touch(self, model: ApiKey, now: datetime) -> None:
        model.last_used_at = now
        await self.session.flush()

    async def delete(self, model: ApiKey) -> None:
        await self.session.delete(model)
        await self.session.flush()
