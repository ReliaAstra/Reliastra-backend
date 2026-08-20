"""Admin control-plane router.

Canonical surface (≈25–30 high-leverage endpoints):

    GET  /v1/admin/overview
    GET  /v1/admin/attention
    GET  /v1/admin/search

    /v1/admin/customers/*
    /v1/admin/revenue/*
    /v1/admin/growth/*
    /v1/admin/product/*
    /v1/admin/support/*
    /v1/admin/communications/*
    /v1/admin/operations/*
    /v1/admin/audit-log
    /v1/admin/partners/*   (separate module)

Legacy module-oriented routes under /business, /analytics, /users remain
registered and marked deprecated for backward compatibility.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user
from app.db.session import get_db
from app.modules.admin.control_plane_schemas import (
    AdminOverviewResponse,
    AdminSearchResponse,
    AttentionResponse,
    CommunicationsOverviewResponse,
    CustomerDeactivateRequest,
    CustomerDetailResponse,
    CustomerEmailRequest,
    CustomerImpersonateRequest,
    CustomerImpersonateResponse,
    CustomerListResponse,
    CustomerPlanRequest,
    CustomerUpdateRequest,
    GrowthFunnelResponse,
    GrowthOverviewResponse,
    GrowthReferralsResponse,
    OperationsOverviewResponse,
    ProductActivationResponse,
    ProductEngagementResponse,
    ProductFeaturesResponse,
    ProductOverviewResponse,
    ProductVendorsResponse,
    RevenueAttentionResponse,
    RevenueSummaryResponse,
    RevenueTimeseriesResponse,
    SupportOverviewResponse,
    SupportTicketWorkspaceResponse,
)
from app.modules.admin.control_plane_service import admin_control_plane_service
from app.modules.admin.decorators import audit_log
from app.modules.admin.guards import require_system_admin
from app.modules.admin.schemas import (
    AdminSendEmailRequest,
    AdminUserUpdateRequest,
    AnnouncementCreateRequest,
    AnnouncementUpdateRequest,
    EmailCampaignCreateRequest,
    EmailCampaignUpdateRequest,
    FeedbackBulkUpdateRequest,
    FeedbackMessageCreateRequest,
    FeedbackTicketCreateRequest,
    FeedbackTicketUpdateRequest,
    ImpersonationTokenResponse,
    InAppNotificationCreateRequest,
    OverridePlanRequest,
    PublicAnnouncementsResponse,
)
from app.modules.admin.service import (
    admin_analytics_service,
    admin_business_service,
    admin_communication_service,
    admin_feedback_service,
    admin_operations_service,
    admin_user_service,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)


# =============================================================================
# Overview / Attention / Search — admin home bootstrap
# =============================================================================

overview_router = APIRouter(
    prefix="/v1/admin",
    tags=["Admin — Overview"],
)


@overview_router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Admin home bootstrap",
    description=(
        "Primary admin bootstrap endpoint. One request returns business health, "
        "growth, product, support, communications, system health, and actions_required."
    ),
)
async def get_admin_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> AdminOverviewResponse:
    return await admin_control_plane_service.get_overview(db)


@overview_router.get(
    "/attention",
    response_model=AttentionResponse,
    summary="Action-required portfolio alerts",
    description="Prioritized operational alerts: support, revenue risk, system health, partners.",
)
async def get_admin_attention(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> AttentionResponse:
    return await admin_control_plane_service.get_attention(db)


@overview_router.get(
    "/search",
    response_model=AdminSearchResponse,
    summary="Global admin search",
    description="Search customers, organizations, tickets, partners, and campaigns.",
)
async def admin_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(default=8, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> AdminSearchResponse:
    return await admin_control_plane_service.search(db, q, limit=limit)


# =============================================================================
# Customers — operational customer control plane
# =============================================================================

customers_router = APIRouter(
    prefix="/v1/admin/customers",
    tags=["Admin — Customers"],
)


@customers_router.get(
    "",
    response_model=CustomerListResponse,
    summary="List customers",
)
async def list_customers(
    request: Request,
    search: str | None = Query(default=None),
    status: str | None = Query(default=None, description="active|inactive"),
    plan: str | None = Query(default=None),
    segment: str | None = Query(
        default=None, description="Optional customer segment filter"
    ),
    health: str | None = Query(
        default=None, description="healthy|at_risk|churning|inactive"
    ),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="created_at_desc"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CustomerListResponse:
    return await admin_control_plane_service.list_customers(
        db,
        search=search,
        status=status,
        plan=plan,
        segment=segment,
        health=health,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        sort=sort,
    )


@customers_router.get(
    "/recent",
    summary="Recent customer signups",
)
async def get_recent_customers(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.get_recent_customers(db, limit=limit)


@customers_router.get(
    "/churn-risk",
    summary="Customers / orgs at churn risk",
)
async def get_churn_risk_customers(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.get_churn_risk(db, limit=limit)


@customers_router.get(
    "/{customer_id}",
    response_model=CustomerDetailResponse,
    summary="Customer workspace snapshot",
    description=(
        "Consolidated customer view: profile, orgs, plan, MRR, product usage, "
        "support, billing, and recent activity."
    ),
)
async def get_customer(
    request: Request,
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CustomerDetailResponse:
    return await admin_control_plane_service.get_customer_detail(db, customer_id)


@customers_router.patch(
    "/{customer_id}",
    response_model=CustomerDetailResponse,
    summary="Update customer profile (safe fields only)",
)
@audit_log(action="update_customer", entity_type="customer")
async def update_customer(
    request: Request,
    customer_id: uuid.UUID,
    body: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CustomerDetailResponse:
    return await admin_control_plane_service.update_customer(
        db,
        customer_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        **body.model_dump(exclude_none=True),
    )


@customers_router.post(
    "/{customer_id}/impersonate",
    response_model=CustomerImpersonateResponse,
    summary="Impersonate customer (security-sensitive)",
)
async def impersonate_customer(
    request: Request,
    customer_id: uuid.UUID,
    body: CustomerImpersonateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CustomerImpersonateResponse:
    return await admin_control_plane_service.impersonate_customer(
        db,
        customer_id,
        reason=body.reason,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@customers_router.post(
    "/{customer_id}/plan",
    summary="Override customer organization plan",
)
@audit_log(action="override_plan", entity_type="organization")
async def change_customer_plan(
    request: Request,
    customer_id: uuid.UUID,
    body: CustomerPlanRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.change_customer_plan(
        db,
        customer_id,
        plan=body.plan,
        reason=body.reason,
        org_id=body.org_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@customers_router.post(
    "/{customer_id}/email",
    summary="Send email to customer",
)
@audit_log(action="send_email_to_customer", entity_type="customer")
async def email_customer(
    request: Request,
    customer_id: uuid.UUID,
    body: CustomerEmailRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.email_customer(
        db,
        customer_id,
        subject=body.subject,
        body=body.body,
        html_body=body.html_body,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@customers_router.post(
    "/{customer_id}/deactivate",
    response_model=CustomerDetailResponse,
    summary="Deactivate customer account",
)
@audit_log(action="deactivate_customer", entity_type="customer")
async def deactivate_customer(
    request: Request,
    customer_id: uuid.UUID,
    body: CustomerDeactivateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CustomerDetailResponse:
    return await admin_control_plane_service.deactivate_customer(
        db,
        customer_id,
        reason=body.reason,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@customers_router.get(
    "/{customer_id}/activity",
    summary="Customer activity timeline",
)
async def get_customer_activity(
    request: Request,
    customer_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.get_customer_activity(
        db, customer_id, page=page, page_size=page_size
    )


# =============================================================================
# Revenue
# =============================================================================

revenue_router = APIRouter(
    prefix="/v1/admin/revenue",
    tags=["Admin — Revenue"],
)


@revenue_router.get(
    "/summary",
    response_model=RevenueSummaryResponse,
    summary="Revenue summary",
)
async def get_revenue_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> RevenueSummaryResponse:
    return await admin_control_plane_service.get_revenue_summary(db)


@revenue_router.get(
    "/timeseries",
    response_model=RevenueTimeseriesResponse,
    summary="Revenue timeseries",
)
async def get_revenue_timeseries(
    request: Request,
    period: str = Query(default="30d", pattern="^(7d|30d|90d|365d)$"),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> RevenueTimeseriesResponse:
    return await admin_control_plane_service.get_revenue_timeseries(
        db, period=period, granularity=granularity
    )


@revenue_router.get(
    "/attention",
    response_model=RevenueAttentionResponse,
    summary="Revenue events needing attention",
)
async def get_revenue_attention(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> RevenueAttentionResponse:
    return await admin_control_plane_service.get_revenue_attention(db)


# =============================================================================
# Growth (canonical — consolidates analytics + growth modules)
# =============================================================================

growth_cp_router = APIRouter(
    prefix="/v1/admin/growth",
    tags=["Admin — Growth"],
)


@growth_cp_router.get(
    "/overview",
    response_model=GrowthOverviewResponse,
    summary="Growth overview",
)
async def get_growth_overview(
    request: Request,
    period: str = Query(default="30d"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> GrowthOverviewResponse:
    return await admin_control_plane_service.get_growth_overview(db, period=period)


@growth_cp_router.get(
    "/funnel",
    response_model=GrowthFunnelResponse,
    summary="Canonical growth funnel",
    description="Signup → verified → org → dependency → monitoring → paid.",
)
async def get_growth_funnel(
    request: Request,
    period: str = Query(default="30d"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> GrowthFunnelResponse:
    return await admin_control_plane_service.get_growth_funnel(db, period=period)


@growth_cp_router.get(
    "/retention",
    summary="Cohort retention",
)
async def get_growth_retention(
    request: Request,
    weeks: int = Query(default=4, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_control_plane_service.get_growth_retention(db, weeks=weeks)


@growth_cp_router.get(
    "/referrals",
    response_model=GrowthReferralsResponse,
    summary="Product referral analytics (PLG)",
    description=(
        "Generic product referral stats. Partner-program stats live under "
        "/v1/admin/partners/stats."
    ),
)
async def get_growth_referrals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> GrowthReferralsResponse:
    return await admin_control_plane_service.get_growth_referrals(db)


# =============================================================================
# Product
# =============================================================================

product_router = APIRouter(
    prefix="/v1/admin/product",
    tags=["Admin — Product"],
)


@product_router.get(
    "/overview",
    response_model=ProductOverviewResponse,
    summary="Product overview",
)
async def get_product_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> ProductOverviewResponse:
    return await admin_control_plane_service.get_product_overview(db)


@product_router.get(
    "/features",
    response_model=ProductFeaturesResponse,
    summary="Feature adoption",
)
async def get_product_features(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> ProductFeaturesResponse:
    return await admin_control_plane_service.get_product_features(db)


@product_router.get(
    "/vendors",
    response_model=ProductVendorsResponse,
    summary="Vendor coverage + engagement",
)
async def get_product_vendors(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> ProductVendorsResponse:
    return await admin_control_plane_service.get_product_vendors(db, limit=limit)


@product_router.get(
    "/engagement",
    response_model=ProductEngagementResponse,
    summary="DAU / WAU / MAU engagement",
)
async def get_product_engagement(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> ProductEngagementResponse:
    return await admin_control_plane_service.get_product_engagement(db)


@product_router.get(
    "/activation",
    response_model=ProductActivationResponse,
    summary="Activation / time-to-value",
)
async def get_product_activation(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> ProductActivationResponse:
    return await admin_control_plane_service.get_product_activation(db)


# =============================================================================
# Support
# =============================================================================

support_router = APIRouter(
    prefix="/v1/admin/support",
    tags=["Admin — Support"],
)


@support_router.get(
    "/overview",
    response_model=SupportOverviewResponse,
    summary="Support triage overview",
)
async def get_support_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> SupportOverviewResponse:
    return await admin_control_plane_service.get_support_overview(db)


@support_router.get("/tickets")
async def list_tickets(
    request: Request,
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List support tickets with filters and pagination."""
    return await admin_feedback_service.list_tickets(
        db,
        status=status,
        category=category,
        priority=priority,
        assigned_to=assigned_to,
        search=search,
        page=page,
        page_size=page_size,
    )


@support_router.get(
    "/tickets/stats",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/support/overview",
)
async def get_ticket_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_feedback_service.get_stats(db)


@support_router.get(
    "/tickets/{ticket_id}",
    response_model=SupportTicketWorkspaceResponse,
    summary="Support ticket workspace",
    description=(
        "Complete support workspace: ticket, messages, customer, organization, "
        "subscription, recent activity."
    ),
)
async def get_ticket(
    request: Request,
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> SupportTicketWorkspaceResponse:
    return await admin_control_plane_service.get_support_ticket_workspace(db, ticket_id)


@support_router.post("/tickets")
@audit_log(action="create_ticket", entity_type="feedback_ticket")
async def create_ticket(
    request: Request,
    body: FeedbackTicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Create a new support ticket on behalf of a user."""
    return await admin_feedback_service.create_ticket(
        db,
        email=body.email,
        full_name=body.full_name,
        category=body.category,
        subject=body.subject,
        body=body.body,
        priority=body.priority,
        source=body.source,
    )


@support_router.patch("/tickets/{ticket_id}")
@audit_log(action="update_ticket", entity_type="feedback_ticket")
async def update_ticket(
    request: Request,
    ticket_id: uuid.UUID,
    body: FeedbackTicketUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Update a ticket's status, priority, assignment, or resolution."""
    return await admin_feedback_service.update_ticket(
        db,
        ticket_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        **body.model_dump(exclude_none=True),
    )


@support_router.post("/tickets/{ticket_id}/reply")
@audit_log(action="reply_to_ticket", entity_type="feedback_ticket")
async def reply_to_ticket(
    request: Request,
    ticket_id: uuid.UUID,
    body: FeedbackMessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Reply to a ticket (or add an internal note via is_internal_note=true)."""
    return await admin_feedback_service.reply_to_ticket(
        db,
        ticket_id,
        body,
        admin_user_id=admin_user.id,
        admin_name=admin_user.full_name,
    )


@support_router.post("/tickets/bulk-update")
@audit_log(action="bulk_update_tickets", entity_type="feedback_ticket")
async def bulk_update_tickets(
    request: Request,
    body: FeedbackBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Bulk update multiple tickets' status, priority, or assignment."""
    return await admin_feedback_service.bulk_update_tickets(
        db,
        body,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


# =============================================================================
# Communications
# =============================================================================

communications_router = APIRouter(
    prefix="/v1/admin/communications",
    tags=["Admin — Communications"],
)


@communications_router.get(
    "/overview",
    response_model=CommunicationsOverviewResponse,
    summary="Communications overview",
)
async def get_communications_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> CommunicationsOverviewResponse:
    return await admin_control_plane_service.get_communications_overview(db)


# -- Email Campaigns --

@communications_router.post("/campaigns")
async def create_email_campaign(
    request: Request,
    body: EmailCampaignCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Create a new email campaign (draft)."""
    return await admin_communication_service.create_campaign(
        db,
        campaign_name=body.campaign_name,
        subject=body.subject,
        body_html=body.body_html,
        body_text=body.body_text,
        segment=body.segment,
        utm_campaign=body.utm_campaign,
        scheduled_at=body.scheduled_at,
        created_by=admin_user.id,
    )


@communications_router.get("/campaigns")
async def list_email_campaigns(
    request: Request,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List email campaigns with optional status filter."""
    return await admin_communication_service.list_campaigns(
        db, status=status, page=page, page_size=page_size,
    )


@communications_router.get("/campaigns/{campaign_id}")
async def get_email_campaign(
    request: Request,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Get a single email campaign by ID (includes delivery metrics)."""
    return await admin_communication_service.get_campaign(db, campaign_id)


@communications_router.patch("/campaigns/{campaign_id}")
async def update_email_campaign(
    request: Request,
    campaign_id: uuid.UUID,
    body: EmailCampaignUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Update an email campaign (draft only)."""
    return await admin_communication_service.update_campaign(
        db, campaign_id, **body.model_dump(exclude_none=True),
    )


@communications_router.post("/campaigns/{campaign_id}/send")
@audit_log(action="send_campaign", entity_type="email_campaign")
async def send_email_campaign(
    request: Request,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Send/distribute an email campaign to recipients (idempotent against re-send)."""
    return await admin_communication_service.send_campaign(
        db,
        campaign_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


# -- In-App Notifications --

@communications_router.post("/notifications")
async def create_notification(
    request: Request,
    body: InAppNotificationCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Create a new in-app notification (draft)."""
    return await admin_communication_service.create_notification(
        db,
        title=body.title,
        body=body.body,
        notification_type=body.notification_type,
        action_url=body.action_url,
        action_label=body.action_label,
        priority=body.priority,
        expires_at=body.expires_at,
        is_dismissible=body.is_dismissible,
        created_by=admin_user.id,
    )


@communications_router.get("/notifications")
async def list_notifications(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List all in-app notifications."""
    return await admin_communication_service.list_notifications(
        db, page=page, page_size=page_size,
    )


# -- Announcements --

@communications_router.post("/announcements")
@audit_log(action="create_announcement", entity_type="announcement")
async def create_announcement(
    request: Request,
    body: AnnouncementCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Create a new banner/modal announcement."""
    return await admin_communication_service.create_announcement(
        db,
        title=body.title,
        body_html=body.body_html,
        placement=body.placement,
        target_plans=body.target_plans,
        target_segment=body.target_segment,
        action_url=body.action_url,
        action_label=body.action_label,
        is_dismissible=body.is_dismissible,
        bg_color=body.bg_color,
        text_color=body.text_color,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
        created_by=admin_user.id,
    )


@communications_router.get("/announcements")
async def list_announcements(
    request: Request,
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List all announcements (admin view with stats)."""
    return await admin_communication_service.list_announcements(
        db, is_active=is_active, page=page, page_size=page_size,
    )


@communications_router.get("/announcements/{announcement_id}")
async def get_announcement(
    request: Request,
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Get a single announcement by ID."""
    return await admin_communication_service.get_announcement(db, announcement_id)


@communications_router.patch("/announcements/{announcement_id}")
@audit_log(action="update_announcement", entity_type="announcement")
async def update_announcement(
    request: Request,
    announcement_id: uuid.UUID,
    body: AnnouncementUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Update an existing announcement (lifecycle: draft/published/expired via is_active + dates)."""
    return await admin_communication_service.update_announcement(
        db, announcement_id, **body.model_dump(exclude_none=True),
    )


# =============================================================================
# Operations
# =============================================================================

operations_router = APIRouter(
    prefix="/v1/admin/operations",
    tags=["Admin — Operations"],
)


@operations_router.get(
    "/overview",
    response_model=OperationsOverviewResponse,
    summary="Operations health overview",
)
async def get_operations_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
) -> OperationsOverviewResponse:
    return await admin_control_plane_service.get_operations_overview(db)


@operations_router.get(
    "/errors",
    summary="System error logs",
)
async def list_error_logs(
    request: Request,
    level: str | None = Query(default=None),
    is_resolved: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Paginated application error logs with filters."""
    return await admin_operations_service.list_error_logs(
        db,
        level=level,
        is_resolved=is_resolved,
        page=page,
        page_size=page_size,
    )


@operations_router.get(
    "/error-logs",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/operations/errors",
)
async def list_error_logs_legacy(
    request: Request,
    level: str | None = Query(default=None),
    is_resolved: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_operations_service.list_error_logs(
        db,
        level=level,
        is_resolved=is_resolved,
        page=page,
        page_size=page_size,
    )


@operations_router.get("/metrics")
async def get_system_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """System-wide aggregated metrics (users, orgs, deps, incidents, pool)."""
    return await admin_operations_service.get_metrics(db)


@operations_router.get(
    "/health",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/operations/overview",
)
async def health_check_legacy(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_operations_service.health_check(db)


@operations_router.get(
    "/check-engines",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/operations/overview",
)
async def check_engines_legacy(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_operations_service.check_engines(db)


# =============================================================================
# Audit Log
# =============================================================================

audit_router = APIRouter(
    prefix="/v1/admin/audit-log",
    tags=["Admin — Audit Log"],
)


@audit_router.get("")
async def list_audit_logs(
    request: Request,
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor: uuid.UUID | None = Query(default=None, description="Filter by admin_user_id"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List admin audit log entries with filters."""
    from app.modules.admin.repository import AdminAuditRepository
    from app.modules.admin.schemas import AuditLogItem, AuditLogListResponse
    from app.modules.admin.models import AdminAuditLog
    from sqlalchemy import select, func, or_

    query = select(AdminAuditLog)
    count_q = select(func.count()).select_from(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action == action)
        count_q = count_q.where(AdminAuditLog.action == action)
    if entity_type:
        query = query.where(AdminAuditLog.entity_type == entity_type)
        count_q = count_q.where(AdminAuditLog.entity_type == entity_type)
    if actor:
        query = query.where(AdminAuditLog.admin_user_id == actor)
        count_q = count_q.where(AdminAuditLog.admin_user_id == actor)
    if search:
        pattern = f"%{search}%"
        filt = or_(
            AdminAuditLog.admin_email.ilike(pattern),
            AdminAuditLog.action.ilike(pattern),
            AdminAuditLog.entity_id.ilike(pattern),
        )
        query = query.where(filt)
        count_q = count_q.where(filt)

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(l) for l in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# DEPRECATED — Business (→ overview / revenue / customers)
# =============================================================================

business_router = APIRouter(
    prefix="/v1/admin/business",
    tags=["Admin — Business (deprecated)"],
    deprecated=True,
)


@business_router.get(
    "/summary",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/overview or /v1/admin/revenue/summary",
)
async def get_business_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_business_service.get_summary(db)


@business_router.get(
    "/mrr-timeseries",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/revenue/timeseries",
)
async def get_mrr_timeseries(
    request: Request,
    days: int = Query(default=30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_business_service.get_mrr_timeseries(db, days=days)


@business_router.get(
    "/recent-signups",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/customers/recent",
)
async def get_recent_signups(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_business_service.get_recent_signups(db, limit=limit)


@business_router.get(
    "/churn-signals",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/customers/churn-risk",
)
async def get_churn_signals(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_business_service.get_churn_signals(db, limit=limit)


# =============================================================================
# DEPRECATED — Analytics (→ growth / product)
# =============================================================================

analytics_router = APIRouter(
    prefix="/v1/admin/analytics",
    tags=["Admin — Analytics (deprecated)"],
    deprecated=True,
)


@analytics_router.get(
    "/growth-funnel",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/growth/funnel",
)
async def get_analytics_growth_funnel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_growth_funnel(db)


@analytics_router.get(
    "/retention",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/growth/retention",
)
async def get_analytics_retention(
    request: Request,
    weeks: int = Query(default=4, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_retention(db, weeks=weeks)


@analytics_router.get(
    "/feature-adoption",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/product/features",
)
async def get_feature_adoption(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_feature_adoption(db)


@analytics_router.get(
    "/vendor-coverage",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/product/vendors",
)
async def get_vendor_coverage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_vendor_coverage(db)


@analytics_router.get(
    "/time-to-value",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/product/activation",
)
async def get_time_to_value(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_time_to_value(db)


@analytics_router.get(
    "/engagement",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/product/engagement",
)
async def get_engagement(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_analytics_service.get_engagement(db)


# =============================================================================
# DEPRECATED — Users (→ customers)
# =============================================================================

users_router = APIRouter(
    prefix="/v1/admin/users",
    tags=["Admin — Users (deprecated)"],
    deprecated=True,
)


@users_router.get(
    "",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/customers",
)
async def list_users(
    request: Request,
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    is_system_admin: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.search_users(
        db,
        search=search,
        is_active=is_active,
        is_system_admin=is_system_admin,
        source=source,
        page=page,
        page_size=page_size,
    )


@users_router.get(
    "/{user_id}",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/customers/{customer_id}",
)
async def get_user_detail(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.get_user_detail(db, user_id)


@users_router.patch(
    "/{user_id}",
    deprecated=True,
    summary="[Deprecated] Use PATCH /v1/admin/customers/{customer_id}",
)
async def update_user(
    request: Request,
    user_id: uuid.UUID,
    body: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.update_user(
        db,
        user_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        **body.model_dump(exclude_none=True),
    )


@users_router.post(
    "/{user_id}/impersonate",
    response_model=ImpersonationTokenResponse,
    deprecated=True,
    summary="[Deprecated] Use POST /v1/admin/customers/{customer_id}/impersonate",
)
@audit_log(action="impersonate_user", entity_type="user")
async def impersonate_user(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.impersonate(
        db,
        user_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@users_router.post(
    "/override-plan",
    deprecated=True,
    summary="[Deprecated] Use POST /v1/admin/customers/{customer_id}/plan",
)
@audit_log(action="override_plan", entity_type="organization")
async def override_plan(
    request: Request,
    body: OverridePlanRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.override_plan(
        db,
        org_id=body.org_id,
        new_plan=body.new_plan,
        reason=body.reason,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@users_router.get(
    "/{user_id}/activity",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/customers/{customer_id}/activity",
)
async def get_user_activity(
    request: Request,
    user_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.get_user_activity(
        db, user_id, page=page, page_size=page_size,
    )


@users_router.post(
    "/send-email",
    deprecated=True,
    summary="[Deprecated] Use POST /v1/admin/customers/{customer_id}/email",
)
@audit_log(action="send_email_to_user", entity_type="user")
async def send_email_to_user(
    request: Request,
    body: AdminSendEmailRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    return await admin_user_service.send_email_to_user(
        db,
        body,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


# =============================================================================
# Public Announcements Router (authenticated, NOT admin-only)
# =============================================================================

public_announcements_router = APIRouter(
    prefix="/v1/announcements",
    tags=["Announcements"],
)


@public_announcements_router.get("", response_model=PublicAnnouncementsResponse)
async def get_active_announcements(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get active announcements for the current user."""
    from app.modules.admin.repository import AdminCommunicationRepository
    from app.modules.admin.schemas import PublicAnnouncement
    from app.modules.organizations.repository import OrganizationRepository

    orgs = await OrganizationRepository.list_for_user(db, current_user.id)
    user_plan = orgs[0].plan if orgs else "free"

    announcements = await AdminCommunicationRepository.get_active_announcements_for_user(
        db, current_user.id, user_plan,
    )

    return PublicAnnouncementsResponse(
        announcements=[PublicAnnouncement.model_validate(a) for a in announcements],
    )


# =============================================================================
# Main Admin Router — aggregates all sub-routers
# =============================================================================

admin_router = APIRouter(
    include_in_schema=True,
)

# Canonical control plane (preferred)
admin_router.include_router(overview_router)
admin_router.include_router(customers_router)
admin_router.include_router(revenue_router)
admin_router.include_router(growth_cp_router)
admin_router.include_router(product_router)
admin_router.include_router(support_router)
admin_router.include_router(communications_router)
admin_router.include_router(operations_router)
admin_router.include_router(audit_router)

# Deprecated compatibility aliases
admin_router.include_router(business_router)
admin_router.include_router(analytics_router)
admin_router.include_router(users_router)
