"""Commission ledger service.

This is the financial heart of the partner network, and it is deliberately
conservative:

* **Append-only.** Money is never edited in place. A refund produces a new
  negative ``reversal`` row pointing at the original via ``reverses_id``; the
  original keeps its amount forever.
* **Idempotent.** Every accrual is keyed by
  ``(partner_id, entry_type, idempotency_key)`` with a database unique
  constraint. A replayed Paystack webhook, a retried Celery task and a double
  click on "verify" all converge on exactly one ledger row.
* **Actual revenue only.** The base is the amount the payment provider
  reports as collected, never a plan list price.
* **Ceilinged.** The combined rate applied to a single payment can never
  exceed ``PARTNER_MAX_TOTAL_COMMISSION_BPS`` (50%), no matter how many
  partners have a claim on the customer.
* **Auditable.** Every status change writes a ``PartnerCommissionEvent``
  recording who/what moved it and why.

Arithmetic lives in :mod:`app.modules.partners.economics` (pure, unit-tested);
this module only orchestrates persistence and state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import ConflictException, ValidationException
from app.modules.partners import economics
from app.modules.partners.constants import (
    COMMISSION_TRANSITIONS,
    EARNING_STATUSES,
    CommissionStatus,
    HoldReason,
    LedgerEntryType,
    PartnerStatus,
    RelationshipStatus,
    ReversalReason,
)
from app.modules.partners.models import (
    Partner,
    PartnerCommission,
    PartnerCommissionEvent,
    PartnerCustomerRelationship,
    PartnerSettlement,
)
from app.modules.partners.repository import (
    CommissionRepository,
    PartnerRepository,
    RelationshipRepository,
    SettlementRepository,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class CommissionService:
    """Creates, transitions and reverses commission ledger entries."""

    # ─────────────────────────── accrual ─────────────────────────────

    async def record_payment(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        collected_minor: int,
        currency: str,
        payment_reference: str,
        paid_at: datetime | None = None,
        payment_provider: str = "paystack",
        tax_minor: int = 0,
        processing_fee_minor: int = 0,
    ) -> list[PartnerCommission]:
        """Fan a collected payment out to every partner owning the customer.

        This is the single entry point used by billing. It is safe to call
        repeatedly with the same ``payment_reference``: existing rows are
        returned rather than duplicated.

        Partners are processed oldest-relationship-first, and each one
        consumes part of the 50% ceiling, so an early relationship cannot be
        diluted by a later one.
        """
        if collected_minor <= 0:
            return []

        relationships = await RelationshipRepository.list_active_for_org(
            session, organization_id
        )
        if not relationships:
            return []

        event_at = _aware(paid_at) or _now()
        created: list[PartnerCommission] = []
        applied_bps = await CommissionRepository.applied_bps_for_payment(
            session, source_reference=payment_reference
        )

        for relationship in relationships:
            commission = await self._accrue_for_relationship(
                session,
                relationship=relationship,
                collected_minor=collected_minor,
                currency=currency,
                payment_reference=payment_reference,
                event_at=event_at,
                payment_provider=payment_provider,
                tax_minor=tax_minor,
                processing_fee_minor=processing_fee_minor,
                already_applied_bps=applied_bps,
            )
            if commission is not None:
                created.append(commission)
                applied_bps += commission.rate_bps

        return created

    async def _accrue_for_relationship(
        self,
        session: AsyncSession,
        *,
        relationship: PartnerCustomerRelationship,
        collected_minor: int,
        currency: str,
        payment_reference: str,
        event_at: datetime,
        payment_provider: str,
        tax_minor: int,
        processing_fee_minor: int,
        already_applied_bps: int,
    ) -> PartnerCommission | None:
        partner = await PartnerRepository.get_by_id(session, relationship.partner_id)
        if partner is None:
            return None

        idempotency_key = self.build_idempotency_key(
            payment_reference, relationship.id
        )
        existing = await CommissionRepository.get_by_idempotency_key(
            session,
            partner_id=partner.id,
            entry_type=LedgerEntryType.COMMISSION.value,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            logger.info(
                "Commission already recorded for payment %s / relationship %s",
                payment_reference,
                relationship.id,
            )
            return existing

        quote = economics.calculate_commission(
            earning_method=relationship.earning_method,
            collected_minor=collected_minor,
            currency=currency,
            relationship_started_at=_aware(relationship.started_at) or event_at,
            event_at=event_at,
            eligible_until=_aware(relationship.eligible_until),
            tax_minor=tax_minor,
            processing_fee_minor=processing_fee_minor,
            custom_rate_bps=partner.custom_rate_bps,
            relationship_rate_bps=relationship.rate_bps,
            already_applied_bps=already_applied_bps,
        )

        if quote.amount_minor <= 0:
            # Zero-value outcomes are expected (resell, expired Year-1
            # window, ceiling reached). We log rather than persist a
            # meaningless ledger row.
            logger.info(
                "No commission for relationship %s on payment %s: %s",
                relationship.id,
                payment_reference,
                quote.reason,
            )
            # An elapsed Year-1 window should also close the relationship.
            if quote.reason == "outside_earning_window":
                relationship.status = RelationshipStatus.EXPIRED.value
                relationship.ended_at = event_at
                relationship.end_reason = "earning_window_elapsed"
                await session.flush()
            return None

        # Money that would otherwise be payable is parked in `held` when the
        # partner is under review or not in good standing.
        hold_reason = self._hold_reason_for(partner)

        commission = PartnerCommission(
            partner_id=partner.id,
            relationship_id=relationship.id,
            organization_id=relationship.organization_id,
            campaign_id=relationship.campaign_id,
            entry_type=LedgerEntryType.COMMISSION.value,
            status=(
                CommissionStatus.HELD.value
                if hold_reason
                else CommissionStatus.PENDING.value
            ),
            earning_method=relationship.earning_method,
            source_amount_minor=collected_minor,
            commissionable_amount_minor=quote.commissionable_minor,
            rate_bps=quote.rate_bps,
            amount_minor=quote.amount_minor,
            currency=quote.currency,
            calculation_basis=quote.basis,
            idempotency_key=idempotency_key,
            source_type="payment",
            source_reference=payment_reference,
            payment_provider=payment_provider,
            period_month=economics.period_month(event_at),
            earned_at=event_at,
            hold_reason=hold_reason.value if hold_reason else None,
            payable_at=economics.hold_until(event_at),
        )

        try:
            await CommissionRepository.add(session, commission)
        except IntegrityError:
            # Lost a race with a concurrent webhook delivery; the other
            # writer's row is the canonical one.
            await session.rollback()
            existing = await CommissionRepository.get_by_idempotency_key(
                session,
                partner_id=partner.id,
                entry_type=LedgerEntryType.COMMISSION.value,
                idempotency_key=idempotency_key,
            )
            return existing

        await self._record_event(
            session,
            commission,
            from_status=None,
            to_status=commission.status,
            reason="commission_accrued",
            actor_type="system",
            context={
                "payment_reference": payment_reference,
                "rate_bps": quote.rate_bps,
            },
        )

        relationship.total_revenue_minor = (
            relationship.total_revenue_minor or 0
        ) + collected_minor
        relationship.total_commission_minor = (
            relationship.total_commission_minor or 0
        ) + quote.amount_minor

        await self.refresh_partner_aggregates(session, partner)

        await AuditLogService.log_event(
            session,
            event_type="partner.commission.accrued",
            org_id=relationship.organization_id,
            resource_type="partner_commission",
            resource_id=str(commission.id),
            payload={
                "partner_id": str(partner.id),
                "amount_minor": quote.amount_minor,
                "currency": quote.currency,
                "rate_bps": quote.rate_bps,
                "earning_method": relationship.earning_method,
            },
        )
        return commission

    @staticmethod
    def build_idempotency_key(
        payment_reference: str, relationship_id: uuid.UUID
    ) -> str:
        """One commission per (payment, relationship) — the durable guard
        against double-paying a partner for the same money."""
        return f"payment:{payment_reference}:rel:{relationship_id}"

    @staticmethod
    def _hold_reason_for(partner: Partner) -> HoldReason | None:
        if partner.status == PartnerStatus.SUSPENDED.value:
            return HoldReason.PARTNER_SUSPENDED
        if partner.commissions_held:
            return HoldReason.FRAUD_REVIEW
        return None

    # ──────────────────────── state transitions ──────────────────────

    async def transition(
        self,
        session: AsyncSession,
        commission: PartnerCommission,
        *,
        to_status: str,
        reason: str,
        actor_user_id: uuid.UUID | None = None,
        actor_type: str = "system",
        context: dict[str, Any] | None = None,
    ) -> PartnerCommission:
        """Move a commission through its lifecycle, or refuse.

        The allowed graph lives in ``COMMISSION_TRANSITIONS``; ``paid`` and
        ``reversed`` are terminal. Every accepted move is journalled.
        """
        current = commission.status
        allowed = COMMISSION_TRANSITIONS.get(current, frozenset())
        if to_status not in allowed:
            raise ConflictException(
                f"Cannot move a commission from {current} to {to_status}",
                details={"allowed": sorted(allowed), "commission_id": str(commission.id)},
            )

        now = _now()
        commission.status = to_status
        if to_status == CommissionStatus.PAYABLE.value:
            commission.became_payable_at = now
            commission.hold_reason = None
        elif to_status == CommissionStatus.HELD.value:
            commission.hold_reason = reason
        elif to_status == CommissionStatus.PAID.value:
            commission.paid_at = now
        elif to_status == CommissionStatus.REVERSED.value:
            commission.reversed_at = now

        await session.flush()
        await self._record_event(
            session,
            commission,
            from_status=current,
            to_status=to_status,
            reason=reason,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            context=context,
        )
        return commission

    async def _record_event(
        self,
        session: AsyncSession,
        commission: PartnerCommission,
        *,
        from_status: str | None,
        to_status: str,
        reason: str | None,
        actor_user_id: uuid.UUID | None = None,
        actor_type: str = "system",
        context: dict[str, Any] | None = None,
    ) -> PartnerCommissionEvent:
        return await CommissionRepository.add_event(
            session,
            PartnerCommissionEvent(
                commission_id=commission.id,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                actor_user_id=actor_user_id,
                actor_type=actor_type,
                context=context,
                created_at=_now(),
            ),
        )

    async def release_due_holds(
        self, session: AsyncSession, *, limit: int = 1000
    ) -> int:
        """Promote pending → payable once the holding period has elapsed.

        Partners who are suspended or under fraud review are skipped and
        their entries moved to ``held`` instead, so a review can never be
        outrun by the clock.
        """
        now = _now()
        due = await CommissionRepository.list_due_for_release(
            session, now=now, limit=limit
        )
        released = 0
        partner_cache: dict[uuid.UUID, Partner | None] = {}

        for commission in due:
            partner = partner_cache.get(commission.partner_id)
            if commission.partner_id not in partner_cache:
                partner = await PartnerRepository.get_by_id(
                    session, commission.partner_id
                )
                partner_cache[commission.partner_id] = partner
            if partner is None:
                continue

            hold_reason = self._hold_reason_for(partner)
            if hold_reason is not None:
                await self.transition(
                    session,
                    commission,
                    to_status=CommissionStatus.HELD.value,
                    reason=hold_reason.value,
                )
                continue

            await self.transition(
                session,
                commission,
                to_status=CommissionStatus.PAYABLE.value,
                reason="holding_period_elapsed",
            )
            released += 1

        return released

    async def hold_partner_commissions(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        reason: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> int:
        """Freeze all not-yet-paid commissions for a partner."""
        held = 0
        commissions, _ = await CommissionRepository.list_for_partner(
            session, partner.id, size=1000
        )
        for commission in commissions:
            if commission.status in {
                CommissionStatus.PENDING.value,
                CommissionStatus.PAYABLE.value,
            }:
                await self.transition(
                    session,
                    commission,
                    to_status=CommissionStatus.HELD.value,
                    reason=reason,
                    actor_user_id=actor_user_id,
                    actor_type="admin" if actor_user_id else "system",
                )
                held += 1
        partner.commissions_held = True
        await session.flush()
        return held

    async def release_partner_commissions(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        reason: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> int:
        """Unfreeze held commissions.

        Entries whose holding period has already elapsed go straight to
        ``payable``; the rest return to ``pending`` and finish their hold
        normally.
        """
        released = 0
        now = _now()
        partner.commissions_held = False
        commissions, _ = await CommissionRepository.list_for_partner(
            session, partner.id, status=CommissionStatus.HELD.value, size=1000
        )
        for commission in commissions:
            payable_at = _aware(commission.payable_at)
            target = (
                CommissionStatus.PAYABLE.value
                if payable_at is not None and payable_at <= now
                else CommissionStatus.PENDING.value
            )
            await self.transition(
                session,
                commission,
                to_status=target,
                reason=reason,
                actor_user_id=actor_user_id,
                actor_type="admin" if actor_user_id else "system",
            )
            released += 1
        await session.flush()
        return released

    # ─────────────────────────── reversals ───────────────────────────

    async def reverse_commission(
        self,
        session: AsyncSession,
        commission: PartnerCommission,
        *,
        reason: ReversalReason | str,
        refunded_minor: int | None = None,
        actor_user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> PartnerCommission | None:
        """Claw back a commission by writing a negative ledger entry.

        The original row is left untouched and simply marked ``reversed``;
        the money movement is expressed by a new row so the ledger's running
        sum stays correct and the history stays legible.

        Already-*paid* commissions are still reversed — the negative balance
        is recovered from the partner's next payout rather than being
        written off silently.
        """
        reason_value = reason.value if hasattr(reason, "value") else str(reason)

        if commission.entry_type != LedgerEntryType.COMMISSION.value:
            raise ValidationException("Only commission entries can be reversed")

        idempotency_key = f"reversal:{commission.id}:{reason_value}"
        existing = await CommissionRepository.get_by_idempotency_key(
            session,
            partner_id=commission.partner_id,
            entry_type=LedgerEntryType.REVERSAL.value,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing

        magnitude = economics.calculate_reversal(
            original_amount_minor=commission.amount_minor,
            refunded_minor=refunded_minor,
            original_commissionable_minor=commission.commissionable_amount_minor,
            rate_bps=commission.rate_bps,
        )
        if magnitude <= 0:
            return None

        now = _now()
        reversal = PartnerCommission(
            partner_id=commission.partner_id,
            relationship_id=commission.relationship_id,
            organization_id=commission.organization_id,
            campaign_id=commission.campaign_id,
            entry_type=LedgerEntryType.REVERSAL.value,
            status=CommissionStatus.REVERSED.value,
            earning_method=commission.earning_method,
            source_amount_minor=refunded_minor or commission.source_amount_minor,
            commissionable_amount_minor=commission.commissionable_amount_minor,
            rate_bps=commission.rate_bps,
            amount_minor=-magnitude,
            currency=commission.currency,
            calculation_basis={
                "reverses": str(commission.id),
                "reason": reason_value,
                "original_amount_minor": commission.amount_minor,
                "refunded_minor": refunded_minor,
                "is_partial": refunded_minor is not None
                and magnitude < abs(commission.amount_minor),
            },
            idempotency_key=idempotency_key,
            source_type="reversal",
            source_reference=commission.source_reference,
            payment_provider=commission.payment_provider,
            # Reversals land in the *current* period: a closed month is
            # never retroactively rewritten.
            period_month=economics.period_month(now),
            earned_at=now,
            reversed_at=now,
            reversal_reason=reason_value,
            reverses_id=commission.id,
            notes=notes,
        )
        await CommissionRepository.add(session, reversal)
        await self._record_event(
            session,
            reversal,
            from_status=None,
            to_status=CommissionStatus.REVERSED.value,
            reason=reason_value,
            actor_user_id=actor_user_id,
            actor_type="admin" if actor_user_id else "system",
            context={"reverses": str(commission.id)},
        )

        # Mark the original reversed when fully clawed back. A partial
        # reversal leaves the original in place: it still represents real,
        # partially-earned money.
        if magnitude >= abs(commission.amount_minor):
            if commission.status != CommissionStatus.REVERSED.value:
                allowed = COMMISSION_TRANSITIONS.get(commission.status, frozenset())
                if CommissionStatus.REVERSED.value in allowed:
                    await self.transition(
                        session,
                        commission,
                        to_status=CommissionStatus.REVERSED.value,
                        reason=reason_value,
                        actor_user_id=actor_user_id,
                        actor_type="admin" if actor_user_id else "system",
                    )
                else:
                    # Terminal (already paid): the negative entry carries the
                    # correction; the original stays 'paid' truthfully.
                    commission.reversal_reason = reason_value
                    await session.flush()

        if commission.relationship_id:
            relationship = await RelationshipRepository.get_by_id(
                session, commission.relationship_id
            )
            if relationship is not None:
                relationship.total_commission_minor = (
                    relationship.total_commission_minor or 0
                ) - magnitude

        partner = await PartnerRepository.get_by_id(session, commission.partner_id)
        if partner is not None:
            await self.refresh_partner_aggregates(session, partner)

        await AuditLogService.log_event(
            session,
            event_type="partner.commission.reversed",
            user_id=actor_user_id,
            org_id=commission.organization_id,
            resource_type="partner_commission",
            resource_id=str(reversal.id),
            payload={
                "reverses": str(commission.id),
                "amount_minor": -magnitude,
                "reason": reason_value,
            },
        )
        return reversal

    async def reverse_payment(
        self,
        session: AsyncSession,
        *,
        payment_reference: str,
        reason: ReversalReason | str,
        refunded_minor: int | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[PartnerCommission]:
        """Reverse every commission generated by one payment.

        Used for refunds and chargebacks, where the platform lost the
        revenue and therefore every partner's share of it.
        """
        originals = await CommissionRepository.list_for_source(
            session, source_reference=payment_reference
        )
        reversals: list[PartnerCommission] = []
        for original in originals:
            if original.status == CommissionStatus.REVERSED.value:
                continue
            share = None
            if refunded_minor is not None and original.source_amount_minor:
                # Distribute a partial refund proportionally to each
                # partner's share of the same payment.
                share = min(refunded_minor, original.source_amount_minor)
            reversal = await self.reverse_commission(
                session,
                original,
                reason=reason,
                refunded_minor=share,
                actor_user_id=actor_user_id,
            )
            if reversal is not None:
                reversals.append(reversal)
        return reversals

    async def handle_churn(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        occurred_at: datetime | None = None,
    ) -> int:
        """Close relationships when a customer churns.

        Churn stops *future* accrual. It does not reverse commissions on
        revenue that was genuinely collected and kept — that money was
        earned.
        """
        now = _aware(occurred_at) or _now()
        relationships = await RelationshipRepository.list_active_for_org(
            session, organization_id
        )
        for relationship in relationships:
            relationship.status = RelationshipStatus.CHURNED.value
            relationship.ended_at = now
            relationship.end_reason = "customer_churned"
        await session.flush()

        for relationship in relationships:
            partner = await PartnerRepository.get_by_id(
                session, relationship.partner_id
            )
            if partner is not None:
                partner.active_customer_count = (
                    await RelationshipRepository.count_active(session, partner.id)
                )
        return len(relationships)

    async def expire_relationships(
        self, session: AsyncSession, *, limit: int = 1000
    ) -> int:
        """Close Year-1 relationships whose earning window has elapsed."""
        now = _now()
        expiring = await RelationshipRepository.list_expiring(
            session, now=now, limit=limit
        )
        for relationship in expiring:
            relationship.status = RelationshipStatus.EXPIRED.value
            relationship.ended_at = now
            relationship.end_reason = "earning_window_elapsed"
        await session.flush()
        return len(expiring)

    # ────────────────────────── adjustments ──────────────────────────

    async def create_adjustment(
        self,
        session: AsyncSession,
        *,
        partner: Partner,
        amount_minor: int,
        currency: str,
        reason: str,
        actor_user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> PartnerCommission:
        """Manual admin correction, recorded as its own ledger entry.

        Adjustments are immediately payable — they exist precisely to fix
        something already reviewed by a human — but they are never silent:
        the reason and the actor are stored on the row and in the audit log.
        """
        if amount_minor == 0:
            raise ValidationException("An adjustment must be non-zero")

        now = _now()
        idempotency_key = f"adjustment:{uuid.uuid4()}"
        adjustment = PartnerCommission(
            partner_id=partner.id,
            organization_id=organization_id,
            entry_type=LedgerEntryType.ADJUSTMENT.value,
            status=CommissionStatus.PAYABLE.value,
            source_amount_minor=0,
            commissionable_amount_minor=0,
            rate_bps=0,
            amount_minor=amount_minor,
            currency=currency.upper(),
            calculation_basis={"type": "manual_adjustment", "reason": reason},
            idempotency_key=idempotency_key,
            source_type="adjustment",
            period_month=economics.period_month(now),
            earned_at=now,
            became_payable_at=now,
            notes=reason,
        )
        await CommissionRepository.add(session, adjustment)
        await self._record_event(
            session,
            adjustment,
            from_status=None,
            to_status=CommissionStatus.PAYABLE.value,
            reason=reason,
            actor_user_id=actor_user_id,
            actor_type="admin",
        )
        await self.refresh_partner_aggregates(session, partner)
        await AuditLogService.log_event(
            session,
            event_type="partner.commission.adjusted",
            user_id=actor_user_id,
            resource_type="partner_commission",
            resource_id=str(adjustment.id),
            payload={"amount_minor": amount_minor, "reason": reason},
        )
        return adjustment

    # ─────────────────────────── settlement ──────────────────────────

    async def settle_period(
        self,
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        period_month: str,
    ) -> PartnerSettlement:
        """Close one partner-month.

        Idempotent: re-running for a closed period recomputes and updates the
        same settlement row rather than creating a second one. Settlements
        are a *view* over the ledger — recomputing them can never change what
        the partner earned.
        """
        totals = await CommissionRepository.period_totals(
            session, partner_id, period_month
        )
        gross = reversal_total = adjustment_total = revenue = 0
        count = 0
        breakdown: dict[str, dict[str, int]] = {}

        for entry_type, amount, entries, source in totals:
            breakdown[entry_type] = {"amount_minor": amount, "count": entries}
            count += entries
            if entry_type == LedgerEntryType.COMMISSION.value:
                gross += amount
                revenue += source
            elif entry_type == LedgerEntryType.REVERSAL.value:
                reversal_total += amount
            elif entry_type == LedgerEntryType.ADJUSTMENT.value:
                adjustment_total += amount

        partner = await PartnerRepository.get_by_id(session, partner_id)
        currency = partner.payout_currency if partner else settings.PARTNER_DEFAULT_CURRENCY

        settlement = await SettlementRepository.get(session, partner_id, period_month)
        if settlement is None:
            settlement = PartnerSettlement(
                partner_id=partner_id, period_month=period_month
            )
            await SettlementRepository.add(session, settlement)

        settlement.currency = currency
        settlement.gross_commission_minor = gross
        settlement.reversal_minor = reversal_total
        settlement.adjustment_minor = adjustment_total
        settlement.net_commission_minor = gross + reversal_total + adjustment_total
        settlement.commission_count = count
        settlement.revenue_minor = revenue
        settlement.breakdown = breakdown
        settlement.status = "closed"
        settlement.closed_at = _now()
        await session.flush()
        return settlement

    # ─────────────────────────── aggregates ──────────────────────────

    async def refresh_partner_aggregates(
        self, session: AsyncSession, partner: Partner
    ) -> Partner:
        """Recompute the cached counters on ``partners`` from the ledger.

        These are a convenience for listing screens only. Anything that
        matters financially is read from ``partner_commissions`` directly.
        """
        revenue, commission = await CommissionRepository.lifetime_totals(
            session, partner.id
        )
        partner.lifetime_revenue_minor = revenue
        partner.lifetime_commission_minor = commission
        partner.active_customer_count = await RelationshipRepository.count_active(
            session, partner.id
        )
        partner.aggregates_updated_at = _now()
        await session.flush()
        return partner

    async def balance(
        self, session: AsyncSession, partner: Partner
    ) -> dict[str, Any]:
        """Ledger-derived balance summary for the partner UI/API."""
        balances = await CommissionRepository.balance_by_status(session, partner.id)
        payable = balances.get(CommissionStatus.PAYABLE.value, 0)
        minimum = economics.payout_minimum_minor(partner.min_payout_minor)
        _, lifetime = await CommissionRepository.lifetime_totals(session, partner.id)
        return {
            "currency": partner.payout_currency,
            "pending_minor": balances.get(CommissionStatus.PENDING.value, 0),
            "held_minor": balances.get(CommissionStatus.HELD.value, 0),
            "payable_minor": payable,
            "paid_minor": balances.get(CommissionStatus.PAID.value, 0),
            "reversed_minor": balances.get(CommissionStatus.REVERSED.value, 0),
            "lifetime_minor": lifetime,
            "min_payout_minor": minimum,
            "can_request_payout": (
                payable >= minimum
                and not partner.commissions_held
                and partner.status in EARNING_STATUSES
            ),
            "next_release_at": await CommissionRepository.next_release_at(
                session, partner.id
            ),
        }


commission_service = CommissionService()

__all__ = ["CommissionService", "commission_service"]
