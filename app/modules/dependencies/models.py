import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, ForeignKey, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


class Dependency(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "dependencies"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expected_status_codes: Mapped[list[int]] = mapped_column(
        JSON, default=lambda: [200], nullable=False
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
        index=True,
    )
    regions: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["us-east", "eu-west"], nullable=False
    )
    alert_threshold_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
