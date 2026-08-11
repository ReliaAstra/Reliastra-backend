"""External endpoint monitoring configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, utc_now
from app.modules.dependencies.constants import HttpMethod


class Dependency(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "dependencies"

    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[HttpMethod] = mapped_column(
        Enum(HttpMethod, name="http_method"), default=HttpMethod.GET
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expected_status_codes: Mapped[list[int]] = mapped_column(JSONB, default=lambda: [200])
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    regions: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["us-east", "eu-west"])
    alert_threshold_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    dependency_type: Mapped[str] = mapped_column(String(20), default="vendor")
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
