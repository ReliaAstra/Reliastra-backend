"""Declarative base and reusable model mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def import_all_models() -> None:
    """Register model metadata for Alembic; business modules never use this escape hatch."""
    from app.core.audit_log import AuditLog  # noqa: F401
    from app.modules.api_keys.models import ApiKey  # noqa: F401
    from app.modules.auth.models import RefreshToken  # noqa: F401
    from app.modules.checks.models import CheckResult  # noqa: F401
    from app.modules.dependencies.models import Dependency  # noqa: F401
    from app.modules.evidence.models import EvidenceReport  # noqa: F401
    from app.modules.incidents.models import Incident, IncidentCorrelation  # noqa: F401
    from app.modules.notifications.models import AlertConfig  # noqa: F401
    from app.modules.organizations.models import Organization, OrganizationMember  # noqa: F401
    from app.modules.users.models import User  # noqa: F401
    from app.modules.vendors.models import VendorTracking  # noqa: F401
