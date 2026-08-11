"""Alert configuration persistence."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import AlertConfig


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, org_id: UUID, active_only: bool = False) -> list[AlertConfig]:
        statement = select(AlertConfig).where(AlertConfig.org_id == org_id)
        if active_only:
            statement = statement.where(AlertConfig.is_active.is_(True))
        return list((await self.session.scalars(statement.order_by(AlertConfig.created_at))).all())

    async def get(self, org_id: UUID, config_id: UUID) -> AlertConfig | None:
        return cast(
            AlertConfig | None,
            await self.session.scalar(
                select(AlertConfig).where(AlertConfig.id == config_id, AlertConfig.org_id == org_id)
            ),
        )

    async def create(self, org_id: UUID, values: dict[str, object]) -> AlertConfig:
        model = AlertConfig(org_id=org_id, **values)
        self.session.add(model)
        await self.session.flush()
        return model

    async def update(self, model: AlertConfig, values: dict[str, object]) -> AlertConfig:
        for field, value in values.items():
            setattr(model, field, value)
        await self.session.flush()
        return model

    async def delete(self, model: AlertConfig) -> None:
        await self.session.delete(model)
        await self.session.flush()
