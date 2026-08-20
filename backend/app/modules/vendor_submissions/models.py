from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class VendorSubmission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vendor_submissions"

    vendor_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    category: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    website_url: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    submitter_email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    submitter_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    submitter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    endpoints_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_review",
    )
    review_note: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class VendorSubmissionEndpoint(UUIDMixin, Base):
    __tablename__ = "vendor_submission_endpoints"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor_submissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    url: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    method: Mapped[str] = mapped_column(
        String(10), nullable=False, default="GET",
    )
    expected_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=200,
    )
