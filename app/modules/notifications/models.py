"""Organization notification routing configuration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.notifications.constants import ChannelType


class AlertConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alert_configs"

    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    channel_type: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="channel_type"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
