from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.security import create_access_token
from app.infrastructure.email import email_client
from app.modules.admin.repository import (
    AdminAnalyticsRepository,
    AdminAuditRepository,
    AdminBusinessRepository,
    AdminCommunicationRepository,
    AdminFeedbackRepository,
    AdminOperationsRepository,
    AdminUserRepository,
)
from app.modules.admin.schemas import (
    AdminSendEmailRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserOrgInfo,
    AnnouncementListResponse,
    AnnouncementResponse,
    BusinessSummaryResponse,
    ChurnSignalsResponse,
    EmailCampaignListResponse,
    EmailCampaignResponse,
    EmailCampaignSendResponse,
    EngagementResponse,
    ErrorLogListResponse,
    FoundingCustomersResponse,
    FeedbackBulkUpdateRequest,
    FeedbackMessageCreateRequest,
    FeedbackMessageResponse,
    FeedbackStatsResponse,
    FeedbackTicketDetailResponse,
    FeedbackTicketListResponse,
    FeedbackTicketResponse,
    GrowthFunnelData,
    HealthCheckResponse,
    InAppNotificationListResponse,
    InAppNotificationPublishResponse,
    InAppNotificationResponse,
    MRRTimeSeriesResponse,
    RecentSignupsResponse,
    RetentionData,
    FeatureAdoptionResponse,
    VendorCoverageResponse,
    TimeToValueResponse,
    UserActivityResponse,
    AuditLogListResponse,
    BulkActionResponse,
)
from app.modules.admin.models import (
    PlanChangeHistory,
)

logger = logging.getLogger(__name__)

IMPERSONATION_TOKEN_TTL_MINUTES = 15


# =============================================================================
# AdminAuditService
# =============================================================================

class AdminAuditService:
    """Helper service for writing admin audit log entries."""

    def __init__(
        self, repository: AdminAuditRepository = AdminAuditRepository(),
    ) -> None:
        self.repository = repository

    async def log_action(
        self,
        session: AsyncSession,
        *,
        admin_user_id: uuid.UUID | None = None,
        admin_email: str | None = None,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        try:
            await self.repository.log(
                session,
                admin_user_id=admin_user_id,
                admin_email=admin_email,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as exc:
            logger.warning("Failed to write admin audit log: %s", exc)


admin_audit_service = AdminAuditService()


# =============================================================================
# AdminUserService
# =============================================================================

class AdminUserService:
    def __init__(
        self,
        user_repo: AdminUserRepository = AdminUserRepository(),
        audit_svc: AdminAuditService = admin_audit_service,
    ) -> None:
        self.user_repo = user_repo
        self.audit_svc = audit_svc

    async def search_users(
        self,
        session: AsyncSession,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        is_system_admin: bool | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AdminUserListResponse:
        users, total = await self.user_repo.search_users(
            session,
            search=search,
            is_active=is_active,
            is_system_admin=is_system_admin,
            source=source,
            page=page,
            page_size=page_size,
        )
        items = [AdminUserListResponse.model_validate(u) for u in users]
        return AdminUserListResponse(
            items=items, total=total, page=page, page_size=page_size,
        )

    async def get_user_detail(
        self, session: AsyncSession, user_id: uuid.UUID,
    ) -> AdminUserDetailResponse:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")

        orgs = await self.user_repo.get_user_orgs(session, user_id)
        org_infos = [AdminUserOrgInfo(**o) for o in orgs]

        detail = AdminUserDetailResponse.model_validate(user)
        detail.organizations = org_infos
        return detail

    async def update_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        **kwargs: Any,
    ) -> AdminUserDetailResponse:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")

        update_fields = {}
        for key in ("full_name", "is_active", "is_system_admin", "admin_note", "source"):
            if key in kwargs and kwargs[key] is not None:
                update_fields[key] = kwargs[key]

        updated = await UserRepository.update(session, user, **update_fields)

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="update_user",
            entity_type="user",
            entity_id=str(user_id),
            details=update_fields,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        orgs = await self.user_repo.get_user_orgs(session, user_id)
        detail = AdminUserDetailResponse.model_validate(updated)
        detail.organizations = [AdminUserOrgInfo(**o) for o in orgs]
        return detail

    async def impersonate(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")
        if not user.is_active:
            raise ValidationException("Cannot impersonate an inactive user")

        token = create_access_token(
            subject=str(user_id),
            additional_claims={
                "impersonator_id": str(admin_user_id),
                "impersonated_user_id": str(user_id),
                "type": "impersonation",
            },
        )
        # Manually set 15-minute TTL
        from datetime import timedelta
        import jwt as _jwt
        from app.config import settings
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        payload["exp"] = int(
            (datetime.now(timezone.utc) + timedelta(minutes=IMPERSONATION_TOKEN_TTL_MINUTES)).timestamp()
        )
        token = _jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="impersonate_user",
            entity_type="user",
            entity_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "token": token,
            "impersonated_user_id": user_id,
            "impersonated_email": user.email,
            "expires_in_seconds": IMPERSONATION_TOKEN_TTL_MINUTES * 60,
        }

    async def override_plan(
        self,
        session: AsyncSession,
        *,
        org_id: uuid.UUID,
        new_plan: str,
        reason: str | None = None,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, str]:
        from app.modules.organizations.repository import OrganizationRepository

        org = await OrganizationRepository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        from_plan = org.plan
        await OrganizationRepository.update(session, org, plan=new_plan)

        # Record plan change history
        change = PlanChangeHistory(
            org_id=org_id,
            changed_by=admin_user_id,
            from_plan=from_plan,
            to_plan=new_plan,
            reason=reason,
            admin_note=f"Admin override by {admin_email}",
        )
        session.add(change)
        await session.flush()

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="override_plan",
            entity_type="organization",
            entity_id=str(org_id),
            details={"from_plan": from_plan, "to_plan": new_plan, "reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"message": f"Plan changed from {from_plan} to {new_plan}"}

    async def send_email_to_user(
        self,
        session: AsyncSession,
        request: AdminSendEmailRequest,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, bool]:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, request.user_id)
        if not user:
            raise ResourceNotFoundException("User not found")

        success = email_client.send_email(
            to_email=user.email,
            subject=request.subject,
            body=request.body,
            html_body=request.html_body,
        )

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="send_email_to_user",
            entity_type="user",
            entity_id=str(request.user_id),
            details={"subject": request.subject, "success": success},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"success": success}

    async def get_user_activity(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> UserActivityResponse:
        logs, total = await self.user_repo.list_activity(
            session, user_id, page=page, page_size=page_size,
        )
        return UserActivityResponse(
            items=logs,
            total=total,
            page=page,
            page_size=page_size,
        )


admin_user_service = AdminUserService()


# =============================================================================
# AdminBusinessService
# =============================================================================

class AdminBusinessService:
    def __init__(
        self, repository: AdminBusinessRepository = AdminBusinessRepository(),
    ) -> None:
        self.repository = repository

    async def get_summary(self, session: AsyncSession) -> BusinessSummaryResponse:
        data = await self.repository.get_summary(session)
        return BusinessSummaryResponse(**data)

    async def get_mrr_timeseries(
        self, session: AsyncSession, days: int = 30,
    ) -> MRRTimeSeriesResponse:
        data_points = await self.repository.get_mrr_timeseries(session, days)
        return MRRTimeSeriesResponse(data_points=data_points)

    async def get_recent_signups(
        self, session: AsyncSession, limit: int = 20,
    ) -> RecentSignupsResponse:
        items = await self.repository.get_recent_signups(session, limit)
        return RecentSignupsResponse(items=items)

    async def get_churn_signals(
        self, session: AsyncSession, limit: int = 20,
    ) -> ChurnSignalsResponse:
        items = await self.repository.get_churn_signals(session, limit)
        return ChurnSignalsResponse(items=items)

    async def get_founding_customers(
        self, session: AsyncSession,
    ) -> FoundingCustomersResponse:
        items = await self.repository.get_founding_customers(session)
        return FoundingCustomersResponse(items=items)


admin_business_service = AdminBusinessService()


# =============================================================================
# AdminAnalyticsService
# =============================================================================

class AdminAnalyticsService:
    def __init__(
        self, repository: AdminAnalyticsRepository = AdminAnalyticsRepository(),
    ) -> None:
        self.repository = repository

    async def get_growth_funnel(
        self, session: AsyncSession,
    ) -> GrowthFunnelData:
        stages = await self.repository.get_growth_funnel(session)
        return GrowthFunnelData(stages=stages)

    async def get_retention(
        self, session: AsyncSession, weeks: int = 4,
    ) -> RetentionData:
        cohorts = await self.repository.get_retention_cohorts(session, weeks)
        return RetentionData(cohorts=cohorts)

    async def get_feature_adoption(
        self, session: AsyncSession,
    ) -> FeatureAdoptionResponse:
        features = await self.repository.get_feature_adoption(session)
        return FeatureAdoptionResponse(features=features)

    async def get_vendor_coverage(
        self, session: AsyncSession,
    ) -> VendorCoverageResponse:
        vendors = await self.repository.get_vendor_coverage(session)
        return VendorCoverageResponse(vendors=vendors)

    async def get_time_to_value(
        self, session: AsyncSession,
    ) -> TimeToValueResponse:
        buckets = await self.repository.get_time_to_value(session)
        return TimeToValueResponse(buckets=buckets)

    async def get_engagement(
        self, session: AsyncSession,
    ) -> EngagementResponse:
        metrics = await self.repository.get_engagement(session)
        return EngagementResponse(metrics=metrics)


admin_analytics_service = AdminAnalyticsService()


# =============================================================================
# AdminFeedbackService
# =============================================================================

class AdminFeedbackService:
    def __init__(
        self,
        repository: AdminFeedbackRepository = AdminFeedbackRepository(),
        audit_svc: AdminAuditService = admin_audit_service,
    ) -> None:
        self.repository = repository
        self.audit_svc = audit_svc

    async def create_ticket(
        self,
        session: AsyncSession,
        *,
        email: str,
        full_name: str | None = None,
        category: str = "general",
        subject: str,
        body: str,
        priority: str = "normal",
        source: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> FeedbackTicketResponse:
        ticket_number = f"FB-{secrets.token_hex(4).upper()}"
        ticket = await self.repository.create_ticket(
            session,
            ticket_number=ticket_number,
            email=email,
            full_name=full_name,
            category=category,
            subject=subject,
            body=body,
            priority=priority,
            source=source,
            user_id=user_id,
        )
        return FeedbackTicketResponse.model_validate(ticket)

    async def get_ticket(
        self, session: AsyncSession, ticket_id: uuid.UUID,
    ) -> FeedbackTicketDetailResponse:
        ticket = await self.repository.get_ticket_by_id(session, ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket not found")
        messages = await self.repository.list_messages(session, ticket_id)
        return FeedbackTicketDetailResponse(
            ticket=FeedbackTicketResponse.model_validate(ticket),
            messages=[FeedbackMessageResponse.model_validate(m) for m in messages],
        )

    async def list_tickets(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> FeedbackTicketListResponse:
        tickets, total = await self.repository.list_tickets(
            session,
            status=status,
            category=category,
            priority=priority,
            assigned_to=assigned_to,
            search=search,
            page=page,
            page_size=page_size,
        )
        return FeedbackTicketListResponse(
            items=[FeedbackTicketResponse.model_validate(t) for t in tickets],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_ticket(
        self,
        session: AsyncSession,
        ticket_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        **kwargs: Any,
    ) -> FeedbackTicketResponse:
        ticket = await self.repository.get_ticket_by_id(session, ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket not found")
        updated = await self.repository.update_ticket(session, ticket, **kwargs)

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="update_ticket",
            entity_type="feedback_ticket",
            entity_id=str(ticket_id),
            details=kwargs,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return FeedbackTicketResponse.model_validate(updated)

    async def reply_to_ticket(
        self,
        session: AsyncSession,
        ticket_id: uuid.UUID,
        request: FeedbackMessageCreateRequest,
        *,
        admin_user_id: uuid.UUID,
        admin_name: str,
    ) -> FeedbackMessageResponse:
        ticket = await self.repository.get_ticket_by_id(session, ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket not found")

        msg = await self.repository.add_message(
            session,
            ticket_id=ticket_id,
            sender_type="admin",
            sender_id=admin_user_id,
            sender_name=admin_name,
            body=request.body,
            is_internal_note=request.is_internal_note,
        )
        return FeedbackMessageResponse.model_validate(msg)

    async def bulk_update_tickets(
        self,
        session: AsyncSession,
        request: FeedbackBulkUpdateRequest,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BulkActionResponse:
        update_fields = {}
        if request.status:
            update_fields["status"] = request.status
        if request.priority:
            update_fields["priority"] = request.priority
        if request.assigned_to:
            update_fields["assigned_to"] = request.assigned_to

        updated_count = 0
        for tid in request.ticket_ids:
            ticket = await self.repository.get_ticket_by_id(session, tid)
            if ticket:
                await self.repository.update_ticket(session, ticket, **update_fields)
                updated_count += 1

        if updated_count > 0:
            await self.audit_svc.log_action(
                session,
                admin_user_id=admin_user_id,
                admin_email=admin_email,
                action="bulk_update_tickets",
                entity_type="feedback_ticket",
                entity_id=",".join(str(t) for t in request.ticket_ids),
                details=update_fields,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return BulkActionResponse(
            updated_count=updated_count,
            message=f"Updated {updated_count} tickets",
        )

    async def get_stats(self, session: AsyncSession) -> FeedbackStatsResponse:
        data = await self.repository.get_ticket_stats(session)
        return FeedbackStatsResponse(**data)


admin_feedback_service = AdminFeedbackService()


# =============================================================================
# AdminCommunicationService
# =============================================================================

class AdminCommunicationService:
    def __init__(
        self,
        repository: AdminCommunicationRepository = AdminCommunicationRepository(),
        audit_svc: AdminAuditService = admin_audit_service,
    ) -> None:
        self.repository = repository
        self.audit_svc = audit_svc

    # -- Email Campaigns --

    async def create_campaign(
        self,
        session: AsyncSession,
        *,
        campaign_name: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        segment: str | None = None,
        utm_campaign: str | None = None,
        scheduled_at: datetime | None = None,
        created_by: uuid.UUID,
    ) -> EmailCampaignResponse:
        campaign = await self.repository.create_campaign(
            session,
            campaign_name=campaign_name,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            segment=segment,
            utm_campaign=utm_campaign,
            scheduled_at=scheduled_at,
            created_by=created_by,
        )
        return EmailCampaignResponse.model_validate(campaign)

    async def list_campaigns(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> EmailCampaignListResponse:
        campaigns, total = await self.repository.list_campaigns(
            session, status=status, page=page, page_size=page_size,
        )
        return EmailCampaignListResponse(
            items=[EmailCampaignResponse.model_validate(c) for c in campaigns],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_campaign(
        self, session: AsyncSession, campaign_id: uuid.UUID,
    ) -> EmailCampaignResponse:
        campaign = await self.repository.get_campaign_by_id(session, campaign_id)
        if not campaign:
            raise ResourceNotFoundException("Campaign not found")
        return EmailCampaignResponse.model_validate(campaign)

    async def update_campaign(
        self,
        session: AsyncSession,
        campaign_id: uuid.UUID,
        **kwargs: Any,
    ) -> EmailCampaignResponse:
        campaign = await self.repository.get_campaign_by_id(session, campaign_id)
        if not campaign:
            raise ResourceNotFoundException("Campaign not found")
        updated = await self.repository.update_campaign(session, campaign, **kwargs)
        return EmailCampaignResponse.model_validate(updated)

    async def send_campaign(
        self,
        session: AsyncSession,
        campaign_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EmailCampaignSendResponse:
        campaign = await self.repository.get_campaign_by_id(session, campaign_id)
        if not campaign:
            raise ResourceNotFoundException("Campaign not found")
        if campaign.status == "sent":
            raise ValidationException("Campaign has already been sent")

        # Get target users
        from app.modules.users.models import User
        from sqlalchemy import select

        query = select(User).where(User.is_active.is_(True))
        users = (await session.execute(query)).scalars().all()

        sent = 0
        for user in users:
            await self.repository.create_recipient(
                session,
                campaign_id=campaign_id,
                user_id=user.id,
                email=user.email,
            )
            sent += 1

        await self.repository.update_campaign(
            session, campaign,
            status="sent",
            recipient_count=sent,
            sent_at=datetime.now(timezone.utc),
        )

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="send_campaign",
            entity_type="email_campaign",
            entity_id=str(campaign_id),
            details={"recipient_count": sent},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return EmailCampaignSendResponse(
            message=f"Campaign sent to {sent} recipients",
            campaign_id=campaign_id,
            recipient_count=sent,
        )

    # -- In-App Notifications --

    async def create_notification(
        self,
        session: AsyncSession,
        *,
        title: str,
        body: str,
        notification_type: str = "info",
        action_url: str | None = None,
        action_label: str | None = None,
        priority: str = "normal",
        expires_at: datetime | None = None,
        is_dismissible: bool = True,
        created_by: uuid.UUID,
    ) -> InAppNotificationResponse:
        notification = await self.repository.create_notification(
            session,
            title=title,
            body=body,
            notification_type=notification_type,
            action_url=action_url,
            action_label=action_label,
            priority=priority,
            expires_at=expires_at,
            is_dismissible=is_dismissible,
            created_by=created_by,
        )
        return InAppNotificationResponse.model_validate(notification)

    async def list_notifications(
        self,
        session: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> InAppNotificationListResponse:
        notifications, total = await self.repository.list_notifications(
            session, page=page, page_size=page_size,
        )
        return InAppNotificationListResponse(
            items=[InAppNotificationResponse.model_validate(n) for n in notifications],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def publish_notification(
        self,
        session: AsyncSession,
        notification_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        target_segment: str | None = None,
        target_plan: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InAppNotificationPublishResponse:
        notification = await self.repository.get_notification_by_id(
            session, notification_id,
        )
        if not notification:
            raise ResourceNotFoundException("Notification not found")

        # Deliver to all active users
        from app.modules.users.models import User
        from sqlalchemy import select as sa_select

        query = sa_select(User).where(User.is_active.is_(True))
        users = (await session.execute(query)).scalars().all()

        delivered = 0
        for user in users:
            await self.repository.create_delivery(
                session,
                notification_id=notification_id,
                user_id=user.id,
            )
            delivered += 1

        await self.audit_svc.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="publish_notification",
            entity_type="in_app_notification",
            entity_id=str(notification_id),
            details={"delivery_count": delivered},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return InAppNotificationPublishResponse(
            message=f"Notification delivered to {delivered} users",
            notification_id=notification_id,
            delivery_count=delivered,
        )

    # -- Announcements --

    async def create_announcement(
        self,
        session: AsyncSession,
        *,
        title: str,
        body_html: str,
        placement: str = "top_banner",
        target_plans: list[str] | None = None,
        target_segment: str | None = None,
        action_url: str | None = None,
        action_label: str | None = None,
        is_dismissible: bool = True,
        bg_color: str | None = None,
        text_color: str | None = None,
        starts_at: datetime | None = None,
        expires_at: datetime | None = None,
        created_by: uuid.UUID,
    ) -> AnnouncementResponse:
        announcement = await self.repository.create_announcement(
            session,
            title=title,
            body_html=body_html,
            placement=placement,
            target_plans=target_plans,
            target_segment=target_segment,
            action_url=action_url,
            action_label=action_label,
            is_dismissible=is_dismissible,
            bg_color=bg_color,
            text_color=text_color,
            starts_at=starts_at,
            expires_at=expires_at,
            created_by=created_by,
        )
        return AnnouncementResponse.model_validate(announcement)

    async def list_announcements(
        self,
        session: AsyncSession,
        *,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AnnouncementListResponse:
        announcements, total = await self.repository.list_announcements(
            session, is_active=is_active, page=page, page_size=page_size,
        )
        return AnnouncementListResponse(
            items=[AnnouncementResponse.model_validate(a) for a in announcements],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_announcement(
        self, session: AsyncSession, announcement_id: uuid.UUID,
    ) -> AnnouncementResponse:
        announcement = await self.repository.get_announcement_by_id(
            session, announcement_id,
        )
        if not announcement:
            raise ResourceNotFoundException("Announcement not found")
        return AnnouncementResponse.model_validate(announcement)

    async def update_announcement(
        self,
        session: AsyncSession,
        announcement_id: uuid.UUID,
        **kwargs: Any,
    ) -> AnnouncementResponse:
        announcement = await self.repository.get_announcement_by_id(
            session, announcement_id,
        )
        if not announcement:
            raise ResourceNotFoundException("Announcement not found")
        updated = await self.repository.update_announcement(
            session, announcement, **kwargs,
        )
        return AnnouncementResponse.model_validate(updated)


admin_communication_service = AdminCommunicationService()


# =============================================================================
# AdminOperationsService
# =============================================================================

class AdminOperationsService:
    def __init__(
        self,
        repository: AdminOperationsRepository = AdminOperationsRepository(),
    ) -> None:
        self.repository = repository

    async def health_check(self, session: AsyncSession) -> HealthCheckResponse:
        import time
        from app.db.session import get_engine
        from sqlalchemy import text

        checks = []
        overall = "ok"

        # Database check
        try:
            engine = get_engine()
            start = time.monotonic()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            latency = (time.monotonic() - start) * 1000
            checks.append({
                "component": "database",
                "status": "ok",
                "latency_ms": round(latency, 2),
                "message": None,
            })
        except Exception as exc:
            overall = "degraded"
            checks.append({
                "component": "database",
                "status": "error",
                "latency_ms": None,
                "message": str(exc),
            })

        # Redis check
        try:
            from app.infrastructure.redis_client import safe_redis_ping
            start = time.monotonic()
            ok = await safe_redis_ping()
            latency = (time.monotonic() - start) * 1000
            if ok:
                checks.append({
                    "component": "redis",
                    "status": "ok",
                    "latency_ms": round(latency, 2),
                    "message": None,
                })
            else:
                overall = "degraded"
                checks.append({
                    "component": "redis",
                    "status": "error",
                    "latency_ms": None,
                    "message": "Redis ping failed",
                })
        except Exception as exc:
            overall = "degraded"
            checks.append({
                "component": "redis",
                "status": "error",
                "latency_ms": None,
                "message": str(exc),
            })

        return HealthCheckResponse(overall=overall, checks=checks)

    async def check_engines(self, session: AsyncSession) -> dict[str, Any]:
        return {
            "engines": [
                {"name": "dependency_checker", "status": "running", "last_run_at": None, "next_run_at": None, "last_error": None},
                {"name": "incident_detector", "status": "running", "last_run_at": None, "next_run_at": None, "last_error": None},
                {"name": "evidence_collector", "status": "idle", "last_run_at": None, "next_run_at": None, "last_error": None},
            ]
        }

    async def list_error_logs(
        self,
        session: AsyncSession,
        *,
        level: str | None = None,
        is_resolved: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ErrorLogListResponse:
        logs, total = await self.repository.list_error_logs(
            session, level=level, is_resolved=is_resolved,
            page=page, page_size=page_size,
        )
        from app.modules.admin.schemas import ErrorLogItem
        return ErrorLogListResponse(
            items=[ErrorLogItem.model_validate(l) for l in logs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def resolve_error(
        self, session: AsyncSession, error_id: uuid.UUID,
    ) -> dict[str, str]:
        log = await self.repository.resolve_error_log(session, error_id)
        if not log:
            raise ResourceNotFoundException("Error log not found")
        return {"message": "Error marked as resolved"}

    async def get_metrics(self, session: AsyncSession) -> dict[str, Any]:
        return await self.repository.get_system_metrics(session)


admin_operations_service = AdminOperationsService()
