"""Unit tests for the pure commission arithmetic.

These are the tests that matter most in the whole partner feature: every
number a partner is ever paid comes out of this module, and it has no I/O,
so it can be pinned down exactly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import settings
from app.modules.partners import economics
from app.modules.partners.constants import EarningMethod

JAN = datetime(2025, 1, 1, tzinfo=timezone.utc)


# ─────────────────────────── rate resolution ─────────────────────────────


def test_default_rates_match_the_published_program():
    assert economics.default_rate_bps(EarningMethod.REFER.value) == 2000
    assert economics.default_rate_bps(EarningMethod.DEPLOY.value) == 3000
    assert economics.default_rate_bps(EarningMethod.CREATE.value) == 2500
    assert economics.default_rate_bps(EarningMethod.INTRODUCE.value) == 1500
    assert economics.default_rate_bps(EarningMethod.RESELL.value) == 0


def test_custom_rate_is_honoured_but_clamped_to_the_ceiling():
    resolved = economics.resolve_rate_bps(
        EarningMethod.REFER.value, custom_rate_bps={"refer": 2800}
    )
    assert resolved == 2800

    # A negotiated deal cannot breach the platform maximum.
    clamped = economics.resolve_rate_bps(
        EarningMethod.REFER.value, custom_rate_bps={"refer": 9000}
    )
    assert clamped == economics.max_total_rate_bps() == 5000


def test_negative_custom_rate_is_rejected():
    with pytest.raises(economics.CommissionCalculationError):
        economics.resolve_rate_bps(
            EarningMethod.REFER.value, custom_rate_bps={"refer": -100}
        )


# ────────────────────────────── arithmetic ───────────────────────────────


@pytest.mark.parametrize(
    "amount,rate,expected",
    [
        (1900, 2000, 380),      # $19.00 @ 20% = $3.80
        (4900, 3000, 1470),     # $49.00 @ 30% = $14.70
        (9900, 2500, 2475),     # $99.00 @ 25% = $24.75
        (1999, 1500, 300),      # 299.85 -> 300 (half-up)
        (1, 5000, 1),           # 0.5 -> 1 (half-up, never truncates to 0)
        (0, 5000, 0),
        (100_000_000_000, 2000, 20_000_000_000),  # no precision loss at scale
    ],
)
def test_apply_bps_rounds_half_up_and_returns_int(amount, rate, expected):
    result = economics.apply_bps(amount, rate)
    assert result == expected
    assert isinstance(result, int)


def test_apply_bps_multiplies_before_dividing():
    """A naive ``rate/10000`` float would lose the cent here."""
    assert economics.apply_bps(3333, 1500) == 500  # 499.95 -> 500


def test_to_minor_units_rejects_floats_outright():
    """Floats are the classic way money goes wrong; the door is closed."""
    with pytest.raises(economics.CommissionCalculationError):
        economics.to_minor_units(19.99)

    assert economics.to_minor_units(Decimal("19.99")) == 1999
    assert economics.to_minor_units("19.99") == 1999
    assert economics.to_minor_units(19) == 1900


def test_commissionable_amount_subtracts_and_floors_at_zero():
    assert (
        economics.commissionable_amount(
            collected_minor=10_000, tax_minor=1_000, processing_fee_minor=300
        )
        == 8_700
    )
    # Never negative, even when deductions exceed what was collected.
    assert (
        economics.commissionable_amount(collected_minor=1_000, refunded_minor=5_000)
        == 0
    )


# ──────────────────────── commission calculation ─────────────────────────


def test_refer_commission_on_a_real_payment():
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=4900,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN + timedelta(days=30),
    )
    assert quote.amount_minor == 980
    assert quote.rate_bps == 2000
    assert quote.is_payable
    assert quote.basis["formula"]


def test_commission_uses_collected_revenue_not_list_price():
    """A discounted payment earns commission on what was actually paid."""
    full = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=4900,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
    )
    discounted = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=2940,  # 40% founding discount
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
    )
    assert full.amount_minor == 980
    assert discounted.amount_minor == 588
    assert discounted.source_minor == 2940


def test_resell_earns_no_commission_because_margin_is_the_reward():
    quote = economics.calculate_commission(
        earning_method=EarningMethod.RESELL.value,
        collected_minor=100_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
    )
    assert quote.amount_minor == 0
    assert quote.reason == "resell_wholesale_margin"
    assert not quote.is_payable


def test_introduce_earns_only_inside_the_year_one_window():
    inside = economics.calculate_commission(
        earning_method=EarningMethod.INTRODUCE.value,
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN + timedelta(days=300),
    )
    assert inside.amount_minor == 1500

    outside = economics.calculate_commission(
        earning_method=EarningMethod.INTRODUCE.value,
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN + timedelta(days=400),
    )
    assert outside.amount_minor == 0
    assert outside.reason == "outside_earning_window"


def test_total_commission_is_capped_at_fifty_percent():
    """Two partners on one customer cannot together exceed the ceiling."""
    first = economics.calculate_commission(
        earning_method=EarningMethod.DEPLOY.value,   # 30%
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
    )
    second = economics.calculate_commission(
        earning_method=EarningMethod.CREATE.value,   # 25% -> clipped to 20%
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
        already_applied_bps=first.rate_bps,
    )
    assert first.rate_bps == 3000
    assert second.rate_bps == 2000
    assert second.reason == "rate_capped_by_ceiling"
    assert first.rate_bps + second.rate_bps == 5000
    assert first.amount_minor + second.amount_minor == 5000  # exactly 50%


def test_ceiling_already_consumed_yields_nothing_more():
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
        already_applied_bps=5000,
    )
    assert quote.amount_minor == 0
    assert quote.reason == "commission_ceiling_reached"


def test_snapshotted_relationship_rate_wins_over_current_config():
    """Historical economics must not shift when configuration changes."""
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=10_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
        relationship_rate_bps=1200,  # what was agreed at signup
    )
    assert quote.rate_bps == 1200
    assert quote.amount_minor == 1200


def test_fully_refunded_payment_produces_no_commission():
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=5_000,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN,
        refunded_minor=5_000,
    )
    assert quote.amount_minor == 0
    assert quote.reason == "no_commissionable_revenue"


def test_small_clock_skew_does_not_cost_a_partner_their_first_commission():
    """``paid_at`` and our own ``started_at`` come from different clocks.

    On the very first payment they are effectively simultaneous, so a few
    seconds of skew in either direction must still earn.
    """
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=4900,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN - timedelta(seconds=30),
    )
    assert quote.amount_minor == 980


def test_a_genuinely_earlier_payment_does_not_earn():
    """Revenue collected long before the relationship existed is not owed."""
    quote = economics.calculate_commission(
        earning_method=EarningMethod.REFER.value,
        collected_minor=4900,
        currency="USD",
        relationship_started_at=JAN,
        event_at=JAN - timedelta(days=30),
    )
    assert quote.amount_minor == 0
    assert quote.reason == "outside_earning_window"


def test_negative_collected_amount_is_a_programming_error():
    with pytest.raises(economics.CommissionCalculationError):
        economics.calculate_commission(
            earning_method=EarningMethod.REFER.value,
            collected_minor=-100,
            currency="USD",
            relationship_started_at=JAN,
            event_at=JAN,
        )


# ─────────────────────────────── reversals ───────────────────────────────


def test_full_reversal_returns_the_whole_commission():
    assert economics.calculate_reversal(original_amount_minor=980) == 980


def test_partial_reversal_is_proportional_and_never_exceeds_the_original():
    # $49.00 payment @ 20% = $9.80 commission; $24.50 refunded -> $4.90 back.
    magnitude = economics.calculate_reversal(
        original_amount_minor=980,
        refunded_minor=2450,
        original_commissionable_minor=4900,
        rate_bps=2000,
    )
    assert magnitude == 490

    # An over-stated refund still cannot claw back more than was paid.
    capped = economics.calculate_reversal(
        original_amount_minor=980,
        refunded_minor=999_999,
        original_commissionable_minor=4900,
        rate_bps=2000,
    )
    assert capped == 980


# ──────────────────────────── time helpers ───────────────────────────────


def test_hold_until_uses_the_configured_holding_period():
    assert economics.hold_until(JAN) == JAN + timedelta(
        days=settings.PARTNER_COMMISSION_HOLD_DAYS
    )


def test_attribution_expiry_uses_the_configured_window():
    assert economics.attribution_expiry(JAN) == JAN + timedelta(
        days=settings.PARTNER_ATTRIBUTION_WINDOW_DAYS
    )


def test_introduce_window_end_handles_leap_days():
    """29 Feb + 12 months must not raise; it clamps to the 28th."""
    leap = datetime(2024, 2, 29, tzinfo=timezone.utc)
    assert economics.introduce_window_end(leap) == datetime(
        2025, 2, 28, tzinfo=timezone.utc
    )


def test_period_month_is_the_settlement_grouping_key():
    assert economics.period_month(datetime(2025, 3, 7, tzinfo=timezone.utc)) == "2025-03"
    assert economics.period_month(datetime(2025, 12, 31, tzinfo=timezone.utc)) == "2025-12"


# ───────────────────────────── payout floor ──────────────────────────────


def test_payout_threshold_uses_config_and_honours_partner_overrides():
    assert economics.meets_payout_threshold(5000) is True
    assert economics.meets_payout_threshold(4999) is False
    assert (
        economics.meets_payout_threshold(2000, partner_minimum_minor=1000) is True
    )
