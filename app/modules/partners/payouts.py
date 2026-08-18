"""Partner payout service.

Payouts move real money, so this module is written defensively:

* **Idempotent by construction.** A payout carries a caller-supplied (or
  derived) ``idempotency_key`` protected by a database unique constraint on
  ``(partner_id, idempotency_key)``. The Redis-backed
  ``IdempotencyMiddleware`` fails open when Redis is unavailable, so the DB
  constraint — not the middleware — is what actually prevents double
  payment.
* **Pay-once commissions.** ``partner_payout_items.commission_id`` is unique
  platform-wide, so a commission physically cannot be included in two
  payouts. Payable rows are additionally selected ``FOR UPDATE SKIP LOCKED``.
* **Amounts are derived, never supplied.** The payout total is summed from
  the ledger inside the transaction; a client cannot request an arbitrary
  sum.
* **No new payment abstraction.** Transfers go through the existing
  :class:`app.modules.billing.service.PaystackClient`, extended with the
  transfer endpoints rather than replaced.
* **Details encrypted, responses masked.** Account data is Fernet-encrypted
  with the platform helpers and never logged or returned.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import AuditLogService
from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.core.security import encrypt_jsonb
from app.modules.billing.service import PaystackClient
from app.modules.partners import economics
from app.modules.partners.constants import (
    EARNING_STATUSES,
    PAYOUT_TRANSITIONS,
    CommissionStatus,
    LedgerEntryType,
    PayoutMethod,
    PayoutStatus,
)
from app.modules.partners.commissions import commission_service
from app.modules.partners.models import (
    Partner,
    PartnerPayout,
    PartnerPayoutAccount,
    PartnerPayoutItem,
)
from app.modules.partners.repository import (
    CommissionRepository,
    PayoutAccountRepository,
    PayoutRepository,
)
from app.modules.partners.schemas import PayoutAccountCreate
from app.modules.partners.utils import (
    account_last4,
    build_payout_label,
    generate_reference,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PartnerPaystackClient(PaystackClient):
    """Transfer endpoints layered onto the existing Paystack client.

    Extending the platform's single Paystack client keeps configuration,
    auth and error handling in one place — this is not a second payment
    abstraction.
    """

    async def create_transfer_recipient(
        self,
        *,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/transferrecipient",
                headers=self._headers(),
                json={
                    "type": "nuban",
                    "name": name,
                    "account_number": account_number,
                    "bank_code": bank_code,
                    "currency": currency,
                },
            )
            response.raise_for_status()
            return response.json()

    async def initiate_transfer(
        self,
        *,
        amount: int,
        recipient_code: str,
        reason: str,
        reference: str,
        currency: str,
    ) -> dict[str, Any]:
        """Initiate a transfer.

        ``reference`` is our payout reference, which makes the call itself
        idempotent on Paystack's side as well as ours.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/transfer",
                headers=self._headers(),
                json={
                    "source": "balance",
                    "amount": amount,
                    "recipient": recipient_code,
                    "reason": reason,
                    "reference": reference,
                    "currency": currency,
                },
            )
            response.raise_for_status()
            return response.json()


partner_paystack_client = PartnerPaystackClient()


class PayoutService:
    def __init__(self, client: PartnerPaystackClient | None = None) -> None:
        self.client = client or partner_paystack_client

    # ────────────────────────── payout accounts ──────────────────────

    async def add_account(
        self,
        session: AsyncSession,
        partner: Partner,
        payload: PayoutAccountCreate,
    ) -> PartnerPayoutAccount:
        """Store payout details encrypted at rest.

        Only ``account_last4`` and a display label survive in plaintext. The
        raw account number is never logged — not even at DEBUG.
        """
        details = {
            "account_name": payload.account_name,
            "account_number": payload.account_number,
            "bank_code": payload.bank_code,
            "bank_name": payload.bank_name,
            **(payload.details or {}),
        }

        account = PartnerPayoutAccount(
            partner_id=partner.id,
            method=payload.method.value,
            currency=payload.currency.upper(),
            country_code=payload.country_code,
            bank_name=payload.bank_name,
            display_label=build_payout_label(
                payload.bank_name, payload.account_number, payload.method.value
            ),
            account_last4=account_last4(payload.account_number),
            encrypted_details=encrypt_jsonb(details),
            is_default=payload.set_default,
            is_verified=False,
        )

        if payload.set_default:
            await PayoutAccountRepository.clear_defaults(session, partner.id)
            account.is_default = True
        else:
            existing = await PayoutAccountRepository.list_for_partner(
                session, partner.id
            )
            account.is_default = not existing

        session.add(account)
        await session.flush()

        await AuditLogService.log_event(
            session,
            event_type="partner.payout_account.added",
            user_id=partner.user_id,
            resource_type="partner_payout_account",
            resource_id=str(account.id),
            # Deliberately only the masked tail.
            payload={"method": account.method, "last4": account.account_last4},
        )
        return account

    async def list_accounts(
        self, session: AsyncSession, partner: Partner
    ) -> list[PartnerPayoutAccount]:
        return await PayoutAccountRepository.list_for_partner(session, partner.id)

    async def delete_account(
        self, session: AsyncSession, partner: Partner, account_id: uuid.UUID
    ) -> None:
        account = await PayoutAccountRepository.get_owned(
            session, account_id, partner.id
        )
        if account is None:
            raise ResourceNotFoundException("Payout account not found")

        open_payout = await PayoutRepository.get_open_for_partner(session, partner.id)
        if open_payout is not None and open_payout.payout_account_id == account.id:
            raise ConflictException(
                "This account is referenced by a payout that is still in progress"
            )

        account.is_deleted = True
        account.deleted_at = _now()
        account.is_default = False
        await session.flush()

    # ─────────────────────────── requesting ──────────────────────────

    async def request_payout(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        payout_account_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        notes: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> PartnerPayout:
        """Create a payout for the partner's entire payable balance.

        The amount is summed from ledger rows locked inside this
        transaction, each row is attached to the payout through a uniquely
        constrained item, and each is transitioned ``payable → paid`` with an
        audit event. Re-running with the same idempotency key returns the
        original payout untouched.
        """
        if partner.status not in EARNING_STATUSES:
            raise ConflictException(
                f"Partner account is {partner.status}; payouts are unavailable"
            )
        if partner.commissions_held:
            raise ConflictException(
                "Commissions are currently held pending review",
                details={"reason": "commissions_held"},
            )

        open_payout = await PayoutRepository.get_open_for_partner(session, partner.id)
        if open_payout is not None:
            raise ConflictException(
                "A payout is already in progress",
                details={"payout_id": str(open_payout.id), "status": open_payout.status},
            )

        account = None
        if payout_account_id is not None:
            account = await PayoutAccountRepository.get_owned(
                session, payout_account_id, partner.id
            )
            if account is None:
                raise ResourceNotFoundException("Payout account not found")
        else:
            account = await PayoutAccountRepository.get_default(session, partner.id)
        if account is None:
            raise ValidationException(
                "A payout account must be configured before requesting a payout"
            )

        currency = partner.payout_currency
        commissions = await CommissionRepository.list_payable(
            session, partner.id, currency
        )
        total = sum(c.amount_minor for c in commissions)
        minimum = economics.payout_minimum_minor(partner.min_payout_minor)

        if total <= 0:
            raise ValidationException("There is no payable balance to pay out")
        if not economics.meets_payout_threshold(
            total, partner_minimum_minor=partner.min_payout_minor
        ):
            raise ValidationException(
                "The payable balance is below the minimum payout threshold",
                details={
                    "payable_minor": total,
                    "min_payout_minor": minimum,
                    "currency": currency,
                },
            )

        key = idempotency_key or f"payout:{partner.id}:{_now():%Y%m%d%H%M%S}"
        existing = await PayoutRepository.get_by_idempotency_key(
            session, partner.id, key
        )
        if existing is not None:
            return existing

        payout = PartnerPayout(
            partner_id=partner.id,
            payout_account_id=account.id,
            reference=await self._unique_reference(session),
            idempotency_key=key,
            status=PayoutStatus.REQUESTED.value,
            method=account.method,
            amount_minor=total,
            fee_minor=0,
            net_amount_minor=total,
            currency=currency,
            commission_count=len(commissions),
            provider=(
                "paystack" if account.method == PayoutMethod.PAYSTACK_TRANSFER.value else None
            ),
            requested_at=_now(),
            notes=notes,
        )
        try:
            await PayoutRepository.add(session, payout)
        except IntegrityError as exc:
            await session.rollback()
            existing = await PayoutRepository.get_by_idempotency_key(
                session, partner.id, key
            )
            if existing is not None:
                return existing
            raise ConflictException("A conflicting payout request already exists") from exc

        for commission in commissions:
            await PayoutRepository.add_item(
                session,
                PartnerPayoutItem(
                    payout_id=payout.id,
                    commission_id=commission.id,
                    amount_minor=commission.amount_minor,
                    currency=commission.currency,
                ),
            )
            commission.payout_id = payout.id
            await commission_service.transition(
                session,
                commission,
                to_status=CommissionStatus.PAID.value,
                reason="included_in_payout",
                actor_user_id=actor_user_id,
                actor_type="partner" if actor_user_id else "system",
                context={"payout_id": str(payout.id), "reference": payout.reference},
            )

        await AuditLogService.log_event(
            session,
            event_type="partner.payout.requested",
            user_id=actor_user_id,
            resource_type="partner_payout",
            resource_id=str(payout.id),
            payload={
                "amount_minor": total,
                "currency": currency,
                "commission_count": len(commissions),
                "reference": payout.reference,
            },
        )
        return payout

    async def _unique_reference(self, session: AsyncSession) -> str:
        for _ in range(12):
            reference = generate_reference()
            if not await PayoutRepository.reference_exists(session, reference):
                return reference
        raise ConflictException("Unable to allocate a unique payout reference")

    # ──────────────────────── admin transitions ──────────────────────

    async def transition(
        self,
        session: AsyncSession,
        payout: PartnerPayout,
        *,
        to_status: str,
        actor_user_id: uuid.UUID | None,
        reason: str | None = None,
        provider_reference: str | None = None,
    ) -> PartnerPayout:
        allowed = PAYOUT_TRANSITIONS.get(payout.status, frozenset())
        if to_status not in allowed:
            raise ConflictException(
                f"Cannot move a payout from {payout.status} to {to_status}",
                details={"allowed": sorted(allowed)},
            )

        now = _now()
        previous = payout.status
        payout.status = to_status
        if to_status == PayoutStatus.APPROVED.value:
            payout.approved_at = now
            payout.approved_by_id = actor_user_id
        elif to_status == PayoutStatus.PROCESSING.value:
            payout.processed_at = now
        elif to_status == PayoutStatus.PAID.value:
            payout.paid_at = now
            if provider_reference:
                payout.provider_reference = provider_reference
        elif to_status == PayoutStatus.FAILED.value:
            payout.failed_at = now
            payout.failure_reason = reason
            await self._return_commissions(session, payout, reason="payout_failed")
        elif to_status == PayoutStatus.CANCELLED.value:
            await self._return_commissions(session, payout, reason="payout_cancelled")

        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type=f"partner.payout.{to_status}",
            user_id=actor_user_id,
            resource_type="partner_payout",
            resource_id=str(payout.id),
            payload={"from": previous, "to": to_status, "reason": reason},
        )
        return payout

    async def _return_commissions(
        self, session: AsyncSession, payout: PartnerPayout, *, reason: str
    ) -> None:
        """Give the money back to the partner's payable balance.

        A failed or cancelled payout must not silently swallow commissions.
        Because ``paid`` is terminal in the commission state graph, the
        return is expressed as a compensating ``payout_reversal`` ledger
        entry rather than by rewriting history.
        """
        items = await PayoutRepository.list_items(session, payout.id)
        if not items:
            return

        now = _now()
        for item in items:
            commission = await CommissionRepository.get_by_id(
                session, item.commission_id
            )
            if commission is None:
                continue
            commission.payout_id = None

            from app.modules.partners.models import PartnerCommission

            # Only the portion of this commission that has NOT already been
            # clawed back may return to the payable balance. A refund or
            # chargeback that landed while the payout was in flight appends a
            # negative ``reversal`` row against the original commission;
            # restoring the full original amount here would re-credit money the
            # partner is no longer owed and let it be paid out a second time.
            reversed_total_result = await session.execute(
                select(
                    func.coalesce(func.sum(func.abs(PartnerCommission.amount_minor)), 0)
                ).where(
                    PartnerCommission.reverses_id == commission.id,
                    PartnerCommission.entry_type == LedgerEntryType.REVERSAL.value,
                )
            )
            already_reversed_minor = int(reversed_total_result.scalar_one())
            restorable_minor = max(commission.amount_minor - already_reversed_minor, 0)
            if restorable_minor <= 0:
                # Fully refunded while in flight: nothing to give back.
                continue

            key = f"payout_reversal:{payout.id}:{commission.id}"
            existing = await CommissionRepository.get_by_idempotency_key(
                session,
                partner_id=payout.partner_id,
                entry_type=LedgerEntryType.PAYOUT_REVERSAL.value,
                idempotency_key=key,
            )
            if existing is not None:
                continue

            restored = PartnerCommission(
                partner_id=payout.partner_id,
                relationship_id=commission.relationship_id,
                organization_id=commission.organization_id,
                campaign_id=commission.campaign_id,
                entry_type=LedgerEntryType.PAYOUT_REVERSAL.value,
                status=CommissionStatus.PAYABLE.value,
                earning_method=commission.earning_method,
                source_amount_minor=0,
                commissionable_amount_minor=0,
                rate_bps=0,
                amount_minor=restorable_minor,
                currency=commission.currency,
                calculation_basis={
                    "restores_commission": str(commission.id),
                    "payout_id": str(payout.id),
                    "reason": reason,
                    "original_amount_minor": commission.amount_minor,
                    "already_reversed_minor": already_reversed_minor,
                },
                idempotency_key=key,
                source_type="payout_reversal",
                source_reference=payout.reference,
                period_month=economics.period_month(now),
                earned_at=now,
                became_payable_at=now,
                notes=reason,
            )
            await CommissionRepository.add(session, restored)

        logger.info(
            "Returned %d commissions to payable after %s for payout %s",
            len(items),
            reason,
            payout.reference,
        )

    # ─────────────────────────── processing ──────────────────────────

    async def process_payout(
        self, session: AsyncSession, payout: PartnerPayout
    ) -> PartnerPayout:
        """Send an approved payout to the provider.

        Failures are recorded and the commissions are returned to the
        payable balance — never lost. The provider call uses our own payout
        reference so a retry cannot create a second transfer.
        """
        if payout.status != PayoutStatus.APPROVED.value:
            raise ConflictException(
                f"Only approved payouts can be processed (current: {payout.status})"
            )

        account = None
        if payout.payout_account_id:
            account = await PayoutAccountRepository.get_owned(
                session, payout.payout_account_id, payout.partner_id
            )

        if payout.method != PayoutMethod.PAYSTACK_TRANSFER.value or account is None:
            # Manual/bank methods are settled out of band; an operator marks
            # them paid once the transfer clears.
            return await self.transition(
                session,
                payout,
                to_status=PayoutStatus.PROCESSING.value,
                actor_user_id=None,
                reason="awaiting_manual_settlement",
            )

        await self.transition(
            session,
            payout,
            to_status=PayoutStatus.PROCESSING.value,
            actor_user_id=None,
            reason="submitted_to_provider",
        )

        if not account.provider_recipient_code:
            await self.transition(
                session,
                payout,
                to_status=PayoutStatus.FAILED.value,
                actor_user_id=None,
                reason="payout_account_not_registered_with_provider",
            )
            return payout

        try:
            result = await self.client.initiate_transfer(
                amount=payout.net_amount_minor,
                recipient_code=account.provider_recipient_code,
                reason=f"Reliastra partner payout {payout.reference}",
                reference=payout.reference,
                currency=payout.currency,
            )
        except httpx.HTTPError as exc:
            logger.warning("Payout %s transfer failed: %s", payout.reference, exc)
            await self.transition(
                session,
                payout,
                to_status=PayoutStatus.FAILED.value,
                actor_user_id=None,
                reason="provider_transfer_failed",
            )
            return payout

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        payout.provider_reference = str(data.get("transfer_code") or payout.reference)
        payout.provider_status = str(data.get("status") or "pending")
        payout.provider_response = {
            k: v for k, v in data.items() if k in {"status", "transfer_code", "id"}
        }
        await session.flush()

        if payout.provider_status in {"success", "completed"}:
            await self.transition(
                session,
                payout,
                to_status=PayoutStatus.PAID.value,
                actor_user_id=None,
                reason="provider_confirmed",
                provider_reference=payout.provider_reference,
            )
        return payout


payout_service = PayoutService()

__all__ = [
    "PartnerPaystackClient",
    "PayoutService",
    "partner_paystack_client",
    "payout_service",
]
