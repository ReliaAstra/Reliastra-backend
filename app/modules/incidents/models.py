"""Verified incident and correlation models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utc_now
from app.modules.incidents.constants import (
    CorrelationMethod,
    IncidentSeverity,
    IncidentStatus,
    RootCause,
)


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    dependency_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dependencies.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incident_severity"), default=IncidentSeverity.MAJOR
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"), default=IncidentStatus.OPEN, index=True
    )
    root_cause: Mapped[RootCause] = mapped_column(
        Enum(RootCause, name="root_cause"), default=RootCause.UNKNOWN
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_report_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "evidence_reports.id",
            use_alter=True,
            name="fk_incident_evidence_report",
            ondelete="SET NULL",
        ),
        nullable=True,
    )


class IncidentCorrelation(UUIDMixin, Base):
    __tablename__ = "incident_correlations"

    incident_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    correlated_dependency_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dependencies.id", ondelete="CASCADE")
    )
    correlation_confidence: Mapped[float] = mapped_column(Float)
    time_window_seconds: Mapped[int] = mapped_column(Integer)
    correlation_method: Mapped[CorrelationMethod] = mapped_column(
        Enum(CorrelationMethod, name="correlation_method"), default=CorrelationMethod.TEMPORAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
