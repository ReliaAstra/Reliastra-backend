"""SQLAlchemy models for the RELIASTRA Partner Referral program (v1).

This is a deliberately minimal schema. There is exactly one earning
mechanism: a partner shares one referral link; a customer signs up through
it, subscribes, and the partner earns a recurring commission while that
customer stays subscribed.

Design rules:

* Money is never a float. Monetary columns are ``BigInteger`` minor units
  (cents for USD) paired with a ``currency`` column. Rates are integer
  percentages (``30`` == 30%).
* Partner identity reuses the existing ``referral_codes`` table (one user
  = one code). The partner does not get a second referral identity.
* The commission ledger is append-only: reversals are recorded on the same
  row via ``status``/``reversal_reason`` and the original amount is never
  edited (``subscription_amount_minor`` / ``commission_amount_minor`` keep
  their original values; a reversal simply changes ``status``).
* Duplicate commission accrual is prevented at the database level with a
  unique ``(billing_event_id, partner_id)`` constraint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PartnerProfile(UUIDMixin, TimestampMixin, Base):
    """A RELIASTRA user who has opted into the referral program.

    One partner per user. The partner links to the user's existing
    ``referral_codes`` row — there is exactly one canonical referral link
    per partner, and it is the same identity used by the PLG referral flow.
    """

    __tablename__ = "partner_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_partner_profiles_user_id"),
        UniqueConstraint(
            "referral_code_id", name="uq_partner_profiles_referral_code_id"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referral_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("referral_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )
    #: Simple lifetime counter powering the dashboard "clicks" metric. It is
    #: a counter, not an analytics platform — no per-click rows are stored.
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PartnerReferral(UUIDMixin, TimestampMixin, Base):
    """A customer attributed to a partner through their referral link.

    One customer can belong to at most one partner (enforced by the unique
    ``referred_user_id``), and a user can never refer themselves.
    """

    __tablename__ = "partner_referrals"
    __table_args__ = (
        UniqueConstraint(
            "referred_user_id", name="uq_partner_referrals_referred_user_id"
        ),
        Index("ix_partner_referrals_partner_status", "partner_id", "status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referred_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    #: referred | signed_up | paid | churned
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="signed_up", index=True
    )
    subscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PartnerCommission(UUIDMixin, TimestampMixin, Base):
    """One commission earned on one collected subscription payment.

    The ledger is append-only in spirit: the original amounts are never
    mutated. A refund/chargeback sets ``status`` to ``reversed`` and records
    ``reversal_reason``; the historical accrual remains visible.
    """

    __tablename__ = "partner_commissions"
    __table_args__ = (
        UniqueConstraint(
            "billing_event_id", "partner_id", name="uq_partner_commissions_idempotency"
        ),
        Index("ix_partner_commissions_partner_status", "partner_id", "status"),
        Index("ix_partner_commissions_status", "status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_referrals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: Idempotency anchor — the billing provider's transaction reference.
    billing_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Settlement bucket, ``YYYY-MM``.
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    subscription_amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    commission_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    #: Commission rate as an integer percentage (30 == 30%). Snapshotted so
    #: historical economics are stable even if configuration changes later.
    rate: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    #: pending | payable | paid | reversed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    payable_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: Payout that settled this commission, when paid.
    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_payouts.id", ondelete="SET NULL"), nullable=True
    )


class PartnerPayout(UUIDMixin, TimestampMixin, Base):
    """A payout of accumulated commission to a partner."""

    __tablename__ = "partner_payouts"
    __table_args__ = (
        Index("ix_partner_payouts_partner_status", "partner_id", "status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    #: pending | processing | paid | failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    transaction_reference: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = [
    "PartnerProfile",
    "PartnerReferral",
    "PartnerCommission",
    "PartnerPayout",
]
