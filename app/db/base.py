import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
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


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


def import_all_models() -> None:
    # Ensure all models are imported so Base.metadata is populated
    import app.core.audit_log  # noqa: F401
    import app.modules.auth.models  # noqa: F401
    import app.modules.users.models  # noqa: F401
    import app.modules.organizations.models  # noqa: F401
    import app.modules.dependencies.models  # noqa: F401
    import app.modules.checks.models  # noqa: F401
    import app.modules.incidents.models  # noqa: F401
    import app.modules.evidence.models  # noqa: F401
    import app.modules.vendors.models  # noqa: F401
    import app.modules.notifications.models  # noqa: F401
    import app.modules.api_keys.models  # noqa: F401
    import app.modules.billing.models  # noqa: F401
    import app.modules.dashboard.models  # noqa: F401
