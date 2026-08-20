from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user
from app.db.session import get_db
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
    admin_audit_service,
    admin_business_service,
    admin_communication_service,
    admin_feedback_service,
    admin_operations_service,
    admin_user_service,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)


# =============================================================================
# Business Dashboard Router
# =============================================================================

business_router = APIRouter(
    prefix="/v1/admin/business",
    tags=["Admin — Business"],
)


@business_router.get("/summary")
async def get_business_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Business overview: total users, orgs, MRR, signups, churn."""
    return await admin_business_service.get_summary(db)


@business_router.get("/mrr-timeseries")
async def get_mrr_timeseries(
    request: Request,
    days: int = Query(default=30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Monthly Recurring Revenue time series."""
    return await admin_business_service.get_mrr_timeseries(db, days=days)


@business_router.get("/recent-signups")
async def get_recent_signups(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Recently signed up users with org info."""
    return await admin_business_service.get_recent_signups(db, limit=limit)


@business_router.get("/churn-signals")
async def get_churn_signals(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Organizations showing churn risk signals."""
    return await admin_business_service.get_churn_signals(db, limit=limit)


# =============================================================================
# Analytics Dashboard Router
# =============================================================================

analytics_router = APIRouter(
    prefix="/v1/admin/analytics",
    tags=["Admin — Analytics"],
)


@analytics_router.get("/growth-funnel")
async def get_growth_funnel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Signup → Org → Dependency → Monitoring funnel."""
    return await admin_analytics_service.get_growth_funnel(db)


@analytics_router.get("/retention")
async def get_retention(
    request: Request,
    weeks: int = Query(default=4, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Cohort retention data by weekly periods."""
    return await admin_analytics_service.get_retention(db, weeks=weeks)


@analytics_router.get("/feature-adoption")
async def get_feature_adoption(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Feature adoption metrics across the user base."""
    return await admin_analytics_service.get_feature_adoption(db)


@analytics_router.get("/vendor-coverage")
async def get_vendor_coverage(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Top vendors and how many orgs are monitoring each."""
    return await admin_analytics_service.get_vendor_coverage(db)


@analytics_router.get("/time-to-value")
async def get_time_to_value(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Distribution of time-to-first-check across users."""
    return await admin_analytics_service.get_time_to_value(db)


@analytics_router.get("/engagement")
async def get_engagement(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """DAU/WAU/MAU and stickiness ratio."""
    return await admin_analytics_service.get_engagement(db)


# =============================================================================
# Users Dashboard Router
# =============================================================================

users_router = APIRouter(
    prefix="/v1/admin/users",
    tags=["Admin — Users"],
)


@users_router.get("")
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
    """Search and list users with filters and pagination."""
    return await admin_user_service.search_users(
        db,
        search=search,
        is_active=is_active,
        is_system_admin=is_system_admin,
        source=source,
        page=page,
        page_size=page_size,
    )


@users_router.get("/{user_id}")
async def get_user_detail(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Get detailed user profile including org memberships."""
    return await admin_user_service.get_user_detail(db, user_id)


@users_router.patch("/{user_id}")
async def update_user(
    request: Request,
    user_id: uuid.UUID,
    body: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Update user fields (name, active status, admin flag, note, source)."""
    return await admin_user_service.update_user(
        db,
        user_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        **body.model_dump(exclude_none=True),
    )


@users_router.post("/{user_id}/impersonate", response_model=ImpersonationTokenResponse)
@audit_log(action="impersonate_user", entity_type="user")
async def impersonate_user(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Generate a short-lived impersonation JWT for the target user."""
    return await admin_user_service.impersonate(
        db,
        user_id,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@users_router.post("/override-plan")
@audit_log(action="override_plan", entity_type="organization")
async def override_plan(
    request: Request,
    body: OverridePlanRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Override the plan for an organization."""
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


@users_router.get("/{user_id}/activity")
async def get_user_activity(
    request: Request,
    user_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Get paginated activity log for a specific user."""
    return await admin_user_service.get_user_activity(
        db, user_id, page=page, page_size=page_size,
    )


@users_router.post("/send-email")
@audit_log(action="send_email_to_user", entity_type="user")
async def send_email_to_user(
    request: Request,
    body: AdminSendEmailRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Send an arbitrary email to a specific user."""
    return await admin_user_service.send_email_to_user(
        db,
        body,
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


# =============================================================================
# Communications Dashboard Router
# =============================================================================

communications_router = APIRouter(
    prefix="/v1/admin/communications",
    tags=["Admin — Communications"],
)

# -- Email Campaigns --

communications_router.include_router(
    APIRouter(prefix="/campaigns"),
)


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
    """Get a single email campaign by ID."""
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
    """Send/distribute an email campaign to recipients."""
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
    """Update an existing announcement."""
    return await admin_communication_service.update_announcement(
        db, announcement_id, **body.model_dump(exclude_none=True),
    )


# =============================================================================
# Operations Dashboard Router
# =============================================================================

operations_router = APIRouter(
    prefix="/v1/admin/operations",
    tags=["Admin — Operations"],
)


@operations_router.get("/health")
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """System health check (database, redis, scheduler)."""
    return await admin_operations_service.health_check(db)


@operations_router.get("/check-engines")
async def check_engines(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Status of background check/engine workers."""
    return await admin_operations_service.check_engines(db)


@operations_router.get("/error-logs")
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


@operations_router.get("/metrics")
async def get_system_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """System-wide metrics (users, orgs, deps, incidents, pool)."""
    return await admin_operations_service.get_metrics(db)


# =============================================================================
# Support / Feedback Router
# =============================================================================

support_router = APIRouter(
    prefix="/v1/admin/support",
    tags=["Admin — Support"],
)


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


@support_router.get("/tickets/stats")
async def get_ticket_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Support ticket aggregate statistics."""
    return await admin_feedback_service.get_stats(db)


@support_router.get("/tickets/{ticket_id}")
async def get_ticket(
    request: Request,
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """Get a ticket with all messages."""
    return await admin_feedback_service.get_ticket(db, ticket_id)


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
    """Reply to a ticket (or add an internal note)."""
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
# Audit Log Router
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_system_admin),
):
    """List admin audit log entries with filters."""
    from app.modules.admin.repository import AdminAuditRepository
    from app.modules.admin.schemas import AuditLogItem, AuditLogListResponse

    logs, total = await AdminAuditRepository.list_logs(
        db,
        action=action,
        entity_type=entity_type,
        page=page,
        page_size=page_size,
    )
    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(l) for l in logs],
        total=total,
        page=page,
        page_size=page_size,
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
    include_in_schema=False,
)

admin_router.include_router(business_router)
admin_router.include_router(analytics_router)
admin_router.include_router(users_router)
admin_router.include_router(communications_router)
admin_router.include_router(operations_router)
admin_router.include_router(support_router)
admin_router.include_router(audit_router)
