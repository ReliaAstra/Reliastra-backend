import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AttributionResult(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attribution_results"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suspected_dependency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    classification: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    signal_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    contradicting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    methodology_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1.0"
    )
