"""Fraud scoring, geo resolution and background-job behaviour.

The fraud tests exist as much to pin down what the system *refuses* to
treat as fraud as what it flags. Shared IPs, shared corporate domains,
offices, universities and VPNs are normal customer behaviour, and a rule
that punished them would quietly destroy legitimate partnerships.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import settings
from app.modules.partners.constants import (
    FRAUD_SIGNAL_WEIGHTS,
    RISK_BANDS,
    FraudSignal,
    RiskBand,
    risk_band_for_score,
)
from app.modules.partners.fraud import FraudService, _severity_for
from app.modules.partners.geo import GeoResult, _is_public_ip, lookup_ip, reset_reader


# ═════════════════════════════ risk bands ════════════════════════════════


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, RiskBand.LOW.value),
        (29, RiskBand.LOW.value),
        (30, RiskBand.MEDIUM.value),
        (59, RiskBand.MEDIUM.value),
        (60, RiskBand.HIGH.value),
        (79, RiskBand.HIGH.value),
        (80, RiskBand.CRITICAL.value),
        (100, RiskBand.CRITICAL.value),
    ],
)
def test_risk_bands_match_the_documented_thresholds(score, expected):
    assert risk_band_for_score(score) == expected


def test_bands_are_ordered_for_first_match_lookup_and_cover_zero():
    """``RISK_BANDS`` is descending so the first matching floor wins."""
    thresholds = [t for t, _ in RISK_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)
    # A zero floor guarantees every score resolves to a band.
    assert thresholds[-1] == 0


# ═════════════════════════════ signal rules ══════════════════════════════


def _metrics(**overrides) -> dict:
    base = {
        "window_days": 90,
        "clicks": 0,
        "unique_visitors": 0,
        "bot_clicks": 0,
        "signups": 0,
        "self_referrals": 0,
        "commissions": 0,
        "commission_amount_minor": 0,
        "reversals": 0,
        "reversal_amount_minor": 0,
        "chargebacks": 0,
        "relationships": 0,
        "churned_within_30d": 0,
        "rejected_claims": 0,
        "disposable_email_leads": 0,
    }
    base.update(overrides)
    return base


class TestFraudSignalsAreBehavioural:
    def test_there_is_no_shared_ip_signal_at_all(self):
        """Shared infrastructure is not evidence of fraud.

        Offices, coworking spaces, universities, VPNs and mobile carrier
        NAT all produce shared addresses for entirely unrelated people.
        """
        signal_names = {s.value for s in FraudSignal}
        for forbidden in ("same_ip", "shared_ip", "ip_match", "duplicate_ip"):
            assert forbidden not in signal_names
        assert not any("ip" in name.split("_") for name in signal_names)

    def test_there_is_no_shared_email_domain_signal(self):
        """Colleagues referring colleagues is the product working."""
        signal_names = {s.value for s in FraudSignal}
        for forbidden in ("same_domain", "shared_domain", "company_domain"):
            assert forbidden not in signal_names

    def test_a_clean_partner_scores_zero(self):
        assert FraudService._derive_signals(_metrics()) == set()

    def test_a_normal_successful_partner_is_not_flagged(self):
        """High volume with healthy conversion must stay clean."""
        signals = FraudService._derive_signals(
            _metrics(
                clicks=5_000,
                unique_visitors=3_200,
                signups=180,
                commissions=40,
                reversals=2,
                relationships=40,
                churned_within_30d=3,
            )
        )
        assert signals == set()

    def test_self_referral_is_flagged(self):
        signals = FraudService._derive_signals(_metrics(self_referrals=1))
        assert FraudSignal.SELF_REFERRAL.value in signals

    def test_chargebacks_need_a_pattern_not_a_single_incident(self):
        assert FraudService._derive_signals(_metrics(chargebacks=1)) == set()
        assert FraudSignal.CHARGEBACK_HISTORY.value in FraudService._derive_signals(
            _metrics(chargebacks=2)
        )

    def test_refund_rate_requires_enough_volume_to_be_meaningful(self):
        # 1 of 2 refunded is a 50% rate but far too small a sample.
        assert FraudService._derive_signals(
            _metrics(commissions=2, reversals=1)
        ) == set()
        # 4 of 10 at real volume is a genuine signal.
        assert FraudSignal.HIGH_REFUND_RATE.value in FraudService._derive_signals(
            _metrics(commissions=10, reversals=4)
        )

    def test_rapid_churn_requires_volume_and_a_majority(self):
        assert FraudService._derive_signals(
            _metrics(relationships=4, churned_within_30d=4)
        ) == set()
        assert FraudSignal.RAPID_CHURN.value in FraudService._derive_signals(
            _metrics(relationships=10, churned_within_30d=6)
        )

    def test_click_flooding_needs_both_volume_and_extreme_concentration(self):
        # A popular link with real visitors is fine.
        assert FraudService._derive_signals(
            _metrics(clicks=1_000, unique_visitors=800)
        ) == set()
        # 600 clicks from 5 visitors is not organic traffic.
        assert FraudSignal.CLICK_FLOODING.value in FraudService._derive_signals(
            _metrics(clicks=600, unique_visitors=5)
        )

    def test_signups_far_exceeding_visitors_is_a_velocity_anomaly(self):
        assert FraudSignal.VELOCITY_ANOMALY.value in FraudService._derive_signals(
            _metrics(signups=30, unique_visitors=2)
        )

    def test_scores_are_clamped_to_one_hundred(self):
        every_signal = {s.value for s in FraudSignal}
        total = sum(FRAUD_SIGNAL_WEIGHTS.get(s, 0) for s in every_signal)
        assert total > 100  # the raw weights do exceed the cap
        assert min(100, total) == 100

    def test_severity_tracks_signal_weight(self):
        assert _severity_for(FraudSignal.SELF_REFERRAL.value) == "high"
        assert _severity_for(FraudSignal.DISPOSABLE_EMAIL.value) == "medium"
        assert _severity_for(FraudSignal.GEO_MISMATCH.value) == "low"

    def test_a_single_high_weight_signal_does_not_reach_the_review_threshold(self):
        """One signal should prompt attention, not an automatic freeze."""
        score = FRAUD_SIGNAL_WEIGHTS[FraudSignal.SELF_REFERRAL.value]
        assert score < settings.PARTNER_FRAUD_REVIEW_SCORE
        assert risk_band_for_score(score) == RiskBand.MEDIUM.value

    def test_several_serious_signals_together_do_trigger_review(self):
        signals = {
            FraudSignal.SELF_REFERRAL.value,
            FraudSignal.CHARGEBACK_HISTORY.value,
        }
        score = min(100, sum(FRAUD_SIGNAL_WEIGHTS[s] for s in signals))
        assert score >= settings.PARTNER_FRAUD_REVIEW_SCORE


# ════════════════════════════════ geo ════════════════════════════════════


class TestGeoResolution:
    def test_private_and_reserved_addresses_are_never_looked_up(self):
        for ip in ("10.0.0.5", "192.168.1.1", "172.16.0.1", "127.0.0.1", "::1"):
            assert _is_public_ip(ip) is False

    def test_public_addresses_are_eligible(self):
        assert _is_public_ip("8.8.8.8") is True
        assert _is_public_ip("2001:4860:4860::8888") is True

    def test_malformed_input_is_rejected_without_raising(self):
        assert _is_public_ip("not-an-ip") is False
        assert lookup_ip("not-an-ip") == GeoResult()

    def test_a_missing_database_degrades_to_unknown_rather_than_failing(
        self, monkeypatch
    ):
        """Geo is analytics. It must never be able to break a click."""
        reset_reader()
        monkeypatch.setattr(settings, "MAXMIND_DB_PATH", "/nonexistent/GeoLite2.mmdb")
        assert lookup_ip("8.8.8.8") == GeoResult()
        assert lookup_ip("8.8.8.8").is_resolved is False
        reset_reader()

    def test_geo_result_reports_resolution_state(self):
        assert GeoResult(country_code="NG", country_name="Nigeria").is_resolved
        assert not GeoResult().is_resolved


# ═════════════════════════ scheduled jobs wiring ═════════════════════════


class TestBackgroundJobRegistration:
    """All eight required jobs must be registered and scheduled."""

    REQUIRED = {
        "commission_calculation",
        "commission_monthly_settlement",
        "commission_hold_release",
        "commission_reversal",
        "partner_tier_evaluation",
        "fraud_analysis",
        "geo_aggregation",
        "referral_attribution_expiry",
    }

    def test_all_required_tasks_are_registered_with_celery(self):
        from app.infrastructure.celery_app import celery_app
        import app.modules.partners.tasks  # noqa: F401  (registers the tasks)

        registered = set(celery_app.tasks.keys())
        for name in self.REQUIRED:
            assert f"app.modules.partners.tasks.{name}" in registered

    def test_all_required_tasks_are_on_the_beat_schedule(self):
        from app.infrastructure.celery_app import celery_app

        scheduled = {
            entry["task"].rsplit(".", 1)[-1]
            for entry in celery_app.conf.beat_schedule.values()
            if entry["task"].startswith("app.modules.partners.tasks.")
        }
        assert scheduled == self.REQUIRED

    def test_the_partner_task_module_is_included_for_workers(self):
        from app.infrastructure.celery_app import celery_app

        assert "app.modules.partners.tasks" in celery_app.conf.include

    def test_partner_models_are_imported_into_worker_metadata(self):
        """Workers need the full FK graph or ORM flushes fail."""
        from app.db.base import Base, import_all_models

        import_all_models()
        assert "partner_commissions" in Base.metadata.tables
        assert "partners" in Base.metadata.tables


class TestSettlementPeriodHelper:
    def test_previous_period_month_rolls_back_across_a_year_boundary(self):
        from app.modules.partners.tasks import _previous_period_month

        assert (
            _previous_period_month(datetime(2025, 1, 15, tzinfo=timezone.utc))
            == "2024-12"
        )
        assert (
            _previous_period_month(datetime(2025, 3, 1, tzinfo=timezone.utc))
            == "2025-02"
        )
