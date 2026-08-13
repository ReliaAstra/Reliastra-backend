import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class VendorTracking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vendor_trackings"

    vendor_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# Compatibility alias while callers migrate from the original flat model name.
Vendor = VendorTracking


class VendorEndpoint(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vendor_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "vendor_id", "endpoint_url", name="uq_vendor_endpoints_vendor_url"
        ),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor_trackings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )
    regions: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["us-east", "eu-west"], nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(30), default="unknown", nullable=False
    )
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
