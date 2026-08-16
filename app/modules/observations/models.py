import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_source_timestamp", "source_id", "timestamp"),
        Index("ix_observations_org_timestamp", "org_id", "timestamp"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tls_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tls_certificate_issuer: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    tls_certificate_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # `metadata` is reserved by SQLAlchemy's declarative base, so expose the
    # database column through an unambiguous Python attribute.
    observation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
