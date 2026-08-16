from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class TimelineShare(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "timeline_shares"

    vendor_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    share_token: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    window: Mapped[str] = mapped_column(
        String(50), nullable=False, default="24h"
    )
    region: Mapped[str] = mapped_column(
        String(50), nullable=False, default="us-east"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    utm_source: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
