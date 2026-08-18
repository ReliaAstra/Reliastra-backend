"""Pure commission arithmetic for the Partner Network.

This module is deliberately free of I/O: no database, no HTTP, no clock
unless it is passed in. Everything here is a total function over integers,
which is what makes the financial behaviour of the platform testable and
reviewable in isolation.

**Money rules enforced here**

* All amounts are integer *minor units* (cents). No ``float`` ever appears
  in a calculation path; where division is unavoidable we use
  :class:`~decimal.Decimal` with an explicit rounding mode and immediately
  return to ``int``.
* Rates are integer basis points (bps). ``rate_bps / 10_000`` is the
  fraction, but we never actually perform that float division — we multiply
  first and divide last.
* Commission is always computed from the **actual collected amount**, never
  from a list price or an invoice face value.
* The combined rate applied to a single payment is capped at
  ``PARTNER_MAX_TOTAL_COMMISSION_BPS`` (50% by default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.config import settings
from app.modules.partners.constants import (
    BPS_DENOMINATOR,
    EarningMethod,
    ZERO_COMMISSION_METHODS,
)


class CommissionCalculationError(ValueError):
    """Raised when inputs to a commission calculation are not coherent."""


# ─────────────────────────────── Rates ───────────────────────────────────


def default_rate_bps(method: str) -> int:
    """Return the configured commission rate (bps) for an earning method.

    Rates live in configuration, never in code, so that the economics can be
    tuned per-environment without a deploy of business logic.
    """
    mapping = {
        EarningMethod.REFER.value: settings.PARTNER_RATE_REFER_BPS,
        EarningMethod.DEPLOY.value: settings.PARTNER_RATE_DEPLOY_BPS,
        EarningMethod.CREATE.value: settings.PARTNER_RATE_CREATE_BPS,
        EarningMethod.INTRODUCE.value: settings.PARTNER_RATE_INTRODUCE_BPS,
        EarningMethod.RESELL.value: settings.PARTNER_RATE_RESELL_BPS,
    }
    if method not in mapping:
        raise CommissionCalculationError(f"Unknown earning method: {method!r}")
    return int(mapping[method])


def max_total_rate_bps() -> int:
    """The hard ceiling on the combined rate for one payment."""
    return int(settings.PARTNER_MAX_TOTAL_COMMISSION_BPS)


def resolve_rate_bps(
    method: str,
    *,
    custom_rate_bps: dict | None = None,
) -> int:
    """Resolve the effective rate for a method, honouring negotiated terms.

    A partner may carry per-method custom rates (a STRATEGIC-tier capability).
    Custom rates are still clamped to the global ceiling — a negotiated deal
    can never breach the platform's maximum.
    """
    rate = default_rate_bps(method)
    if custom_rate_bps:
        override = custom_rate_bps.get(method)
        if override is not None:
            try:
                rate = int(override)
            except (TypeError, ValueError) as exc:
                raise CommissionCalculationError(
                    f"Invalid custom rate for {method!r}: {override!r}"
                ) from exc
    if rate < 0:
        raise CommissionCalculationError("Commission rate cannot be negative")
    return min(rate, max_total_rate_bps())


# ──────────────────────────── Core arithmetic ────────────────────────────


def apply_bps(amount_minor: int, rate_bps: int) -> int:
    """Apply a basis-point rate to an integer minor-unit amount.

    Uses :class:`Decimal` with ``ROUND_HALF_UP`` — the conventional rounding
    for money — and returns an ``int``. Multiplication happens before
    division so no precision is lost.

    >>> apply_bps(1900, 2000)   # 20% of $19.00
    380
    >>> apply_bps(1999, 1500)   # 15% of $19.99 → 2.9985 → 3.00
    300
    """
    if amount_minor < 0:
        raise CommissionCalculationError("amount_minor must be non-negative")
    if rate_bps < 0:
        raise CommissionCalculationError("rate_bps must be non-negative")
    if rate_bps == 0 or amount_minor == 0:
        return 0
    product = Decimal(int(amount_minor)) * Decimal(int(rate_bps))
    return int(
        (product / Decimal(BPS_DENOMINATOR)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def to_minor_units(amount: Decimal | int | str, exponent: int = 2) -> int:
    """Convert a major-unit amount to integer minor units.

    Accepts ``Decimal``/``int``/``str`` only — passing a ``float`` is a bug
    and raises, because float parsing of money is exactly the failure mode
    this codebase forbids.
    """
    if isinstance(amount, float):  # pragma: no cover - defensive
        raise CommissionCalculationError(
            "Refusing to convert a float to money; pass Decimal or str"
        )
    value = Decimal(amount) if not isinstance(amount, Decimal) else amount
    scaled = value * (Decimal(10) ** exponent)
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_minor(amount_minor: int, exponent: int = 2) -> str:
    """Render minor units as a decimal string for display/audit trails."""
    sign = "-" if amount_minor < 0 else ""
    quantum = Decimal(10) ** exponent
    value = (Decimal(abs(int(amount_minor))) / quantum).quantize(
        Decimal(1).scaleb(-exponent)
    )
    return f"{sign}{value}"


# ───────────────────────── Commissionable base ───────────────────────────


def commissionable_amount(
    *,
    collected_minor: int,
    tax_minor: int = 0,
    processing_fee_minor: int = 0,
    refunded_minor: int = 0,
) -> int:
    """Net revenue the platform actually kept, and may pay commission on.

    Commission is never paid on tax collected on behalf of a government, on
    the payment processor's cut, or on money that was refunded.
    """
    for name, value in (
        ("collected_minor", collected_minor),
        ("tax_minor", tax_minor),
        ("processing_fee_minor", processing_fee_minor),
        ("refunded_minor", refunded_minor),
    ):
        if value < 0:
            raise CommissionCalculationError(f"{name} must be non-negative")
    base = (
        int(collected_minor)
        - int(tax_minor)
        - int(processing_fee_minor)
        - int(refunded_minor)
    )
    return max(0, base)


# ───────────────────────────── Eligibility ───────────────────────────────


def introduce_window_end(started_at: datetime) -> datetime:
    """End of the Year-1 window for an INTRODUCE relationship."""
    months = int(settings.PARTNER_INTRODUCE_WINDOW_MONTHS)
    year = started_at.year + (started_at.month - 1 + months) // 12
    month = (started_at.month - 1 + months) % 12 + 1
    day = min(
        started_at.day,
        [
            31,
            29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return started_at.replace(year=year, month=month, day=day)


#: Tolerance for a payment timestamp that slightly predates the
#: relationship it belongs to.
#:
#: The two timestamps come from different clocks: ``event_at`` is the
#: provider's ``paid_at`` while ``relationship_started_at`` is set by our
#: own server when the conversion is recorded. On the very first payment
#: these are effectively simultaneous, and a few seconds of skew must not
#: silently cost a partner their commission. Anything older than this is a
#: genuinely pre-existing payment and does not earn.
CLOCK_SKEW_TOLERANCE = timedelta(hours=1)


def is_within_earning_window(
    method: str,
    *,
    relationship_started_at: datetime,
    event_at: datetime,
    eligible_until: datetime | None = None,
) -> bool:
    """Whether a payment at ``event_at`` still earns for this method.

    Recurring methods (refer/deploy/create) have no end date while the
    relationship is active. Year-1 methods (introduce) stop at the window
    boundary.
    """
    if event_at < relationship_started_at - CLOCK_SKEW_TOLERANCE:
        return False
    if eligible_until is not None:
        return event_at <= eligible_until
    if method in {EarningMethod.INTRODUCE.value}:
        return event_at <= introduce_window_end(relationship_started_at)
    return True


def hold_until(earned_at: datetime, *, hold_days: int | None = None) -> datetime:
    """When a commission earned at ``earned_at`` becomes payable."""
    days = (
        int(settings.PARTNER_COMMISSION_HOLD_DAYS) if hold_days is None else int(hold_days)
    )
    return earned_at + timedelta(days=days)


def attribution_expiry(occurred_at: datetime, *, window_days: int | None = None) -> datetime:
    """End of the attribution window for a touch at ``occurred_at``."""
    days = (
        int(settings.PARTNER_ATTRIBUTION_WINDOW_DAYS)
        if window_days is None
        else int(window_days)
    )
    return occurred_at + timedelta(days=days)


def period_month(moment: datetime) -> str:
    """``YYYY-MM`` settlement bucket for a revenue event."""
    as_utc = moment.astimezone(timezone.utc) if moment.tzinfo else moment
    return f"{as_utc.year:04d}-{as_utc.month:02d}"


# ─────────────────────────── Calculation result ──────────────────────────


@dataclass(frozen=True)
class CommissionQuote:
    """The full, auditable result of a commission calculation.

    ``basis`` is persisted verbatim onto the ledger entry so that any future
    reader can reconstruct exactly why the partner was paid this amount,
    even after configuration has changed.
    """

    amount_minor: int
    rate_bps: int
    commissionable_minor: int
    source_minor: int
    currency: str
    earning_method: str
    is_payable: bool
    reason: str | None = None
    basis: dict = field(default_factory=dict)

    @property
    def is_zero(self) -> bool:
        return self.amount_minor == 0


def calculate_commission(
    *,
    earning_method: str,
    collected_minor: int,
    currency: str,
    relationship_started_at: datetime,
    event_at: datetime,
    eligible_until: datetime | None = None,
    tax_minor: int = 0,
    processing_fee_minor: int = 0,
    refunded_minor: int = 0,
    custom_rate_bps: dict | None = None,
    relationship_rate_bps: int | None = None,
    already_applied_bps: int = 0,
) -> CommissionQuote:
    """Compute the commission owed for one collected payment.

    Parameters
    ----------
    collected_minor:
        The amount **actually collected** from the customer, in minor units,
        as reported by the verified payment. Never a list price.
    relationship_rate_bps:
        The rate snapshotted when the relationship was created. Preferred
        over the live configured rate so that historical economics are
        stable; the ceiling is still applied.
    already_applied_bps:
        Total bps already committed to other partners for this same payment.
        Used to enforce the global ceiling when several partners have a claim
        on one customer (e.g. one referred, another deployed).

    Returns
    -------
    CommissionQuote
        Always returned — a zero/ineligible outcome is expressed as
        ``amount_minor == 0`` with a populated ``reason``, never an
        exception, so that callers can record *why* nothing was earned.
    """
    if collected_minor < 0:
        raise CommissionCalculationError("collected_minor must be non-negative")

    base = commissionable_amount(
        collected_minor=collected_minor,
        tax_minor=tax_minor,
        processing_fee_minor=processing_fee_minor,
        refunded_minor=refunded_minor,
    )

    def _quote(
        amount: int, rate: int, payable: bool, reason: str | None, **extra
    ) -> CommissionQuote:
        basis = {
            "earning_method": earning_method,
            "collected_minor": int(collected_minor),
            "tax_minor": int(tax_minor),
            "processing_fee_minor": int(processing_fee_minor),
            "refunded_minor": int(refunded_minor),
            "commissionable_minor": int(base),
            "rate_bps": int(rate),
            "amount_minor": int(amount),
            "currency": currency,
            "max_total_bps": max_total_rate_bps(),
            "already_applied_bps": int(already_applied_bps),
            "event_at": event_at.isoformat(),
            "relationship_started_at": relationship_started_at.isoformat(),
            "formula": "round_half_up(commissionable_minor * rate_bps / 10000)",
        }
        basis.update(extra)
        if reason:
            basis["reason"] = reason
        return CommissionQuote(
            amount_minor=int(amount),
            rate_bps=int(rate),
            commissionable_minor=int(base),
            source_minor=int(collected_minor),
            currency=currency,
            earning_method=earning_method,
            is_payable=payable,
            reason=reason,
            basis=basis,
        )

    # Resellers are compensated by their wholesale margin. They never draw a
    # platform commission, so we short-circuit before any rate lookup.
    if earning_method in ZERO_COMMISSION_METHODS:
        return _quote(0, 0, False, "resell_wholesale_margin")

    if not is_within_earning_window(
        earning_method,
        relationship_started_at=relationship_started_at,
        event_at=event_at,
        eligible_until=eligible_until,
    ):
        return _quote(0, 0, False, "outside_earning_window")

    if base == 0:
        return _quote(0, 0, False, "no_commissionable_revenue")

    rate = (
        min(int(relationship_rate_bps), max_total_rate_bps())
        if relationship_rate_bps is not None
        else resolve_rate_bps(earning_method, custom_rate_bps=custom_rate_bps)
    )

    # Global ceiling across all partners claiming this payment.
    remaining = max_total_rate_bps() - max(0, int(already_applied_bps))
    if remaining <= 0:
        return _quote(0, 0, False, "commission_ceiling_reached")

    capped = min(rate, remaining)
    amount = apply_bps(base, capped)

    reason = "rate_capped_by_ceiling" if capped < rate else None
    return _quote(amount, capped, True, reason, requested_rate_bps=int(rate))


def calculate_reversal(
    *,
    original_amount_minor: int,
    refunded_minor: int | None = None,
    original_commissionable_minor: int | None = None,
    rate_bps: int | None = None,
) -> int:
    """Magnitude (positive) of the commission to claw back.

    A full refund reverses the whole commission. A partial refund reverses
    proportionally, using the same rate that produced the original entry so
    that partial reversals can never exceed the original.
    """
    original = abs(int(original_amount_minor))
    if refunded_minor is None or original_commissionable_minor in (None, 0):
        return original
    if rate_bps is None:
        raise CommissionCalculationError(
            "rate_bps is required to compute a partial reversal"
        )
    proportional = apply_bps(min(int(refunded_minor), int(original_commissionable_minor)), int(rate_bps))
    return min(original, proportional)


def meets_payout_threshold(
    balance_minor: int, *, partner_minimum_minor: int | None = None
) -> bool:
    """Whether a payable balance clears the minimum payout threshold."""
    minimum = (
        int(settings.PARTNER_MIN_PAYOUT_MINOR)
        if partner_minimum_minor is None
        else int(partner_minimum_minor)
    )
    return int(balance_minor) >= minimum


def payout_minimum_minor(partner_minimum_minor: int | None = None) -> int:
    return (
        int(settings.PARTNER_MIN_PAYOUT_MINOR)
        if partner_minimum_minor is None
        else int(partner_minimum_minor)
    )


__all__ = [
    "CommissionCalculationError",
    "CommissionQuote",
    "apply_bps",
    "attribution_expiry",
    "calculate_commission",
    "calculate_reversal",
    "commissionable_amount",
    "default_rate_bps",
    "format_minor",
    "hold_until",
    "introduce_window_end",
    "is_within_earning_window",
    "max_total_rate_bps",
    "meets_payout_threshold",
    "payout_minimum_minor",
    "period_month",
    "resolve_rate_bps",
    "to_minor_units",
]
