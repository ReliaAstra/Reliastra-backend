from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class StatusPage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "status_pages"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    show_uptime_graph: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    show_incident_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    branding: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # {logo_url, primary_color, custom_css}
    allowed_domains: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class StatusComponent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "status_components"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="operational"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    uptime_30d: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0
    )
