import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDMixin, TimestampMixin


class Subscription(UUIDMixin, TimestampMixin, Base):
    """Decoupled payment subscription record.

    Replaces the Stripe-specific columns on ``Organization``. The
    ``organizations.stripe_customer_id`` / ``stripe_subscription_id`` columns are
    deprecated and kept only for backward compatibility (Phase 10).
    """

    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="paystack"
    )
    provider_customer_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    provider_reference: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="initiated"
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
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
