import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Float, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AttributionResult(Base):
    """Deterministic attribution output for an incident (Phase 6)."""

    __tablename__ = "attribution_results"

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
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    methodology_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="v1.0"
    )
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_chain: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
