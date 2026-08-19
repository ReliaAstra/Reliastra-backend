"""Commission service for the Partner Referral program (v1).

Responsibilities:

* determine eligible revenue (the amount actually collected),
* calculate the 30% (configurable) commission with integer arithmetic,
* create the ledger entry idempotently,
* handle refunds / chargebacks / churn,
* expose balance summaries.

Commission is only ever created from a *confirmed* billing event — never
from a signup or a subscription that has not yet been paid for.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException
from app.modules.partners.constants import (
    CommissionStatus,
    EARNING_STATUSES,
    ReferralStatus,
    ReversalReason,
)
from app.modules.partners.repository import (
    PartnerCommissionRepository,
    PartnerProfileRepository,
    PartnerReferralRepository,
)
from app.modules.partners.service import apply_rate, _period_month
from app.modules.organizations.repository import OrganizationRepository

logger = logging.getLogger(__name__)


class CommissionService:
    def __init__(self) -> None:
        self.commission_repo = PartnerCommissionRepository()
        self.referral_repo = PartnerReferralRepository()
        self.profile_repo = PartnerProfileRepository()

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
    ) -> None:
        """Convert one confirmed payment into at most one commission.

        Idempotent on ``(payment_reference, partner_id)``: a duplicate
        delivery of the same billing event can never pay a partner twice
        (backed by a database unique constraint).
        """
        if not payment_reference or collected_minor <= 0:
            return

        # Resolve the referred customer from the paying organization's owner.
        owner = await self._org_owner(session, organization_id)
        if owner is None:
            return
        referral = await self.referral_repo.get_by_referred_user(session, owner)
        if referral is None:
            return
        if referral.status == ReferralStatus.CHURNED.value:
            return

        partner = await self.profile_repo.get_by_id(session, referral.partner_id)
        if partner is None or partner.status not in EARNING_STATUSES:
            return

        existing = await self.commission_repo.get_by_billing_event(
            session, payment_reference, partner.id
        )
        if existing is not None:
            return

        now = datetime.now(timezone.utc)
        event_at = paid_at or now
        rate = int(settings.PARTNER_COMMISSION_RATE)
        amount = apply_rate(int(collected_minor), rate)
        if amount <= 0:
            return

        payable_at = event_at + timedelta(
            days=int(settings.PARTNER_COMMISSION_HOLD_DAYS)
        )

        # First confirmed payment promotes the referral to a paying customer.
        if referral.status == ReferralStatus.SIGNED_UP.value:
            await self.referral_repo.update(
                session,
                referral,
                status=ReferralStatus.PAID.value,
                subscribed_at=event_at,
            )

        commission = await self.commission_repo.create(
            session,
            partner_id=partner.id,
            referral_id=referral.id,
            billing_event_id=payment_reference,
            period=_period_month(event_at),
            subscription_amount_minor=int(collected_minor),
            commission_amount_minor=amount,
            currency=currency[:3].upper() or settings.PARTNER_DEFAULT_CURRENCY,
            rate=rate,
            payable_at=payable_at,
        )
        await AuditLogService.log_event(
            session=session,
            event_type="partner_commission_created",
            user_id=partner.user_id,
            resource_type="partner_commission",
            resource_id=str(commission.id),
            payload={
                "partner_id": str(partner.id),
                "referral_id": str(referral.id),
                "billing_event_id": payment_reference,
                "amount_minor": amount,
                "currency": currency,
                "rate": rate,
                "payment_provider": payment_provider,
            },
        )
        logger.info(
            "Commission created: partner=%s billing_event=%s amount=%s %s",
            partner.id,
            payment_reference,
            amount,
            currency,
        )

    async def reverse_by_reference(
        self,
        session: AsyncSession,
        payment_reference: str,
        reason: str,
    ) -> int:
        """Reverse all commissions tied to a refunded/charge-backed payment.

        The original commission rows are never deleted — their status is set
        to ``reversed`` and ``reversal_reason`` recorded. Returns the number
        of commissions reversed.
        """
        if not payment_reference:
            return 0
        from sqlalchemy import select

        from app.modules.partners.models import PartnerCommission

        rows = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.billing_event_id == payment_reference,
                PartnerCommission.status != CommissionStatus.REVERSED.value,
            )
        )
        commissions = list(rows.scalars().all())
        count = 0
        for commission in commissions:
            await self.commission_repo.update(
                session,
                commission,
                status=CommissionStatus.REVERSED.value,
                reversal_reason=reason,
                payout_id=None,
            )
            count += 1
        return count

    async def reverse_commission(
        self, session: AsyncSession, commission_id: uuid.UUID, reason: str
    ) -> None:
        """Admin-initiated reversal of a single commission."""
        commission = await self.commission_repo.get_by_id(session, commission_id)
        if commission is None:
            raise ResourceNotFoundException("Commission not found")
        if commission.status == CommissionStatus.REVERSED.value:
            return
        await self.commission_repo.update(
            session,
            commission,
            status=CommissionStatus.REVERSED.value,
            reversal_reason=reason or ReversalReason.ADMIN.value,
            payout_id=None,
        )
        await AuditLogService.log_event(
            session=session,
            event_type="partner_commission_reversed",
            resource_type="partner_commission",
            resource_id=str(commission.id),
            payload={"reason": reason},
        )

    async def handle_churn(
        self, session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        """Mark the referred customer as churned — future commission stops.

        Historical commissions remain valid; only future accrual stops.
        """
        owner = await self._org_owner(session, organization_id)
        if owner is None:
            return
        referral = await self.referral_repo.get_by_referred_user(session, owner)
        if referral is None or referral.status == ReferralStatus.CHURNED.value:
            return
        await self.referral_repo.update(
            session, referral, status=ReferralStatus.CHURNED.value
        )
        logger.info("Partner referral churned: %s", referral.id)

    async def release_payable(self, session: AsyncSession) -> int:
        """Promote pending commissions whose hold has elapsed to payable."""
        now = datetime.now(timezone.utc)
        pending = await self.commission_repo.pending_past_hold(session, now)
        count = 0
        for commission in pending:
            await self.commission_repo.update(
                session, commission, status=CommissionStatus.PAYABLE.value
            )
            count += 1
        return count

    async def _org_owner(
        self, session: AsyncSession, organization_id: uuid.UUID
    ) -> uuid.UUID | None:
        members = await OrganizationRepository.list_members(session, organization_id)
        owner = next((m for m in members if m.role == "owner"), None)
        return owner.user_id if owner else None


commission_service = CommissionService()
