import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class EvidenceReport(Base):
    """Legacy mutable evidence report (kept for backward compatibility)."""

    __tablename__ = "evidence_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EvidenceSnapshot(Base):
    """Immutable evidence snapshot (Phase 7).

    Captured at the time of incident resolution; never modified. New evidence
    creates a new snapshot. A public ``verification_id`` powers the
    unauthenticated verification API.
    """

    __tablename__ = "evidence_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependencies.id", ondelete="CASCADE"), nullable=False
    )
    time_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    time_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observation_ids: Mapped[list[uuid.UUID]] = mapped_column(
        JSON, nullable=False
    )
    attribution_result: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    methodology_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="v1.0"
    )
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    report_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    report_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    json_evidence_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
