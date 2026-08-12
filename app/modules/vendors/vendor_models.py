import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDMixin, TimestampMixin


class Vendor(UUIDMixin, TimestampMixin, Base):
    """Canonical vendor record (Phase 3/4). Renamed from vendor_trackings with
    the addition of slug + icon_url."""

    __tablename__ = "vendors"

    vendor_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VendorEndpoint(UUIDMixin, TimestampMixin, Base):
    """Per-endpoint monitoring target for a vendor."""

    __tablename__ = "vendor_endpoints"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_probed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProbeConfig(UUIDMixin, TimestampMixin, Base):
    """Probe configuration for a vendor endpoint."""

    __tablename__ = "probe_configs"

    vendor_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    expected_status_codes: Mapped[list[int]] = mapped_column(
        JSON, default=lambda: [200], nullable=False
    )
    interval_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)


class VendorIncident(UUIDMixin, TimestampMixin, Base):
    """Independent vendor incident tracking (major vendor outages)."""

    __tablename__ = "vendor_incidents"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="open", nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VendorMetricsDaily(UUIDMixin, Base):
    """Pre-computed daily vendor reliability metrics."""

    __tablename__ = "vendor_metrics_daily"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    uptime_percentage: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_checks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_up: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_down: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
