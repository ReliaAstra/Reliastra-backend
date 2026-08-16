from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class BadgeImpression(UUIDMixin, Base):  # NOTE: No TimestampMixin — only created_at
    __tablename__ = "badge_impressions"

    vendor_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    utm_source: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
