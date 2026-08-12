import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Float, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Observation(Base):
    """Unified observation record (Phase 3).

    Every measurement in the system — public vendor probes, customer dependency
    checks, and future synthetic transactions — is represented as an
    ``Observation``. This is the keystone that powers vendor intelligence,
    deterministic attribution, and evidence snapshots. The legacy
    ``check_results`` table is deprecated in favour of this model.
    """

    __tablename__ = "observations"
    __table_args__ = (
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dependencies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        primary_key=True,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tls_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tls_certificate_issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tls_certificate_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    @property
    def is_up(self) -> bool:
        return self.error_type is None or self.error_type == "none"
