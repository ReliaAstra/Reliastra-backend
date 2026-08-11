"""Public free-tier vendor catalog model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class VendorTracking(UUIDMixin, Base):
    __tablename__ = "vendor_tracking"

    vendor_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    category: Mapped[str] = mapped_column(String(100), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
