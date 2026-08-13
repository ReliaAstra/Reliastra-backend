import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dependency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    severity: Mapped[str] = mapped_column(
        String(30), default="major", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="open", nullable=False, index=True
    )
    root_cause: Mapped[str] = mapped_column(
        String(50), default="unknown", nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_reports.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    correlations: Mapped[list["IncidentCorrelation"]] = relationship(
        "IncidentCorrelation",
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class IncidentCorrelation(UUIDMixin, Base):
    __tablename__ = "incident_correlations"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correlated_dependency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correlation_confidence: Mapped[float] = mapped_column(
        Float, default=0.85, nullable=False
    )
    time_window_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )
    correlation_method: Mapped[str] = mapped_column(
        String(50), default="temporal", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        "Incident", back_populates="correlations"
    )
