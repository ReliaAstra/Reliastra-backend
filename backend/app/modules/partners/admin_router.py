"""Admin API for the Partner Referral program — ``/v1/admin/partners/*``.

Every route depends on :func:`require_system_admin`. Mutations carry the
``@audit_log`` decorator (writes to ``admin_audit_logs``) and the services
additionally write domain audit entries to ``audit_logs``.

The admin panel answers five questions — who, customers, money, payout,
control — and nothing more.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException
from app.db.session import get_db
from app.modules.admin.decorators import audit_log
from app.modules.admin.guards import require_system_admin
from app.modules.partners.commissions import commission_service
from app.modules.partners.payouts import payout_service
from app.modules.partners.repository import (
    PartnerCommissionRepository,
    PartnerPayoutRepository,
    PartnerProfileRepository,
    PartnerReferralRepository,
)
from app.modules.partners.schemas import (
    AdminCommissionItem,
    AdminCommissionListResponse,
    AdminPayoutItem,
    AdminPayoutListResponse,
    CommissionReverseRequest,
    PartnerAdminItem,
    PartnerAdminListResponse,
    PartnerStatsResponse,
    PartnerStatusUpdateRequest,
    PayoutCreateRequest,
    PayoutProcessRequest,
)
from app.modules.partners.service import (
    _period_month,
    mask_email,
    partner_service,
)
from app.modules.referrals.models import ReferralCode
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

admin_partners_router = APIRouter(
    prefix="/v1/admin/partners", tags=["Admin — Partners"]
)


async def _referral_code_for(session: AsyncSession, code_id: uuid.UUID | None) -> str:
    if not code_id:
        return ""
    result = await session.execute(
        select(ReferralCode).where(ReferralCode.id == code_id)
    )
    rc = result.scalar_one_or_none()
    return rc.code if rc else ""


async def _email_for(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    user = await UserRepository.get_by_id(session, user_id)
    return user.email if user else None


async def _admin_item(session: AsyncSession, profile) -> PartnerAdminItem:
    now_period = _period_month(datetime.now(timezone.utc))
    signups = await PartnerReferralRepository.count_by_partner(session, profile.id)
    active_paid = await PartnerReferralRepository.count_by_partner(
        session, profile.id, status="paid"
    )
    monthly = await PartnerCommissionRepository.sum_amount_by_partner(
        session, profile.id, statuses=[], period=now_period
    )
    total_earned = await PartnerCommissionRepository.sum_amount_by_partner(
        session, profile.id, statuses=[]
    )
    total_paid = await PartnerCommissionRepository.sum_amount_by_partner(
        session, profile.id, statuses=["paid"]
    )
    return PartnerAdminItem(
        partner_id=profile.id,
        user_id=profile.user_id,
        email=await _email_for(session, profile.user_id) or "",
        referral_code=await _referral_code_for(session, profile.referral_code_id),
        status=profile.status,
        referred_signups=signups,
        active_paid_customers=active_paid,
        monthly_commission_minor=monthly,
        total_earned_minor=total_earned,
        total_paid_minor=total_paid,
        currency="USD",
        created_at=profile.created_at,
    )


# ═══════════════════════════ Partner list ════════════════════════════════


@admin_partners_router.get(
    "", response_model=PartnerAdminListResponse, summary="List partners"
)
async def list_partners(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerAdminListResponse:
    offset = (page - 1) * page_size
    profiles, total = await PartnerProfileRepository.list_all(
        db, status=status, search=search, offset=offset, limit=page_size
    )
    items = [await _admin_item(db, p) for p in profiles]
    return PartnerAdminListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


# ═══════════════════════════ Stats ═══════════════════════════════════════


@admin_partners_router.get(
    "/stats", response_model=PartnerStatsResponse, summary="Partner program stats"
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> PartnerStatsResponse:
    from sqlalchemy import func

    from app.modules.partners.models import (
        PartnerCommission,
        PartnerProfile,
        PartnerReferral,
    )

    now_period = _period_month(datetime.now(timezone.utc))

    async def _count(model) -> int:
        return int((await db.execute(select(func.count()).select_from(model))).scalar() or 0)

    async def _sum(column, *conditions) -> int:
        q = select(func.coalesce(func.sum(column), 0))
        for cond in conditions:
            q = q.where(cond)
        return int((await db.execute(q)).scalar() or 0)

    total_partners = await _count(PartnerProfile)
    active_partners = int(
        (
            await db.execute(
                select(func.count())
                .select_from(PartnerProfile)
                .where(PartnerProfile.status == "active")
            )
        ).scalar()
        or 0
    )
    total_signups = await _count(PartnerReferral)
    active_paid = int(
        (
            await db.execute(
                select(func.count())
                .select_from(PartnerReferral)
                .where(PartnerReferral.status == "paid")
            )
        ).scalar()
        or 0
    )
    monthly_revenue = await _sum(
        PartnerCommission.subscription_amount_minor,
        PartnerCommission.period == now_period,
        PartnerCommission.status != "reversed",
    )
    monthly_commission = await _sum(
        PartnerCommission.commission_amount_minor,
        PartnerCommission.period == now_period,
        PartnerCommission.status != "reversed",
    )
    total_paid = await _sum(
        PartnerCommission.commission_amount_minor,
        PartnerCommission.status == "paid",
    )
    pending = await _sum(
        PartnerCommission.commission_amount_minor,
        PartnerCommission.status.in_(["pending", "payable"]),
    )

    return PartnerStatsResponse(
        total_partners=total_partners,
        active_partners=active_partners,
        total_referred_signups=total_signups,
        total_active_paid_customers=active_paid,
        monthly_referred_revenue_minor=monthly_revenue,
        monthly_commission_minor=monthly_commission,
        total_commission_paid_minor=total_paid,
        pending_commission_minor=pending,
        currency="USD",
    )


# ═══════════════════════════ Commissions ═════════════════════════════════


@admin_partners_router.get(
    "/commissions",
    response_model=AdminCommissionListResponse,
    summary="List commissions (admin)",
)
async def list_commissions(
    partner_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    period: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> AdminCommissionListResponse:
    offset = (page - 1) * page_size
    rows, total = await PartnerCommissionRepository.list_all(
        db,
        partner_id=partner_id,
        status=status,
        period=period,
        offset=offset,
        limit=page_size,
    )
    items: list[AdminCommissionItem] = []
    for c in rows:
        partner = await PartnerProfileRepository.get_by_id(db, c.partner_id)
        partner_email = (
            await _email_for(db, partner.user_id) if partner else None
        )
        referral = (
            await PartnerReferralRepository.get_by_id(db, c.referral_id)
            if c.referral_id
            else None
        )
        referred_email = None
        if referral:
            referred_email = await _email_for(db, referral.referred_user_id)
        items.append(
            AdminCommissionItem(
                commission_id=c.id,
                partner_id=c.partner_id,
                partner_email=partner_email,
                referral_id=c.referral_id,
                referred_email=referred_email,
                period=c.period,
                subscription_amount_minor=c.subscription_amount_minor,
                commission_amount_minor=c.commission_amount_minor,
                currency=c.currency,
                status=c.status,
                created_at=c.created_at,
                paid_at=c.paid_at,
            )
        )
    return AdminCommissionListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


@admin_partners_router.post(
    "/commissions/{commission_id}/reverse",
    summary="Reverse a commission",
)
@audit_log(action="reverse_commission", entity_type="partner_commission")
async def reverse_commission(
    commission_id: uuid.UUID,
    body: CommissionReverseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict:
    await commission_service.reverse_commission(db, commission_id, body.reason)
    return {"commission_id": str(commission_id), "status": "reversed"}


# ═══════════════════════════ Payouts ═════════════════════════════════════


@admin_partners_router.get(
    "/payouts", response_model=AdminPayoutListResponse, summary="List payouts"
)
async def list_payouts(
    status: str | None = Query(default=None),
    partner_id: uuid.UUID | None = Query(default=None),
    period: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> AdminPayoutListResponse:
    offset = (page - 1) * page_size
    rows, total = await PartnerPayoutRepository.list_all(
        db,
        status=status,
        partner_id=partner_id,
        period=period,
        offset=offset,
        limit=page_size,
    )
    items: list[AdminPayoutItem] = []
    for p in rows:
        partner = await PartnerProfileRepository.get_by_id(db, p.partner_id)
        items.append(
            AdminPayoutItem(
                id=p.id,
                partner_id=p.partner_id,
                partner_email=(await _email_for(db, partner.user_id) if partner else None),
                period=p.period,
                amount_minor=p.amount_minor,
                currency=p.currency,
                status=p.status,
                transaction_reference=p.transaction_reference,
                requested_at=p.created_at,
                paid_at=p.paid_at,
            )
        )
    return AdminPayoutListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


@admin_partners_router.post(
    "/payouts", summary="Create a payout from a partner's payable balance"
)
@audit_log(action="create_payout", entity_type="partner_payout")
async def create_payout(
    body: PayoutCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict:
    payout = await payout_service.create_payout(
        db, body.partner_id, body.amount_minor
    )
    return {
        "payout_id": str(payout.id),
        "partner_id": str(payout.partner_id),
        "amount_minor": payout.amount_minor,
        "status": payout.status,
    }


@admin_partners_router.post(
    "/payouts/{payout_id}/process", summary="Process a payout (mark paid/failed)"
)
@audit_log(action="process_payout", entity_type="partner_payout")
async def process_payout(
    payout_id: uuid.UUID,
    body: PayoutProcessRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict:
    payout = await payout_service.process_payout(
        db, payout_id, body.action, body.transaction_reference
    )
    return {
        "payout_id": str(payout.id),
        "status": payout.status,
        "transaction_reference": payout.transaction_reference,
    }


# ═══════════════════════════ Partner detail / status ═════════════════════


@admin_partners_router.get(
    "/{partner_id}", summary="Partner detail (admin)"
)
async def get_partner_detail(
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict:
    profile = await PartnerProfileRepository.get_by_id(db, partner_id)
    if profile is None:
        raise ResourceNotFoundException("Partner not found")

    referrals, _ = await PartnerReferralRepository.list_by_partner(
        db, profile.id, offset=0, limit=100
    )
    referred = []
    for r in referrals:
        email = await _email_for(db, r.referred_user_id)
        referred.append(
            {
                "referral_id": str(r.id),
                "referred_user_id": str(r.referred_user_id),
                "email": email,
                "masked_email": mask_email(email) if email else None,
                "status": r.status,
                "created_at": r.created_at,
                "subscribed_at": r.subscribed_at,
            }
        )

    commissions, _ = await PartnerCommissionRepository.list_by_partner(
        db, profile.id, offset=0, limit=100
    )
    commission_history = [
        {
            "commission_id": str(c.id),
            "period": c.period,
            "subscription_amount_minor": c.subscription_amount_minor,
            "commission_amount_minor": c.commission_amount_minor,
            "currency": c.currency,
            "rate": c.rate,
            "status": c.status,
            "created_at": c.created_at,
            "paid_at": c.paid_at,
        }
        for c in commissions
    ]

    payouts, _ = await PartnerPayoutRepository.list_by_partner(
        db, profile.id, offset=0, limit=100
    )
    payout_history = [
        {
            "payout_id": str(p.id),
            "amount_minor": p.amount_minor,
            "currency": p.currency,
            "status": p.status,
            "period": p.period,
            "transaction_reference": p.transaction_reference,
            "paid_at": p.paid_at,
        }
        for p in payouts
    ]

    summary = {
        "total_earned_minor": await PartnerCommissionRepository.sum_amount_by_partner(
            db, profile.id, statuses=[]
        ),
        "total_paid_minor": await PartnerCommissionRepository.sum_amount_by_partner(
            db, profile.id, statuses=["paid"]
        ),
        "pending_commission_minor": await PartnerCommissionRepository.sum_amount_by_partner(
            db, profile.id, statuses=["pending", "payable"]
        ),
        "payable_balance_minor": await payout_service.payable_balance(db, profile.id),
    }

    return {
        "partner_id": str(profile.id),
        "user_id": str(profile.user_id),
        "email": await _email_for(db, profile.user_id),
        "referral_code": await _referral_code_for(db, profile.referral_code_id),
        "status": profile.status,
        "created_at": profile.created_at,
        "commission_summary": summary,
        "referred_customers": referred,
        "commission_history": commission_history,
        "payout_history": payout_history,
    }


@admin_partners_router.patch(
    "/{partner_id}", summary="Update partner status"
)
@audit_log(action="update_partner_status", entity_type="partner")
async def update_partner_status(
    partner_id: uuid.UUID,
    body: PartnerStatusUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> dict:
    profile = await PartnerProfileRepository.get_by_id(db, partner_id)
    if profile is None:
        raise ResourceNotFoundException("Partner not found")

    await PartnerProfileRepository.update(db, profile, status=body.status)
    await AuditLogService.log_event(
        session=db,
        event_type="partner_status_changed",
        user_id=admin_user.id,
        resource_type="partner",
        resource_id=str(profile.id),
        payload={"status": body.status, "reason": body.reason},
    )
    return {"partner_id": str(profile.id), "status": body.status}
