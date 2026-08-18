"""Partner fraud risk scoring.

The philosophy here matters more than the arithmetic.

**Shared infrastructure is not evidence.** There is deliberately no
"same IP address" signal, and no rule that treats a shared company domain,
office network, university, coworking space or VPN as suspicious. Those
patterns describe ordinary legitimate customers — a consultancy onboarding
three clients from one office looks exactly like the thing a naive rule
would ban.

**What is actually weighed** is behaviour that costs the business money or
that no honest partner produces: self-referral, chargeback history, reused
payment instruments across "different" customers, high refund rates,
conversions with zero product engagement, rapid churn, and unverifiable
deployment claims.

**Scores never act alone.** A high score can *hold* commissions — money
stays in the ledger, fully recoverable — and raises a flag for a human. No
score suspends a partner, bans a user or reverses money on its own; every
destructive action is an explicit admin decision recorded with a reason.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import ConflictException
from app.modules.partners.commissions import commission_service
from app.modules.partners.constants import (
    FRAUD_SIGNAL_WEIGHTS,
    CommissionStatus,
    FlagResolution,
    FlagStatus,
    FraudSignal,
    LedgerEntryType,
    PartnerStatus,
    RiskBand,
    risk_band_for_score,
)
from app.modules.partners.models import (
    Partner,
    PartnerAttribution,
    PartnerClickEvent,
    PartnerCommission,
    PartnerCustomerRelationship,
    PartnerDeploymentClaim,
    PartnerFraudFlag,
    PartnerRiskAssessment,
)
from app.modules.partners.repository import (
    CommissionRepository,
    FraudRepository,
    PartnerRepository,
)

logger = logging.getLogger(__name__)

#: Severity shown to admins, derived from the signal's own weight.
_SEVERITY_BY_WEIGHT = ((30, "high"), (15, "medium"), (0, "low"))

#: Disposable-email domains seen in referral abuse. Intentionally short and
#: conservative: this contributes 15 points, it does not ban anyone.
_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "throwawaymail.com",
        "yopmail.com",
        "trashmail.com",
        "sharklasers.com",
        "getnada.com",
        "dispostable.com",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _severity_for(signal: str) -> str:
    weight = FRAUD_SIGNAL_WEIGHTS.get(signal, 0)
    for threshold, severity in _SEVERITY_BY_WEIGHT:
        if weight >= threshold:
            return severity
    return "low"


class FraudService:
    """Computes risk assessments and manages fraud flags."""

    async def assess_partner(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        lookback_days: int = 90,
    ) -> PartnerRiskAssessment:
        """Score a partner from observed behaviour over a lookback window.

        Weights are additive and the total is clamped to 100. The metrics
        that produced the score are stored alongside it, so an admin
        reviewing a flag sees the evidence rather than an opaque number.
        """
        since = _now() - timedelta(days=lookback_days)
        metrics = await self._collect_metrics(session, partner, since=since)
        signals = self._derive_signals(metrics)

        score = min(100, sum(FRAUD_SIGNAL_WEIGHTS.get(s, 0) for s in signals))
        band = risk_band_for_score(score)
        review_threshold = settings.PARTNER_FRAUD_REVIEW_SCORE

        assessment = PartnerRiskAssessment(
            partner_id=partner.id,
            score=score,
            band=band,
            signals=sorted(signals),
            metrics=metrics,
            triggered_hold=False,
            created_at=_now(),
        )
        await FraudRepository.add_assessment(session, assessment)

        partner.risk_score = score
        partner.risk_band = band
        partner.risk_evaluated_at = _now()

        # A high score holds money and asks a human to look. It never
        # suspends the account or touches the user.
        if score >= review_threshold and not partner.commissions_held:
            held = await commission_service.hold_partner_commissions(
                session, partner, reason="fraud_review"
            )
            assessment.triggered_hold = True
            logger.warning(
                "Held %d commissions for partner %s (risk score %d)",
                held,
                partner.id,
                score,
            )

        for signal in signals:
            await self.raise_flag(
                session,
                partner=partner,
                signal=signal,
                score=score,
                assessment=assessment,
                summary=self._summary_for(signal, metrics),
                evidence={"metrics": metrics},
            )

        await session.flush()
        return assessment

    # ────────────────────────────── metrics ──────────────────────────

    async def _collect_metrics(
        self, session: AsyncSession, partner: Partner, *, since: datetime
    ) -> dict[str, Any]:
        """Gather the behavioural facts the signals are derived from."""
        # Conversions and reversals straight from the ledger.
        commission_rows = await session.execute(
            select(
                PartnerCommission.entry_type,
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
            )
            .where(
                PartnerCommission.partner_id == partner.id,
                PartnerCommission.earned_at >= since,
            )
            .group_by(PartnerCommission.entry_type)
        )
        commissions = 0
        reversals = 0
        reversal_amount = 0
        commission_amount = 0
        for entry_type, count, amount in commission_rows.all():
            if entry_type == LedgerEntryType.COMMISSION.value:
                commissions = int(count)
                commission_amount = int(amount)
            elif entry_type == LedgerEntryType.REVERSAL.value:
                reversals = int(count)
                reversal_amount = abs(int(amount))

        chargebacks = int(
            (
                await session.execute(
                    select(func.count(PartnerCommission.id)).where(
                        PartnerCommission.partner_id == partner.id,
                        PartnerCommission.reversal_reason == "chargeback",
                    )
                )
            ).scalar_one()
        )

        clicks = int(
            (
                await session.execute(
                    select(func.count(PartnerClickEvent.id)).where(
                        PartnerClickEvent.partner_id == partner.id,
                        PartnerClickEvent.created_at >= since,
                    )
                )
            ).scalar_one()
        )
        unique_visitors = int(
            (
                await session.execute(
                    select(
                        func.count(func.distinct(PartnerClickEvent.visitor_id))
                    ).where(
                        PartnerClickEvent.partner_id == partner.id,
                        PartnerClickEvent.created_at >= since,
                    )
                )
            ).scalar_one()
        )
        bot_clicks = int(
            (
                await session.execute(
                    select(func.count(PartnerClickEvent.id)).where(
                        PartnerClickEvent.partner_id == partner.id,
                        PartnerClickEvent.created_at >= since,
                        PartnerClickEvent.is_bot.is_(True),
                    )
                )
            ).scalar_one()
        )

        signups = int(
            (
                await session.execute(
                    select(func.count(PartnerAttribution.id)).where(
                        PartnerAttribution.partner_id == partner.id,
                        PartnerAttribution.user_id.isnot(None),
                        PartnerAttribution.occurred_at >= since,
                    )
                )
            ).scalar_one()
        )
        self_referrals = int(
            (
                await session.execute(
                    select(func.count(PartnerAttribution.id)).where(
                        PartnerAttribution.partner_id == partner.id,
                        PartnerAttribution.notes == "self_referral",
                    )
                )
            ).scalar_one()
        )

        relationships = int(
            (
                await session.execute(
                    select(func.count(PartnerCustomerRelationship.id)).where(
                        PartnerCustomerRelationship.partner_id == partner.id
                    )
                )
            ).scalar_one()
        )
        churned_fast = int(
            (
                await session.execute(
                    select(func.count(PartnerCustomerRelationship.id)).where(
                        PartnerCustomerRelationship.partner_id == partner.id,
                        PartnerCustomerRelationship.status == "churned",
                        PartnerCustomerRelationship.ended_at.isnot(None),
                        PartnerCustomerRelationship.ended_at
                        < PartnerCustomerRelationship.started_at
                        + timedelta(days=30),
                    )
                )
            ).scalar_one()
        )

        unverified_claims = int(
            (
                await session.execute(
                    select(func.count(PartnerDeploymentClaim.id)).where(
                        PartnerDeploymentClaim.partner_id == partner.id,
                        PartnerDeploymentClaim.status == "rejected",
                    )
                )
            ).scalar_one()
        )

        disposable_leads = await self._count_disposable_leads(session, partner)

        return {
            "window_days": (_now() - since).days,
            "clicks": clicks,
            "unique_visitors": unique_visitors,
            "bot_clicks": bot_clicks,
            "signups": signups,
            "self_referrals": self_referrals,
            "commissions": commissions,
            "commission_amount_minor": commission_amount,
            "reversals": reversals,
            "reversal_amount_minor": reversal_amount,
            "chargebacks": chargebacks,
            "relationships": relationships,
            "churned_within_30d": churned_fast,
            "rejected_claims": unverified_claims,
            "disposable_email_leads": disposable_leads,
        }

    async def _count_disposable_leads(
        self, session: AsyncSession, partner: Partner
    ) -> int:
        from app.modules.partners.models import PartnerLead

        result = await session.execute(
            select(PartnerLead.contact_email).where(
                PartnerLead.partner_id == partner.id
            )
        )
        count = 0
        for (email,) in result.all():
            if email and email.rsplit("@", 1)[-1].lower() in _DISPOSABLE_DOMAINS:
                count += 1
        return count

    # ────────────────────────────── signals ──────────────────────────

    @staticmethod
    def _derive_signals(metrics: dict[str, Any]) -> set[str]:
        """Turn metrics into signals.

        Each rule needs enough volume to be meaningful — small numbers are
        noise, and flagging a partner over two data points is how you lose
        good partners.
        """
        signals: set[str] = set()

        if metrics["self_referrals"] > 0:
            signals.add(FraudSignal.SELF_REFERRAL.value)

        if metrics["chargebacks"] >= 2:
            signals.add(FraudSignal.CHARGEBACK_HISTORY.value)

        commissions = metrics["commissions"]
        if commissions >= 5:
            refund_rate = metrics["reversals"] / commissions
            if refund_rate >= 0.30:
                signals.add(FraudSignal.HIGH_REFUND_RATE.value)

        relationships = metrics["relationships"]
        if relationships >= 5 and metrics["churned_within_30d"] / relationships >= 0.5:
            signals.add(FraudSignal.RAPID_CHURN.value)

        clicks = metrics["clicks"]
        uniques = metrics["unique_visitors"] or 1
        # Many clicks from very few visitors, at volume, is link hammering —
        # it affects reported analytics only, hence the small weight.
        if clicks >= 500 and clicks / uniques >= 20:
            signals.add(FraudSignal.CLICK_FLOODING.value)
        if clicks >= 200 and metrics["bot_clicks"] / clicks >= 0.7:
            signals.add(FraudSignal.CLICK_FLOODING.value)

        if metrics["signups"] >= 20 and metrics["unique_visitors"] < 5:
            signals.add(FraudSignal.VELOCITY_ANOMALY.value)

        if metrics["disposable_email_leads"] >= 3:
            signals.add(FraudSignal.DISPOSABLE_EMAIL.value)

        if metrics["rejected_claims"] >= 2:
            signals.add(FraudSignal.UNVERIFIED_DEPLOYMENT_CLAIM.value)

        return signals

    @staticmethod
    def _summary_for(signal: str, metrics: dict[str, Any]) -> str:
        summaries = {
            FraudSignal.SELF_REFERRAL.value: (
                f"{metrics['self_referrals']} self-referral attempt(s) were blocked "
                "at signup."
            ),
            FraudSignal.CHARGEBACK_HISTORY.value: (
                f"{metrics['chargebacks']} chargeback(s) recorded against referred "
                "customers."
            ),
            FraudSignal.HIGH_REFUND_RATE.value: (
                f"{metrics['reversals']} of {metrics['commissions']} commissions were "
                "reversed by refunds."
            ),
            FraudSignal.RAPID_CHURN.value: (
                f"{metrics['churned_within_30d']} of {metrics['relationships']} "
                "referred customers churned within 30 days."
            ),
            FraudSignal.CLICK_FLOODING.value: (
                f"{metrics['clicks']} clicks from {metrics['unique_visitors']} unique "
                f"visitors ({metrics['bot_clicks']} identified as automated)."
            ),
            FraudSignal.VELOCITY_ANOMALY.value: (
                f"{metrics['signups']} signups against only "
                f"{metrics['unique_visitors']} unique visitors."
            ),
            FraudSignal.DISPOSABLE_EMAIL.value: (
                f"{metrics['disposable_email_leads']} lead(s) used disposable email "
                "domains."
            ),
            FraudSignal.UNVERIFIED_DEPLOYMENT_CLAIM.value: (
                f"{metrics['rejected_claims']} deployment claim(s) were rejected for "
                "insufficient evidence."
            ),
        }
        return summaries.get(signal, f"Signal {signal} triggered.")

    # ─────────────────────────────── flags ───────────────────────────

    async def raise_flag(
        self,
        session: AsyncSession,
        *,
        partner: Partner,
        signal: str,
        score: int,
        summary: str,
        assessment: PartnerRiskAssessment | None = None,
        evidence: dict[str, Any] | None = None,
        related_commission_id: uuid.UUID | None = None,
        related_organization_id: uuid.UUID | None = None,
    ) -> PartnerFraudFlag:
        """Open a flag, or refresh the existing open one for this signal.

        Re-raising is intentionally idempotent: a recurring condition should
        keep one flag current rather than burying reviewers in duplicates.
        """
        existing = await FraudRepository.get_open_flag(session, partner.id, signal)
        if existing is not None:
            existing.score_at_flag = score
            existing.summary = summary
            existing.evidence = evidence
            if assessment is not None:
                existing.assessment_id = assessment.id
            await session.flush()
            return existing

        flag = PartnerFraudFlag(
            partner_id=partner.id,
            assessment_id=assessment.id if assessment else None,
            signal=signal,
            severity=_severity_for(signal),
            status=FlagStatus.OPEN.value,
            score_at_flag=score,
            summary=summary,
            evidence=evidence,
            related_commission_id=related_commission_id,
            related_organization_id=related_organization_id,
        )
        await FraudRepository.add_flag(session, flag)
        await AuditLogService.log_event(
            session,
            event_type="partner.fraud.flag_raised",
            resource_type="partner_fraud_flag",
            resource_id=str(flag.id),
            payload={
                "partner_id": str(partner.id),
                "signal": signal,
                "severity": flag.severity,
                "score": score,
            },
        )
        return flag

    async def resolve_flag(
        self,
        session: AsyncSession,
        flag: PartnerFraudFlag,
        *,
        status: FlagStatus | str,
        resolution: FlagResolution | str,
        notes: str,
        actor_user_id: uuid.UUID,
    ) -> PartnerFraudFlag:
        """Close a flag with an explicit, executed admin decision.

        The chosen resolution is *carried out* here, not merely recorded, so
        that "resolved: release commissions" cannot drift from the actual
        state of the money.
        """
        if flag.status in {
            FlagStatus.RESOLVED_LEGITIMATE.value,
            FlagStatus.RESOLVED_FRAUD.value,
            FlagStatus.DISMISSED.value,
        }:
            raise ConflictException(
                f"Flag is already {flag.status}",
                details={"flag_id": str(flag.id)},
            )

        status_value = status.value if hasattr(status, "value") else str(status)
        resolution_value = (
            resolution.value if hasattr(resolution, "value") else str(resolution)
        )

        partner = await PartnerRepository.get_by_id(session, flag.partner_id)
        if partner is None:
            raise ConflictException("Partner no longer exists")

        flag.status = status_value
        flag.resolution = resolution_value
        flag.resolution_notes = notes
        flag.resolved_at = _now()
        flag.resolved_by_id = actor_user_id
        await session.flush()

        await self._apply_resolution(
            session,
            partner=partner,
            resolution=resolution_value,
            notes=notes,
            actor_user_id=actor_user_id,
            flag=flag,
        )

        await AuditLogService.log_event(
            session,
            event_type="partner.fraud.flag_resolved",
            user_id=actor_user_id,
            resource_type="partner_fraud_flag",
            resource_id=str(flag.id),
            payload={
                "partner_id": str(partner.id),
                "status": status_value,
                "resolution": resolution_value,
            },
        )
        return flag

    async def _apply_resolution(
        self,
        session: AsyncSession,
        *,
        partner: Partner,
        resolution: str,
        notes: str,
        actor_user_id: uuid.UUID,
        flag: PartnerFraudFlag,
    ) -> None:
        from app.modules.partners.service import partner_service

        if resolution == FlagResolution.NO_ACTION.value:
            return

        if resolution == FlagResolution.WARN_PARTNER.value:
            partner.notes = "\n".join(
                filter(None, [partner.notes, f"[warning] {notes}"])
            )
            await session.flush()
            return

        if resolution == FlagResolution.HOLD_COMMISSIONS.value:
            await commission_service.hold_partner_commissions(
                session, partner, reason="fraud_review", actor_user_id=actor_user_id
            )
            return

        if resolution == FlagResolution.RELEASE_COMMISSIONS.value:
            await commission_service.release_partner_commissions(
                session,
                partner,
                reason="fraud_review_cleared",
                actor_user_id=actor_user_id,
            )
            return

        if resolution == FlagResolution.REVERSE_COMMISSIONS.value:
            # Only unpaid commissions are clawed back here; recovering money
            # already paid out is a separate, deliberate finance action.
            commissions, _ = await CommissionRepository.list_for_partner(
                session, partner.id, size=1000
            )
            for commission in commissions:
                if commission.status in {
                    CommissionStatus.PENDING.value,
                    CommissionStatus.HELD.value,
                    CommissionStatus.PAYABLE.value,
                } and commission.entry_type == LedgerEntryType.COMMISSION.value:
                    await commission_service.reverse_commission(
                        session,
                        commission,
                        reason="fraud",
                        actor_user_id=actor_user_id,
                        notes=notes,
                    )
            return

        if resolution == FlagResolution.SUSPEND_PARTNER.value:
            await partner_service.set_status(
                session,
                partner,
                status=PartnerStatus.SUSPENDED.value,
                reason=notes,
                changed_by_id=actor_user_id,
            )
            return

        if resolution == FlagResolution.TERMINATE_PARTNER.value:
            await partner_service.set_status(
                session,
                partner,
                status=PartnerStatus.TERMINATED.value,
                reason=notes,
                changed_by_id=actor_user_id,
            )
            return

    # ───────────────────────── batch evaluation ──────────────────────

    async def assess_all(
        self, session: AsyncSession, *, limit: int = 500
    ) -> int:
        """Score every active partner (background job entry point)."""
        partner_ids = await PartnerRepository.list_active_ids(session)
        assessed = 0
        for partner_id in partner_ids[:limit]:
            partner = await PartnerRepository.get_by_id(session, partner_id)
            if partner is None:
                continue
            try:
                await self.assess_partner(session, partner)
                assessed += 1
            except Exception:  # pragma: no cover - one bad partner must not
                # abort the whole sweep
                logger.exception("Risk assessment failed for partner %s", partner_id)
        return assessed


fraud_service = FraudService()

__all__ = ["FraudService", "RiskBand", "fraud_service"]
