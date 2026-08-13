import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.notifications.models import AlertConfig


class AlertConfigRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, config_id: uuid.UUID
    ) -> AlertConfig | None:
        query = select(AlertConfig).where(AlertConfig.id == config_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        active_only: bool = False,
    ) -> list[AlertConfig]:
        query = (
            select(AlertConfig)
            .where(AlertConfig.org_id == org_id)
            .order_by(AlertConfig.created_at.desc())
        )
        if active_only:
            query = query.where(AlertConfig.is_active == True)  # noqa: E712
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        channel_type: str,
        config: dict[str, Any],
        is_active: bool = True,
    ) -> AlertConfig:
        alert_cfg = AlertConfig(
            org_id=org_id,
            channel_type=channel_type,
            config=config,
            is_active=is_active,
        )
        session.add(alert_cfg)
        await session.flush()
        return alert_cfg

    @staticmethod
    async def update(
        session: AsyncSession, alert_cfg: AlertConfig, **kwargs: Any
    ) -> AlertConfig:
        for key, value in kwargs.items():
            if value is not None and hasattr(alert_cfg, key):
                setattr(alert_cfg, key, value)
        session.add(alert_cfg)
        await session.flush()
        return alert_cfg

    @staticmethod
    async def delete(session: AsyncSession, alert_cfg: AlertConfig) -> None:
        await session.delete(alert_cfg)
        await session.flush()
