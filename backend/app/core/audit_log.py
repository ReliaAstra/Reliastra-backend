import logging
import uuid
from typing import Any
from sqlalchemy import String, JSON, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base, UUIDMixin, TimestampMixin

logger = logging.getLogger(__name__)


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    org_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AuditLogService:
    @staticmethod
    async def log_event(
        session: AsyncSession,
        event_type: str,
        org_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        audit_entry = AuditLog(
            org_id=org_id,
            user_id=user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
        )
        session.add(audit_entry)
        await session.flush()
        logger.info(
            "AuditLog recorded: event_type=%s, org_id=%s, resource_id=%s",
            event_type,
            org_id,
            resource_id,
        )
        return audit_entry

    @staticmethod
    async def get_events(
        session: AsyncSession,
        org_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        query = select(AuditLog)
        if org_id:
            query = query.where(AuditLog.org_id == org_id)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())
