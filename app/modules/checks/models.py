"""High-volume partitioned check result model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        Index("ix_check_results_dep_executed", "dependency_id", "executed_at"),
        Index("ix_check_results_org_executed", "org_id", "executed_at"),
        {"postgresql_partition_by": "RANGE (executed_at)"},
    )

    # PostgreSQL partitioned unique constraints must include the partition key.
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, default=utc_now
    )
    dependency_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dependencies.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    region: Mapped[str] = mapped_column(String(50))
    latency_ms: Mapped[float] = mapped_column(Float)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_up: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    quorum_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
