"""Background jobs for the Partner Network.

All settlement, hold-release, reversal, tier and fraud work happens here
rather than in request handlers: these are long-running, batched and
scheduled operations, and none of them should ever be tied to a user's HTTP
request.

Each task follows the platform's established pattern — a synchronous Celery
entry point wrapping an ``async def _run(session)`` handed to
:func:`app.infrastructure.async_tasks.async_task_body`, which owns the
session and the transaction boundary.

Scheduled in :mod:`app.infrastructure.celery_app`:

===========================  ==========================================
``commission_calculation``   Sweep for missed accruals (safety net).
``commission_hold_release``  pending → payable once the hold elapses.
``commission_monthly_...``   Close the previous month per partner.
``commission_reversal``      Retry/finalise pending reversals.
``partner_tier_evaluation``  Recompute earned tiers from ledger metrics.
``fraud_analysis``           Score active partners, raise flags.
``geo_aggregation``          Roll clicks/conversions into country daily.
``referral_attribution_...`` Expire unconverted touches past the window.
===========================  ==========================================
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _previous_period_month(reference: datetime | None = None) -> str:
    """``YYYY-MM`` of the month before ``reference`` (default: now)."""
    reference = reference or _now()
    first_of_month = reference.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    previous = first_of_month - timedelta(days=1)
    return f"{previous.year:04d}-{previous.month:02d}"


# ═════════════════════════ Commission lifecycle ══════════════════════════


@celery_app.task(name="app.modules.partners.tasks.commission_calculation")
def commission_calculation(lookback_hours: int = 48) -> int:
    """Safety net for commission accrual.

    Commissions are normally created synchronously when Paystack confirms a
    payment. Webhooks do occasionally get lost (delivery failure, a deploy
    mid-flight, a transient DB error), so this job re-checks recently
    started subscription periods that belong to a partner-owned customer and
    have no commission recorded.

    Crucially, it does **not** infer an amount from the plan's list price.
    It re-verifies the transaction with Paystack and uses the amount the
    provider reports as actually collected; if that cannot be established,
    the gap is logged for an operator rather than guessed at. Recording is
    idempotent, so an already-processed payment is a no-op.
    """

    async def _run(session) -> int:
        from sqlalchemy import select

        from app.config import settings
        from app.modules.billing.models import Subscription
        from app.modules.billing.service import paystack_client
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.repository import (
            CommissionRepository,
            RelationshipRepository,
        )

        since = _now() - timedelta(hours=lookback_hours)
        result = await session.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.current_period_start.isnot(None),
                Subscription.current_period_start >= since,
            )
        )
        subscriptions = list(result.scalars().all())

        recovered = 0
        for subscription in subscriptions:
            org_id = subscription.organization_id
            reference = subscription.provider_subscription_id
            if not reference:
                continue

            relationships = await RelationshipRepository.list_active_for_org(
                session, org_id
            )
            if not relationships:
                continue

            already = await CommissionRepository.list_for_source(
                session, source_reference=str(reference)
            )
            if already:
                continue

            if not settings.PAYSTACK_SECRET_KEY:
                logger.warning(
                    "Missing commission for org %s reference %s but Paystack is "
                    "not configured; skipping rather than assuming an amount",
                    org_id,
                    reference,
                )
                continue

            try:
                verified = await paystack_client.verify_transaction(str(reference))
            except Exception:
                logger.warning(
                    "Could not re-verify transaction %s for commission recovery",
                    reference,
                )
                continue

            data = verified.get("data") if isinstance(verified.get("data"), dict) else {}
            if not verified.get("status") or data.get("status") != "success":
                continue

            collected = data.get("amount")
            if not collected:
                continue

            created = await commission_service.record_payment(
                session,
                organization_id=org_id,
                collected_minor=int(collected),
                currency=str(data.get("currency") or "USD").upper()[:3],
                payment_reference=str(reference),
                paid_at=subscription.current_period_start,
            )
            recovered += len(created)

        if recovered:
            logger.info("commission_calculation recovered %d commissions", recovered)
        return recovered

    return async_task_body(_run)


@celery_app.task(name="app.modules.partners.tasks.commission_hold_release")
def commission_hold_release(batch_size: int = 1000) -> int:
    """Promote pending commissions to payable once the hold has elapsed.

    Partners under fraud review or suspension are skipped — their entries
    move to ``held`` instead, so a review can never be outrun by the clock.
    """

    async def _run(session) -> int:
        from app.modules.partners.commissions import commission_service

        released = await commission_service.release_due_holds(
            session, limit=batch_size
        )
        if released:
            logger.info("Released %d commissions to payable", released)
        return released

    return async_task_body(_run)


@celery_app.task(name="app.modules.partners.tasks.commission_monthly_settlement")
def commission_monthly_settlement(period_month: str | None = None) -> int:
    """Close the previous month for every partner with activity.

    Settlements are a derived view over the immutable ledger, so re-running
    this for a closed period recomputes the same numbers rather than
    creating a second record.
    """

    async def _run(session) -> int:
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.repository import CommissionRepository

        period = period_month or _previous_period_month()
        partner_ids = await CommissionRepository.partners_with_activity_in_period(
            session, period
        )
        for partner_id in partner_ids:
            try:
                await commission_service.settle_period(
                    session, partner_id=partner_id, period_month=period
                )
            except Exception:
                logger.exception(
                    "Settlement failed for partner %s period %s", partner_id, period
                )
        logger.info("Settled %d partners for %s", len(partner_ids), period)
        return len(partner_ids)

    return async_task_body(_run)


@celery_app.task(name="app.modules.partners.tasks.commission_reversal")
def commission_reversal(batch_size: int = 500) -> int:
    """Close out relationships whose earning window or lifecycle has ended.

    Refunds and chargebacks are reversed synchronously from the billing
    webhook. This job handles the time-based half: expiring Year-1
    ``introduce`` relationships so they stop accruing.

    Note that churn does *not* reverse past commissions — revenue that was
    genuinely collected and kept was genuinely earned.
    """

    async def _run(session) -> int:
        from app.modules.partners.commissions import commission_service

        expired = await commission_service.expire_relationships(
            session, limit=batch_size
        )
        if expired:
            logger.info("Expired %d partner relationships", expired)
        return expired

    return async_task_body(_run)


# ═════════════════════════════ Partner care ══════════════════════════════


@celery_app.task(name="app.modules.partners.tasks.partner_tier_evaluation")
def partner_tier_evaluation(batch_size: int = 500) -> int:
    """Recompute earned tiers from ledger-backed metrics.

    Promotion only — automated demotion is deliberately not implemented.
    """

    async def _run(session) -> int:
        from app.modules.partners.repository import PartnerRepository
        from app.modules.partners.service import partner_service

        partner_ids = await PartnerRepository.list_active_ids(session)
        promoted = 0
        for partner_id in partner_ids[:batch_size]:
            partner = await PartnerRepository.get_by_id(session, partner_id)
            if partner is None:
                continue
            try:
                entry = await partner_service.evaluate_tier(session, partner)
                if entry is not None:
                    promoted += 1
            except Exception:
                logger.exception("Tier evaluation failed for partner %s", partner_id)
        logger.info(
            "Tier evaluation: %d partners checked, %d promoted",
            len(partner_ids),
            promoted,
        )
        return promoted

    return async_task_body(_run)


@celery_app.task(name="app.modules.partners.tasks.fraud_analysis")
def fraud_analysis(batch_size: int = 500) -> int:
    """Score active partners and raise flags for human review.

    High scores hold commissions (recoverable, in-ledger) and open a flag.
    Nothing here suspends a partner or bans a user; those remain explicit
    admin decisions.
    """

    async def _run(session) -> int:
        from app.modules.partners.fraud import fraud_service

        assessed = await fraud_service.assess_all(session, limit=batch_size)
        logger.info("Risk assessment completed for %d partners", assessed)
        return assessed

    return async_task_body(_run)


# ═══════════════════════════ Attribution & geo ═══════════════════════════


@celery_app.task(name="app.modules.partners.tasks.referral_attribution_expiry")
def referral_attribution_expiry(batch_size: int = 5000) -> int:
    """Expire attribution touches that passed their window unconverted.

    Keeps the last-touch lookup fast and makes "who owns this visitor?"
    answerable without evaluating the window on every read.
    """

    async def _run(session) -> int:
        from app.modules.partners.tracking import tracking_service

        expired = await tracking_service.expire_stale_attributions(
            session, limit=batch_size
        )
        if expired:
            logger.info("Expired %d partner attributions", expired)
        return expired

    return async_task_body(_run)


@celery_app.task(name="app.modules.partners.tasks.geo_aggregation")
def geo_aggregation(target_day: str | None = None) -> int:
    """Roll one day of clicks and commissions into per-country daily rows.

    Writes both platform-wide rows (``partner_id IS NULL``) and per-partner
    rows, so country analytics never has to scan raw click events. Country
    granularity only — no city, region or coordinates are stored anywhere.
    """

    async def _run(session) -> int:
        from sqlalchemy import func, select

        from app.modules.partners.models import PartnerClickEvent, PartnerCommission
        from app.modules.partners.repository import GeoRepository

        if target_day:
            day = date.fromisoformat(target_day)
        else:
            day = (_now() - timedelta(days=1)).date()

        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        # Clicks per (country, partner), excluding duplicates and bots so the
        # aggregates match what partners see in their own analytics.
        click_rows = await session.execute(
            select(
                PartnerClickEvent.country_code,
                func.max(PartnerClickEvent.country_name),
                PartnerClickEvent.partner_id,
                func.count(PartnerClickEvent.id),
                func.count(func.distinct(PartnerClickEvent.visitor_id)),
            )
            .where(
                PartnerClickEvent.created_at >= start,
                PartnerClickEvent.created_at < end,
                PartnerClickEvent.country_code.isnot(None),
                PartnerClickEvent.is_duplicate.is_(False),
                PartnerClickEvent.is_bot.is_(False),
            )
            .group_by(PartnerClickEvent.country_code, PartnerClickEvent.partner_id)
        )

        buckets: dict[tuple[str, object], dict] = {}

        def _bucket(country: str, partner_id, country_name: str | None) -> dict:
            key = (country, partner_id)
            if key not in buckets:
                buckets[key] = {
                    "country_name": country_name,
                    "clicks": 0,
                    "uniques": 0,
                    "signups": 0,
                    "conversions": 0,
                    "revenue": 0,
                    "commission": 0,
                    "currency": "USD",
                }
            if country_name and not buckets[key]["country_name"]:
                buckets[key]["country_name"] = country_name
            return buckets[key]

        for country, country_name, partner_id, clicks, uniques in click_rows.all():
            for pid in (partner_id, None):
                bucket = _bucket(country, pid, country_name)
                bucket["clicks"] += int(clicks)
                bucket["uniques"] += int(uniques)

        # Commissions carry no country of their own; attribute them via the
        # attribution row's captured country.
        from app.modules.partners.models import PartnerAttribution

        commission_rows = await session.execute(
            select(
                PartnerAttribution.country_code,
                PartnerCommission.partner_id,
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.source_amount_minor), 0),
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
                func.max(PartnerCommission.currency),
            )
            .join(
                PartnerAttribution,
                PartnerAttribution.organization_id == PartnerCommission.organization_id,
            )
            .where(
                PartnerCommission.earned_at >= start,
                PartnerCommission.earned_at < end,
                PartnerAttribution.country_code.isnot(None),
            )
            .group_by(PartnerAttribution.country_code, PartnerCommission.partner_id)
        )

        for country, partner_id, count, revenue, commission, currency in (
            commission_rows.all()
        ):
            for pid in (partner_id, None):
                bucket = _bucket(country, pid, None)
                bucket["conversions"] += int(count)
                bucket["revenue"] += int(revenue)
                bucket["commission"] += int(commission)
                if currency:
                    bucket["currency"] = currency

        for (country, partner_id), values in buckets.items():
            await GeoRepository.upsert_daily(
                session,
                day=day,
                country_code=country,
                partner_id=partner_id,
                country_name=values["country_name"],
                click_count=values["clicks"],
                unique_visitor_count=values["uniques"],
                signup_count=values["signups"],
                conversion_count=values["conversions"],
                revenue_minor=values["revenue"],
                commission_minor=values["commission"],
                currency=values["currency"],
            )

        logger.info("Geo aggregation for %s wrote %d rows", day, len(buckets))
        return len(buckets)

    return async_task_body(_run)


__all__ = [
    "commission_calculation",
    "commission_hold_release",
    "commission_monthly_settlement",
    "commission_reversal",
    "fraud_analysis",
    "geo_aggregation",
    "partner_tier_evaluation",
    "referral_attribution_expiry",
]
