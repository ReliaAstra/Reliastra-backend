"""Admin API for the partner network — ``/v1/admin/partners/*`` and
``/v1/admin/geo/*``.

Follows the established admin conventions: every route depends on
:func:`require_system_admin`, mutations carry the ``@audit_log`` decorator
that writes to ``admin_audit_logs``, and the services additionally write
domain audit entries to ``audit_logs``. Between the two, every financial and
lifecycle action is attributable to a named admin with a reason.

Admins see full detail (including unmasked lead contacts, which they need in
order to run the introduction pipeline) — partners never do.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.pagination import OffsetPagination
from app.db.session import get_db
from app.modules.admin.decorators import audit_log
from app.modules.admin.guards import require_system_admin
from app.modules.partners.commissions import commission_service
from app.modules.partners.fraud import fraud_service
from app.modules.partners.geo import GeoService
from app.modules.partners.payouts import payout_service
from app.modules.partners.repository import (
    ClaimRepository,
    CommissionRepository,
    FraudRepository,
    GeoRepository,
    LeadRepository,
    PartnerApplicationRepository,
    PartnerRepository,
    PayoutRepository,
    ProgramContentRepository,
    SettlementRepository,
)
from app.modules.partners.schemas import (
    ClaimEvidenceResponse,
    ClaimReviewRequest,
    CommissionAdjustmentRequest,
    CommissionAdminItem,
    CommissionReversalRequest,
    CountryStatsItem,
    DeploymentClaimAdminItem,
    FraudFlagItem,
    FraudFlagResolveRequest,
    GeoAnalyticsResponse,
    GeoCoverageResponse,
    LeadAdminItem,
    LeadStatusUpdateRequest,
    PartnerAdminItem,
    PartnerApplicationAdminItem,
    PartnerApplicationReviewRequest,
    PartnerProgramContentItem,
    PartnerRateUpdateRequest,
    PartnerStatusUpdateRequest,
    PartnerTierHistoryItem,
    PartnerTierUpdateRequest,
    PayoutActionRequest,
    PayoutAdminItem,
    RiskAssessmentItem,
    SettlementItem,
)
from app.modules.partners.service import partner_service
from app.modules.users.models import User

logger = logging.getLogger(__name__)

admin_partners_router = APIRouter(
    prefix="/v1/admin/partners", tags=["Admin — Partners"]
)
admin_geo_router = APIRouter(prefix="/v1/admin/geo", tags=["Admin — Geo"])


def _pages(total: int, size: int) -> int:
    return (total + size - 1) // size if size else 0


async def _get_partner_or_404(session: AsyncSession, partner_id: uuid.UUID):
    partner = await PartnerRepository.get_by_id(session, partner_id)
    if partner is None:
        raise ResourceNotFoundException("Partner not found")
    return partner


def _admin_item(partner) -> PartnerAdminItem:
    return PartnerAdminItem(
        **partner_service.to_response(partner).model_dump(),
        user_id=partner.user_id,
        organization_id=partner.organization_id,
        risk_score=partner.risk_score,
        risk_band=partner.risk_band,
        risk_evaluated_at=partner.risk_evaluated_at,
        commissions_held=partner.commissions_held,
        suspended_at=partner.suspended_at,
        suspension_reason=partner.suspension_reason,
        terminated_at=partner.terminated_at,
        custom_rate_bps=partner.custom_rate_bps,
        notes=partner.notes,
    )


# ═══════════════════════════ Applications ════════════════════════════════


@admin_partners_router.get(
    "/applications",
    response_model=OffsetPagination[PartnerApplicationAdminItem],
    summary="List partner applications",
)
async def list_applications(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[PartnerApplicationAdminItem]:
    """All partner applications across the platform, optionally filtered
    by status. Includes the applicant identity and reviewer notes.
    """
    applications, total = await PartnerApplicationRepository.list_admin(
        db, status=status_filter, page=page, size=size
    )
    return OffsetPagination[PartnerApplicationAdminItem](
        items=[PartnerApplicationAdminItem.model_validate(a) for a in applications],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@admin_partners_router.post(
    "/applications/{application_id}/review",
    response_model=PartnerApplicationAdminItem,
    summary="Approve or reject a partner application",
    responses={409: {"description": "Application has already been reviewed"}},
)
@audit_log(action="review_partner_application", entity_type="partner_application")
async def review_application(
    request: Request,
    application_id: uuid.UUID,
    payload: PartnerApplicationReviewRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerApplicationAdminItem:
    """Review an application.

    Approval provisions the partner account, allocates a partner code and
    slug, creates the default referral link and records the initial tier.
    """
    application = await PartnerApplicationRepository.get_by_id(db, application_id)
    if application is None:
        raise ResourceNotFoundException("Application not found")

    if payload.approve:
        await partner_service.approve_application(
            db,
            application,
            reviewer_id=admin_user.id,
            tier=payload.tier,
            notes=payload.review_notes,
        )
    else:
        await partner_service.reject_application(
            db,
            application,
            reviewer_id=admin_user.id,
            reason=payload.rejection_reason,
            notes=payload.review_notes,
        )
    return PartnerApplicationAdminItem.model_validate(application)


# ═════════════════════════════ Partners ══════════════════════════════════


@admin_partners_router.get(
    "",
    response_model=OffsetPagination[PartnerAdminItem],
    summary="List partners",
)
async def list_partners(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    tier: str | None = Query(default=None),
    partner_type: str | None = Query(default=None),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    risk_band: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[PartnerAdminItem]:
    """All partners, with risk and lifecycle fields that are never shown
    to partners themselves. Supports filtering by status, tier, type,
    country and risk band.
    """
    partners, total = await PartnerRepository.list_admin(
        db,
        status=status_filter,
        tier=tier,
        partner_type=partner_type,
        country_code=country_code,
        risk_band=risk_band,
        search=search,
        page=page,
        size=size,
    )
    return OffsetPagination[PartnerAdminItem](
        items=[_admin_item(p) for p in partners],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@admin_partners_router.get(
    "/{partner_id}",
    response_model=PartnerAdminItem,
    summary="Get a partner",
)
async def get_partner(
    request: Request,
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerAdminItem:
    """Full admin view of one partner, including risk score, hold state
    and any negotiated rates.
    """
    partner = await _get_partner_or_404(db, partner_id)
    return _admin_item(partner)


@admin_partners_router.patch(
    "/{partner_id}/status",
    response_model=PartnerAdminItem,
    summary="Suspend, terminate or reactivate a partner",
)
@audit_log(action="update_partner_status", entity_type="partner")
async def update_partner_status(
    request: Request,
    partner_id: uuid.UUID,
    payload: PartnerStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerAdminItem:
    """Change a partner's standing.

    Suspension and termination freeze commissions but never delete ledger
    history; reactivation releases the freeze.
    """
    partner = await _get_partner_or_404(db, partner_id)
    partner = await partner_service.set_status(
        db,
        partner,
        status=payload.status,
        reason=payload.reason,
        changed_by_id=admin_user.id,
    )
    return _admin_item(partner)


@admin_partners_router.patch(
    "/{partner_id}/tier",
    response_model=PartnerTierHistoryItem,
    summary="Manually set a partner's tier",
)
@audit_log(action="update_partner_tier", entity_type="partner")
async def update_partner_tier(
    request: Request,
    partner_id: uuid.UUID,
    payload: PartnerTierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerTierHistoryItem:
    """Set a tier directly, bypassing the earned-tier calculation. Used
    for certification and negotiated standing. The change and its
    reason are written to the tier history.
    """
    partner = await _get_partner_or_404(db, partner_id)
    entry = await partner_service.set_tier(
        db,
        partner,
        tier=payload.tier,
        reason=payload.reason,
        changed_by_id=admin_user.id,
    )
    return PartnerTierHistoryItem.model_validate(entry)


@admin_partners_router.patch(
    "/{partner_id}/rates",
    response_model=PartnerAdminItem,
    summary="Set negotiated commission rates for a partner",
)
@audit_log(action="update_partner_rates", entity_type="partner")
async def update_partner_rates(
    request: Request,
    partner_id: uuid.UUID,
    payload: PartnerRateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerAdminItem:
    """Set per-method rates for a partner.

    Rates are clamped to the platform ceiling and apply only to
    relationships created afterwards — existing relationships keep the rate
    snapshotted at their creation.
    """
    partner = await _get_partner_or_404(db, partner_id)
    partner = await partner_service.set_custom_rates(
        db,
        partner,
        custom_rate_bps=payload.custom_rate_bps,
        reason=payload.reason,
        changed_by_id=admin_user.id,
    )
    return _admin_item(partner)


@admin_partners_router.post(
    "/{partner_id}/evaluate-tier",
    response_model=PartnerTierHistoryItem | None,
    summary="Re-evaluate a partner's earned tier",
)
@audit_log(action="evaluate_partner_tier", entity_type="partner")
async def evaluate_partner_tier(
    request: Request,
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerTierHistoryItem | None:
    """Recompute the earned tier from ledger metrics. Promotion only."""
    partner = await _get_partner_or_404(db, partner_id)
    entry = await partner_service.evaluate_tier(
        db, partner, changed_by_id=admin_user.id
    )
    return PartnerTierHistoryItem.model_validate(entry) if entry else None


# ═══════════════════════════ Commissions ═════════════════════════════════


@admin_partners_router.get(
    "/commissions/all",
    response_model=OffsetPagination[CommissionAdminItem],
    summary="List commission ledger entries across all partners",
)
async def list_all_commissions(
    request: Request,
    partner_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    period_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[CommissionAdminItem]:
    """The commission ledger across all partners. Entries are immutable;
    amounts are signed integer minor units.
    """
    commissions, total = await CommissionRepository.list_admin(
        db,
        partner_id=partner_id,
        status=status_filter,
        period_month=period_month,
        page=page,
        size=size,
    )
    return OffsetPagination[CommissionAdminItem](
        items=[CommissionAdminItem.model_validate(c) for c in commissions],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@admin_partners_router.post(
    "/commissions/{commission_id}/reverse",
    response_model=CommissionAdminItem,
    summary="Reverse a commission",
    responses={422: {"description": "Entry is not reversible"}},
)
@audit_log(action="reverse_partner_commission", entity_type="partner_commission")
async def reverse_commission(
    request: Request,
    commission_id: uuid.UUID,
    payload: CommissionReversalRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CommissionAdminItem:
    """Claw back a commission.

    Writes a new negative ledger entry referencing the original; the
    original row is never modified or deleted.
    """
    commission = await CommissionRepository.get_by_id(db, commission_id)
    if commission is None:
        raise ResourceNotFoundException("Commission not found")

    reversal = await commission_service.reverse_commission(
        db,
        commission,
        reason=payload.reason,
        refunded_minor=payload.refunded_minor,
        actor_user_id=admin_user.id,
        notes=payload.notes,
    )
    if reversal is None:
        raise ValidationException("Nothing to reverse for this commission")
    return CommissionAdminItem.model_validate(reversal)


@admin_partners_router.post(
    "/commissions/adjust",
    response_model=CommissionAdminItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual commission adjustment",
)
@audit_log(action="adjust_partner_commission", entity_type="partner_commission")
async def adjust_commission(
    request: Request,
    payload: CommissionAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CommissionAdminItem:
    """Post a signed correction to a partner's ledger.

    Adjustments are immediately payable and always carry a stored reason.
    """
    partner = await _get_partner_or_404(db, payload.partner_id)
    adjustment = await commission_service.create_adjustment(
        db,
        partner=partner,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        reason=payload.reason,
        actor_user_id=admin_user.id,
        organization_id=payload.organization_id,
    )
    return CommissionAdminItem.model_validate(adjustment)


@admin_partners_router.post(
    "/{partner_id}/hold-commissions",
    summary="Hold all unpaid commissions for a partner",
)
@audit_log(action="hold_partner_commissions", entity_type="partner")
async def hold_commissions(
    request: Request,
    partner_id: uuid.UUID,
    reason: str = Query(min_length=3, max_length=200),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict[str, int | str]:
    """Freeze every not-yet-paid commission for a partner.

    Holding keeps the money in the ledger and fully recoverable — it is
    the safe response to an open question about a partner's activity.
    """
    partner = await _get_partner_or_404(db, partner_id)
    held = await commission_service.hold_partner_commissions(
        db, partner, reason=reason, actor_user_id=admin_user.id
    )
    return {"partner_id": str(partner.id), "held": held}


@admin_partners_router.post(
    "/{partner_id}/release-commissions",
    summary="Release held commissions for a partner",
)
@audit_log(action="release_partner_commissions", entity_type="partner")
async def release_commissions(
    request: Request,
    partner_id: uuid.UUID,
    reason: str = Query(min_length=3, max_length=200),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict[str, int | str]:
    """Lift a hold. Entries whose holding period has already elapsed
    become payable immediately; the rest return to pending and finish
    their hold normally.
    """
    partner = await _get_partner_or_404(db, partner_id)
    released = await commission_service.release_partner_commissions(
        db, partner, reason=reason, actor_user_id=admin_user.id
    )
    return {"partner_id": str(partner.id), "released": released}


@admin_partners_router.get(
    "/settlements/all",
    response_model=OffsetPagination[SettlementItem],
    summary="List monthly settlements",
)
async def list_settlements(
    request: Request,
    period_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[SettlementItem]:
    """Monthly settlements across all partners, optionally filtered by
    period or status.
    """
    settlements, total = await SettlementRepository.list_admin(
        db, period_month=period_month, status=status_filter, page=page, size=size
    )
    return OffsetPagination[SettlementItem](
        items=[SettlementItem.model_validate(s) for s in settlements],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


# ═════════════════════════════ Payouts ═══════════════════════════════════


@admin_partners_router.get(
    "/payouts/all",
    response_model=OffsetPagination[PayoutAdminItem],
    summary="List payouts",
)
async def list_payouts(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[PayoutAdminItem]:
    """All payouts, with provider references and approver identity."""
    payouts, total = await PayoutRepository.list_admin(
        db, status=status_filter, partner_id=partner_id, page=page, size=size
    )
    return OffsetPagination[PayoutAdminItem](
        items=[PayoutAdminItem.model_validate(p) for p in payouts],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@admin_partners_router.post(
    "/payouts/{payout_id}/action",
    response_model=PayoutAdminItem,
    summary="Approve, process, complete, fail or cancel a payout",
    responses={409: {"description": "Illegal payout state transition"}},
)
@audit_log(action="partner_payout_action", entity_type="partner_payout")
async def act_on_payout(
    request: Request,
    payout_id: uuid.UUID,
    payload: PayoutActionRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PayoutAdminItem:
    """Advance a payout through its lifecycle.

    ``process`` submits the transfer to the provider using our own payout
    reference, so a retry cannot create a second transfer. Failing or
    cancelling returns the commissions to the partner's payable balance via
    a compensating ledger entry.
    """
    payout = await PayoutRepository.get_by_id(db, payout_id)
    if payout is None:
        raise ResourceNotFoundException("Payout not found")

    action = payload.action.lower()
    if action == "approve":
        payout = await payout_service.transition(
            db,
            payout,
            to_status="approved",
            actor_user_id=admin_user.id,
            reason=payload.reason,
        )
    elif action == "process":
        payout = await payout_service.process_payout(db, payout)
    elif action == "mark_paid":
        payout = await payout_service.transition(
            db,
            payout,
            to_status="paid",
            actor_user_id=admin_user.id,
            reason=payload.reason or "marked_paid_by_admin",
            provider_reference=payload.provider_reference,
        )
    elif action == "fail":
        payout = await payout_service.transition(
            db,
            payout,
            to_status="failed",
            actor_user_id=admin_user.id,
            reason=payload.reason or "failed_by_admin",
        )
    elif action == "cancel":
        payout = await payout_service.transition(
            db,
            payout,
            to_status="cancelled",
            actor_user_id=admin_user.id,
            reason=payload.reason or "cancelled_by_admin",
        )
    else:
        raise ValidationException(
            "Unknown payout action",
            details={"allowed": ["approve", "process", "mark_paid", "fail", "cancel"]},
        )
    return PayoutAdminItem.model_validate(payout)


# ══════════════════════════════ Leads ════════════════════════════════════


@admin_partners_router.get(
    "/leads/all",
    response_model=OffsetPagination[LeadAdminItem],
    summary="List lead introductions",
)
async def list_leads(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[LeadAdminItem]:
    """Leads with full contact details — the sales team needs to act on them."""
    leads, total = await LeadRepository.list_admin(
        db, status=status_filter, partner_id=partner_id, page=page, size=size
    )
    items = [
        LeadAdminItem(
            **partner_service.lead_to_response(lead),
            partner_id=lead.partner_id,
            contact_email=lead.contact_email,
            contact_phone=lead.contact_phone,
            contact_title=lead.contact_title,
            use_case=lead.use_case,
            notes=lead.notes,
            converted_organization_id=lead.converted_organization_id,
        )
        for lead in leads
    ]
    return OffsetPagination[LeadAdminItem](
        items=items, total=total, page=page, size=size, pages=_pages(total, size)
    )


@admin_partners_router.patch(
    "/leads/{lead_id}/status",
    response_model=LeadAdminItem,
    summary="Advance a lead through the pipeline",
    responses={409: {"description": "Illegal lead state transition"}},
)
@audit_log(action="update_partner_lead", entity_type="partner_lead")
async def update_lead_status(
    request: Request,
    lead_id: uuid.UUID,
    payload: LeadStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> LeadAdminItem:
    """Move a lead.

    Converting requires the customer organisation and creates the Year-1
    ``introduce`` earning relationship.
    """
    lead = await LeadRepository.get_by_id(db, lead_id)
    if lead is None:
        raise ResourceNotFoundException("Lead not found")

    lead = await partner_service.transition_lead(
        db,
        lead,
        new_status=payload.status.value,
        actor_id=admin_user.id,
        reason=payload.reason,
        converted_organization_id=payload.converted_organization_id,
    )
    return LeadAdminItem(
        **partner_service.lead_to_response(lead),
        partner_id=lead.partner_id,
        contact_email=lead.contact_email,
        contact_phone=lead.contact_phone,
        contact_title=lead.contact_title,
        use_case=lead.use_case,
        notes=lead.notes,
        converted_organization_id=lead.converted_organization_id,
    )


# ═══════════════════════════ Deployment claims ═══════════════════════════


@admin_partners_router.get(
    "/claims/all",
    response_model=OffsetPagination[DeploymentClaimAdminItem],
    summary="List deployment claims",
)
async def list_claims(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[DeploymentClaimAdminItem]:
    """All deployment and creation claims, with their evidence attached,
    ready for review.
    """
    claims, total = await ClaimRepository.list_admin(
        db, status=status_filter, partner_id=partner_id, page=page, size=size
    )
    evidence_map = await ClaimRepository.list_evidence_for_claims(
        db, [c.id for c in claims]
    )
    items = []
    for claim in claims:
        item = DeploymentClaimAdminItem.model_validate(claim)
        items.append(
            item.model_copy(
                update={
                    "evidence": [
                        ClaimEvidenceResponse.model_validate(e)
                        for e in evidence_map.get(claim.id, [])
                    ]
                }
            )
        )
    return OffsetPagination[DeploymentClaimAdminItem](
        items=items, total=total, page=page, size=size, pages=_pages(total, size)
    )


@admin_partners_router.post(
    "/claims/{claim_id}/review",
    response_model=DeploymentClaimAdminItem,
    summary="Approve or reject a deployment claim",
)
@audit_log(action="review_partner_claim", entity_type="partner_deployment_claim")
async def review_claim(
    request: Request,
    claim_id: uuid.UUID,
    payload: ClaimReviewRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> DeploymentClaimAdminItem:
    """Review a claim.

    Approval creates the earning relationship at the deploy/create rate
    (optionally overridden), snapshotted at that moment.
    """
    claim = await ClaimRepository.get_by_id(db, claim_id)
    if claim is None:
        raise ResourceNotFoundException("Deployment claim not found")

    claim = await partner_service.review_claim(
        db, claim, payload, reviewer_id=admin_user.id
    )
    evidence = await ClaimRepository.list_evidence(db, claim.id)
    item = DeploymentClaimAdminItem.model_validate(claim)
    return item.model_copy(
        update={"evidence": [ClaimEvidenceResponse.model_validate(e) for e in evidence]}
    )


# ═══════════════════════════════ Fraud ═══════════════════════════════════


@admin_partners_router.get(
    "/fraud/flags",
    response_model=OffsetPagination[FraudFlagItem],
    summary="List fraud flags",
)
async def list_fraud_flags(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OffsetPagination[FraudFlagItem]:
    """Open and historical fraud flags. Each flag carries the signal that
    raised it, the score at the time and the supporting metrics.
    """
    flags, total = await FraudRepository.list_flags(
        db,
        status=status_filter,
        partner_id=partner_id,
        severity=severity,
        page=page,
        size=size,
    )
    return OffsetPagination[FraudFlagItem](
        items=[FraudFlagItem.model_validate(f) for f in flags],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@admin_partners_router.post(
    "/fraud/flags/{flag_id}/resolve",
    response_model=FraudFlagItem,
    summary="Resolve a fraud flag",
    responses={409: {"description": "Flag has already been resolved"}},
)
@audit_log(action="resolve_partner_fraud_flag", entity_type="partner_fraud_flag")
async def resolve_fraud_flag(
    request: Request,
    flag_id: uuid.UUID,
    payload: FraudFlagResolveRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> FraudFlagItem:
    """Close a flag and execute the chosen resolution.

    The resolution is carried out, not just recorded, so the flag's stated
    outcome always matches what happened to the money and the account.
    """
    flag = await FraudRepository.get_flag(db, flag_id)
    if flag is None:
        raise ResourceNotFoundException("Fraud flag not found")

    flag = await fraud_service.resolve_flag(
        db,
        flag,
        status=payload.status,
        resolution=payload.resolution,
        notes=payload.notes,
        actor_user_id=admin_user.id,
    )
    return FraudFlagItem.model_validate(flag)


@admin_partners_router.get(
    "/{partner_id}/risk",
    response_model=list[RiskAssessmentItem],
    summary="Risk assessment history for a partner",
)
async def get_partner_risk(
    request: Request,
    partner_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> list[RiskAssessmentItem]:
    """Risk assessment history for one partner, newest first, including
    the metrics each score was derived from.
    """
    await _get_partner_or_404(db, partner_id)
    assessments = await FraudRepository.list_assessments(db, partner_id, limit=limit)
    return [RiskAssessmentItem.model_validate(a) for a in assessments]


@admin_partners_router.post(
    "/{partner_id}/risk/evaluate",
    response_model=RiskAssessmentItem,
    summary="Run a risk assessment for a partner",
)
@audit_log(action="assess_partner_risk", entity_type="partner")
async def evaluate_partner_risk(
    request: Request,
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> RiskAssessmentItem:
    """Run a risk assessment immediately rather than waiting for the
    scheduled sweep. A high score holds commissions and opens flags; it
    never suspends the partner on its own.
    """
    partner = await _get_partner_or_404(db, partner_id)
    assessment = await fraud_service.assess_partner(db, partner)
    return RiskAssessmentItem.model_validate(assessment)


# ═══════════════════════════ Program content ═════════════════════════════


@admin_partners_router.get(
    "/content/all",
    response_model=list[PartnerProgramContentItem],
    summary="List partner program content blocks",
)
async def list_program_content(
    request: Request,
    locale: str = Query(default="en", max_length=10),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> list[PartnerProgramContentItem]:
    """All backend-managed program content blocks for a locale."""
    content = await ProgramContentRepository.list_published(db, locale=locale)
    return [PartnerProgramContentItem.model_validate(c) for c in content]


@admin_partners_router.put(
    "/content/{key}",
    response_model=PartnerProgramContentItem,
    summary="Create or update a partner program content block",
)
@audit_log(action="upsert_partner_content", entity_type="partner_program_content")
async def upsert_program_content(
    request: Request,
    key: str,
    payload: PartnerProgramContentItem,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerProgramContentItem:
    """Manage program copy from the backend.

    Marketing text lives here rather than in a client so it can be changed
    without a deploy.
    """
    row = await ProgramContentRepository.upsert(
        db,
        key=key,
        locale=payload.locale,
        section=payload.section,
        title=payload.title,
        body=payload.body,
        payload=payload.payload,
        sort_order=payload.sort_order,
        is_published=True,
        version=payload.version,
        updated_by_id=admin_user.id,
    )
    return PartnerProgramContentItem.model_validate(row)


# ════════════════════════════════ Geo ════════════════════════════════════


@admin_geo_router.get(
    "/countries",
    response_model=GeoAnalyticsResponse,
    summary="Country analytics",
)
async def get_country_analytics(
    request: Request,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    partner_id: uuid.UUID | None = Query(
        default=None, description="Omit for platform-wide totals"
    ),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> GeoAnalyticsResponse:
    """Aggregated per-country traffic, conversions, revenue and commission.

    Served from the pre-aggregated ``partner_geo_daily`` table written by
    the ``geo_aggregation`` job — country-level only, never city or
    coordinates.
    """
    today = date.today()
    to_date = to_date or today
    from_date = from_date or (to_date - timedelta(days=29))
    if from_date > to_date:
        raise ValidationException("from_date must not be after to_date")

    rows = await GeoRepository.country_totals(
        db, start=from_date, end=to_date, partner_id=partner_id
    )
    countries = [
        CountryStatsItem(
            country_code=code,
            country_name=name,
            clicks=clicks,
            unique_visitors=uniques,
            signups=signups,
            conversions=conversions,
            revenue_minor=revenue,
            commission_minor=commission,
        )
        for code, name, clicks, uniques, signups, conversions, revenue, commission in rows
    ]
    return GeoAnalyticsResponse(
        from_date=from_date,
        to_date=to_date,
        currency="USD",
        total_countries=len(countries),
        countries=countries,
    )


@admin_geo_router.get(
    "/coverage",
    response_model=GeoCoverageResponse,
    summary="GeoIP database and cache status",
)
async def get_geo_coverage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> GeoCoverageResponse:
    """Operational status of the local MaxMind database and lookup cache.

    Use ``database_age_days`` to monitor whether the GeoLite2 file is being
    refreshed.
    """
    coverage = await GeoService.coverage(db)
    return GeoCoverageResponse(**coverage)


__all__ = ["admin_geo_router", "admin_partners_router"]
