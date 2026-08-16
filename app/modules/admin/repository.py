from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, select, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import (
    AdminAuditLog,
    AppErrorLog,
    Announcement,
    AnnouncementDismissal,
    EmailCampaign,
    EmailCampaignRecipient,
    FeedbackMessage,
    FeedbackTicket,
    InAppNotification,
    InAppNotificationDelivery,
    PlanChangeHistory,
    SystemHealthAlert,
    UserActivityLog,
    UserSession,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AdminAuditRepository
# =============================================================================

class AdminAuditRepository:
    @staticmethod
    async def log(
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
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def list_logs(
        session: AsyncSession,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AdminAuditLog], int]:
        query = select(AdminAuditLog)
        count_q = select(func.count()).select_from(AdminAuditLog)
        if action:
            query = query.where(AdminAuditLog.action == action)
            count_q = count_q.where(AdminAuditLog.action == action)
        if entity_type:
            query = query.where(AdminAuditLog.entity_type == entity_type)
            count_q = count_q.where(AdminAuditLog.entity_type == entity_type)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total


# =============================================================================
# AdminUserRepository
# =============================================================================

class AdminUserRepository:
    @staticmethod
    async def search_users(
        session: AsyncSession,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        is_system_admin: bool | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int]:
        from app.modules.users.models import User

        query = select(User)
        count_q = select(func.count()).select_from(User)
        if search:
            pattern = f"%{search}%"
            search_filter = or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
            query = query.where(search_filter)
            count_q = count_q.where(search_filter)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_q = count_q.where(User.is_active == is_active)
        if is_system_admin is not None:
            query = query.where(User.is_system_admin == is_system_admin)
            count_q = count_q.where(User.is_system_admin == is_system_admin)
        if source:
            query = query.where(User.source == source)
            count_q = count_q.where(User.source == source)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def get_user_orgs(
        session: AsyncSession, user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        from app.modules.organizations.models import Organization, OrganizationMember

        query = (
            select(Organization, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
        )
        rows = (await session.execute(query)).all()
        return [
            {"org_id": org.id, "org_name": org.name, "role": role, "plan": org.plan}
            for org, role in rows
        ]

    @staticmethod
    async def list_activity(
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserActivityLog], int]:
        query = select(UserActivityLog).where(UserActivityLog.user_id == user_id)
        count_q = (
            select(func.count())
            .select_from(UserActivityLog)
            .where(UserActivityLog.user_id == user_id)
        )
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(UserActivityLog.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def log_activity(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        action: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserActivityLog:
        entry = UserActivityLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(entry)
        await session.flush()
        return entry


# =============================================================================
# AdminBusinessRepository
# =============================================================================

class AdminBusinessRepository:
    @staticmethod
    async def get_summary(session: AsyncSession) -> dict[str, Any]:
        from app.modules.users.models import User
        from app.modules.organizations.models import Organization
        from app.modules.billing.models import Subscription

        total_users = (await session.execute(
            select(func.count()).select_from(User)
        )).scalar() or 0

        total_orgs = (await session.execute(
            select(func.count()).select_from(Organization)
        )).scalar() or 0

        active_subs = (await session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == "active"
            )
        )).scalar() or 0

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_signups = (await session.execute(
            select(func.count()).select_from(User).where(
                User.created_at >= seven_days_ago
            )
        )).scalar() or 0

        # MRR approximation from active subscriptions
        from app.core.permissions import get_plan_price_usd
        active_plans_q = (
            select(Subscription.plan, func.count().label("cnt"))
            .where(Subscription.status == "active")
            .group_by(Subscription.plan)
        )
        plan_rows = (await session.execute(active_plans_q)).all()
        mrr = sum(get_plan_price_usd(row.plan) * row.cnt for row in plan_rows)

        # Simple churn: orgs with inactive subscription that were active 7 days ago
        churned_7d = 0  # Approximation — would need historical snapshot data

        return {
            "total_users": total_users,
            "total_organizations": total_orgs,
            "mrr": float(mrr),
            "active_subscriptions": active_subs,
            "new_signups_7d": new_signups,
            "churned_7d": churned_7d,
        }

    @staticmethod
    async def get_mrr_timeseries(
        session: AsyncSession, days: int = 30,
    ) -> list[dict[str, Any]]:
        # Approximation: return current MRR for each day
        from app.modules.billing.models import Subscription
        from app.core.permissions import get_plan_price_usd

        now = datetime.now(timezone.utc)
        active_plans_q = (
            select(Subscription.plan, func.count().label("cnt"))
            .where(Subscription.status == "active")
            .group_by(Subscription.plan)
        )
        plan_rows = (await session.execute(active_plans_q)).all()
        mrr = sum(get_plan_price_usd(row.plan) * row.cnt for row in plan_rows)

        data_points = []
        for i in range(days):
            date = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            data_points.append({"date": date, "mrr": float(mrr)})
        return data_points

    @staticmethod
    async def get_recent_signups(
        session: AsyncSession, limit: int = 20,
    ) -> list[dict[str, Any]]:
        from app.modules.users.models import User
        from app.modules.organizations.models import Organization, OrganizationMember

        query = (
            select(User, Organization.name, Organization.plan)
            .outerjoin(
                OrganizationMember,
                and_(
                    OrganizationMember.user_id == User.id,
                    OrganizationMember.role == "owner",
                ),
            )
            .outerjoin(Organization, OrganizationMember.org_id == Organization.id)
            .order_by(User.created_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(query)).all()
        return [
            {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "org_name": org_name,
                "plan": plan,
                "source": user.source,
                "created_at": user.created_at,
            }
            for user, org_name, plan in rows
        ]

    @staticmethod
    async def get_churn_signals(
        session: AsyncSession, limit: int = 20,
    ) -> list[dict[str, Any]]:
        from app.modules.organizations.models import Organization
        from app.modules.billing.models import Subscription
        from app.modules.checks.models import CheckResult

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        query = (
            select(
                Organization.id,
                Organization.name,
                Organization.plan,
                Organization.last_activity_at,
            )
            .outerjoin(Subscription, Subscription.organization_id == Organization.id)
            .where(Organization.plan != "free")
            .order_by(Organization.created_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(query)).all()
        results = []
        for org_id, name, plan, last_act in rows:
            risk = "low"
            if last_act and last_act < thirty_days_ago:
                risk = "high"
            results.append({
                "org_id": org_id,
                "org_name": name,
                "plan": plan,
                "last_activity_at": getattr(last_act, "last_activity_at", None),
                "subscription_status": "active",
                "risk_level": risk,
            })
        return results

    @staticmethod
    async def get_founding_customers(session: AsyncSession) -> list[dict[str, Any]]:
        from app.modules.organizations.models import Organization, OrganizationMember

        query = (
            select(
                Organization.id,
                Organization.name,
                Organization.plan,
                Organization.founding_discount_pct,
                Organization.created_at,
                func.count(OrganizationMember.id).label("member_count"),
            )
            .outerjoin(OrganizationMember, OrganizationMember.org_id == Organization.id)
            .where(Organization.is_founding_customer.is_(True))
            .group_by(
                Organization.id,
                Organization.name,
                Organization.plan,
                Organization.founding_discount_pct,
                Organization.created_at,
            )
            .order_by(Organization.created_at.asc())
        )
        rows = (await session.execute(query)).all()
        return [
            {
                "org_id": org_id,
                "org_name": name,
                "plan": plan,
                "founding_discount_pct": discount,
                "member_count": member_count,
                "created_at": created_at,
            }
            for org_id, name, plan, discount, created_at, member_count in rows
        ]


# =============================================================================
# AdminAnalyticsRepository
# =============================================================================

class AdminAnalyticsRepository:
    @staticmethod
    async def get_growth_funnel(session: AsyncSession) -> list[dict[str, Any]]:
        from app.modules.users.models import User
        from app.modules.organizations.models import Organization
        from app.modules.dependencies.models import Dependency

        total_users = (await session.execute(
            select(func.count()).select_from(User)
        )).scalar() or 0
        orgs_with_deps = (
            await session.execute(
                select(func.count(func.distinct(Dependency.org_id)))
                .select_from(Dependency)
            )
        ).scalar() or 0
        total_deps = (await session.execute(
            select(func.count()).select_from(Dependency)
        )).scalar() or 0

        return [
            {"stage": "signups", "count": total_users},
            {"stage": "organizations", "count": orgs_with_deps},
            {"stage": "dependencies_monitored", "count": total_deps},
        ]

    @staticmethod
    async def get_retention_cohorts(
        session: AsyncSession, weeks: int = 4,
    ) -> list[dict[str, Any]]:
        # Approximation: return empty cohorts since historical data may not exist
        return []

    @staticmethod
    async def get_feature_adoption(session: AsyncSession) -> list[dict[str, Any]]:
        from app.modules.users.models import User
        from app.modules.dependencies.models import Dependency
        from app.modules.organizations.models import Organization
        from app.modules.checks.models import CheckResult

        total_users = (await session.execute(
            select(func.count()).select_from(User)
        )).scalar() or 0
        if total_users == 0:
            return []

        total_orgs = (await session.execute(
            select(func.count()).select_from(Organization)
        )).scalar() or 0
        orgs_with_deps = (
            await session.execute(
                select(func.count(func.distinct(Dependency.org_id)))
                .select_from(Dependency)
            )
        ).scalar() or 0
        orgs_with_checks = (
            await session.execute(
                select(func.count(func.distinct(CheckResult.org_id)))
                .select_from(CheckResult)
            )
        ).scalar() or 0

        return [
            {
                "feature": "dependencies",
                "total_users": total_users,
                "active_users": orgs_with_deps,
                "adoption_pct": round(orgs_with_deps / max(total_users, 1) * 100, 1),
            },
            {
                "feature": "monitoring",
                "total_users": total_users,
                "active_users": orgs_with_checks,
                "adoption_pct": round(orgs_with_checks / max(total_users, 1) * 100, 1),
            },
        ]

    @staticmethod
    async def get_vendor_coverage(session: AsyncSession) -> list[dict[str, Any]]:
        from app.modules.organizations.models import Organization
        from app.modules.dependencies.models import Dependency

        total_orgs = (await session.execute(
            select(func.count()).select_from(Organization)
        )).scalar() or 0
        if total_orgs == 0:
            return []

        query = (
            select(Dependency.name, func.count(func.distinct(Dependency.org_id)).label("cnt"))
            .group_by(Dependency.name)
            .order_by(func.count(func.distinct(Dependency.org_id)).desc())
            .limit(20)
        )
        rows = (await session.execute(query)).all()
        return [
            {
                "vendor_name": name,
                "total_orgs": total_orgs,
                "monitoring_orgs": cnt,
                "coverage_pct": round(cnt / total_orgs * 100, 1),
            }
            for name, cnt in rows
        ]

    @staticmethod
    async def get_time_to_value(session: AsyncSession) -> list[dict[str, Any]]:
        return [
            {"bucket": "same_day", "count": 0},
            {"bucket": "1_3_days", "count": 0},
            {"bucket": "4_7_days", "count": 0},
            {"bucket": "8_30_days", "count": 0},
            {"bucket": "30_plus_days", "count": 0},
        ]

    @staticmethod
    async def get_engagement(session: AsyncSession) -> dict[str, Any]:
        from app.modules.users.models import User

        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        dau = (await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity_at >= today
            )
        )).scalar() or 0
        wau = (await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity_at >= week_ago
            )
        )).scalar() or 0
        mau = (await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity_at >= month_ago
            )
        )).scalar() or 0

        return {
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "dau_mau_ratio": round(dau / max(mau, 1) * 100, 1),
        }


# =============================================================================
# AdminFeedbackRepository
# =============================================================================

class AdminFeedbackRepository:
    @staticmethod
    async def create_ticket(
        session: AsyncSession,
        *,
        ticket_number: str,
        email: str,
        full_name: str | None = None,
        category: str = "general",
        subject: str,
        body: str,
        priority: str = "normal",
        source: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> FeedbackTicket:
        ticket = FeedbackTicket(
            ticket_number=ticket_number,
            user_id=user_id,
            email=email,
            full_name=full_name,
            category=category,
            subject=subject,
            body=body,
            priority=priority,
            source=source,
        )
        session.add(ticket)
        await session.flush()
        return ticket

    @staticmethod
    async def get_ticket_by_id(
        session: AsyncSession, ticket_id: uuid.UUID,
    ) -> FeedbackTicket | None:
        query = select(FeedbackTicket).where(FeedbackTicket.id == ticket_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_ticket_by_number(
        session: AsyncSession, ticket_number: str,
    ) -> FeedbackTicket | None:
        query = select(FeedbackTicket).where(
            FeedbackTicket.ticket_number == ticket_number
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        *,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FeedbackTicket], int]:
        query = select(FeedbackTicket)
        count_q = select(func.count()).select_from(FeedbackTicket)
        filters = []
        if status:
            filters.append(FeedbackTicket.status == status)
        if category:
            filters.append(FeedbackTicket.category == category)
        if priority:
            filters.append(FeedbackTicket.priority == priority)
        if assigned_to:
            filters.append(FeedbackTicket.assigned_to == assigned_to)
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    FeedbackTicket.subject.ilike(pattern),
                    FeedbackTicket.email.ilike(pattern),
                    FeedbackTicket.ticket_number.ilike(pattern),
                )
            )
        for f in filters:
            query = query.where(f)
            count_q = count_q.where(f)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(FeedbackTicket.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def update_ticket(
        session: AsyncSession,
        ticket: FeedbackTicket,
        **kwargs: Any,
    ) -> FeedbackTicket:
        for key, value in kwargs.items():
            if value is not None and hasattr(ticket, key):
                setattr(ticket, key, value)
        if kwargs.get("status") == "resolved" and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(timezone.utc)
        session.add(ticket)
        await session.flush()
        return ticket

    @staticmethod
    async def add_message(
        session: AsyncSession,
        *,
        ticket_id: uuid.UUID,
        sender_type: str,
        sender_id: uuid.UUID,
        sender_name: str,
        body: str,
        is_internal_note: bool = False,
    ) -> FeedbackMessage:
        msg = FeedbackMessage(
            ticket_id=ticket_id,
            sender_type=sender_type,
            sender_id=sender_id,
            sender_name=sender_name,
            body=body,
            is_internal_note=is_internal_note,
        )
        session.add(msg)
        await session.flush()
        return msg

    @staticmethod
    async def list_messages(
        session: AsyncSession,
        ticket_id: uuid.UUID,
    ) -> list[FeedbackMessage]:
        query = (
            select(FeedbackMessage)
            .where(FeedbackMessage.ticket_id == ticket_id)
            .order_by(FeedbackMessage.created_at.asc())
        )
        rows = (await session.execute(query)).scalars().all()
        return list(rows)

    @staticmethod
    async def get_ticket_stats(session: AsyncSession) -> dict[str, Any]:
        total = (await session.execute(
            select(func.count()).select_from(FeedbackTicket)
        )).scalar() or 0
        open_count = (await session.execute(
            select(func.count()).select_from(FeedbackTicket).where(
                FeedbackTicket.status == "open"
            )
        )).scalar() or 0
        resolved = (await session.execute(
            select(func.count()).select_from(FeedbackTicket).where(
                FeedbackTicket.status == "resolved"
            )
        )).scalar() or 0

        by_category = (
            await session.execute(
                select(FeedbackTicket.category, func.count().label("cnt"))
                .group_by(FeedbackTicket.category)
            )
        ).all()
        by_priority = (
            await session.execute(
                select(FeedbackTicket.priority, func.count().label("cnt"))
                .group_by(FeedbackTicket.priority)
            )
        ).all()

        return {
            "total_tickets": total,
            "open_tickets": open_count,
            "resolved_tickets": resolved,
            "avg_resolution_hours": 0.0,
            "by_category": {cat: cnt for cat, cnt in by_category},
            "by_priority": {pri: cnt for pri, cnt in by_priority},
        }


# =============================================================================
# AdminCommunicationRepository
# =============================================================================

class AdminCommunicationRepository:
    # -- Email Campaigns --

    @staticmethod
    async def create_campaign(
        session: AsyncSession,
        *,
        campaign_name: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        segment: str | None = None,
        utm_campaign: str | None = None,
        scheduled_at: datetime | None = None,
        created_by: uuid.UUID | None = None,
    ) -> EmailCampaign:
        campaign = EmailCampaign(
            campaign_name=campaign_name,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            segment=segment,
            utm_campaign=utm_campaign,
            scheduled_at=scheduled_at,
            created_by=created_by,
        )
        session.add(campaign)
        await session.flush()
        return campaign

    @staticmethod
    async def get_campaign_by_id(
        session: AsyncSession, campaign_id: uuid.UUID,
    ) -> EmailCampaign | None:
        query = select(EmailCampaign).where(EmailCampaign.id == campaign_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_campaigns(
        session: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EmailCampaign], int]:
        query = select(EmailCampaign)
        count_q = select(func.count()).select_from(EmailCampaign)
        if status:
            query = query.where(EmailCampaign.status == status)
            count_q = count_q.where(EmailCampaign.status == status)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(EmailCampaign.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def update_campaign(
        session: AsyncSession, campaign: EmailCampaign, **kwargs: Any,
    ) -> EmailCampaign:
        for key, value in kwargs.items():
            if value is not None and hasattr(campaign, key):
                setattr(campaign, key, value)
        session.add(campaign)
        await session.flush()
        return campaign

    @staticmethod
    async def create_recipient(
        session: AsyncSession,
        *,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        email: str,
    ) -> EmailCampaignRecipient:
        recipient = EmailCampaignRecipient(
            campaign_id=campaign_id,
            user_id=user_id,
            email=email,
        )
        session.add(recipient)
        await session.flush()
        return recipient

    # -- In-App Notifications --

    @staticmethod
    async def create_notification(
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
        created_by: uuid.UUID | None = None,
    ) -> InAppNotification:
        notification = InAppNotification(
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
        session.add(notification)
        await session.flush()
        return notification

    @staticmethod
    async def get_notification_by_id(
        session: AsyncSession, notification_id: uuid.UUID,
    ) -> InAppNotification | None:
        query = select(InAppNotification).where(
            InAppNotification.id == notification_id
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_notifications(
        session: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InAppNotification], int]:
        query = select(InAppNotification)
        count_q = select(func.count()).select_from(InAppNotification)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(InAppNotification.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def create_delivery(
        session: AsyncSession,
        *,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> InAppNotificationDelivery:
        delivery = InAppNotificationDelivery(
            notification_id=notification_id,
            user_id=user_id,
        )
        session.add(delivery)
        await session.flush()
        return delivery

    # -- Announcements --

    @staticmethod
    async def create_announcement(
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
        created_by: uuid.UUID | None = None,
    ) -> Announcement:
        announcement = Announcement(
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
        session.add(announcement)
        await session.flush()
        return announcement

    @staticmethod
    async def get_announcement_by_id(
        session: AsyncSession, announcement_id: uuid.UUID,
    ) -> Announcement | None:
        query = select(Announcement).where(Announcement.id == announcement_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_announcements(
        session: AsyncSession,
        *,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Announcement], int]:
        query = select(Announcement)
        count_q = select(func.count()).select_from(Announcement)
        if is_active is not None:
            query = query.where(Announcement.is_active == is_active)
            count_q = count_q.where(Announcement.is_active == is_active)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(Announcement.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def update_announcement(
        session: AsyncSession, announcement: Announcement, **kwargs: Any,
    ) -> Announcement:
        for key, value in kwargs.items():
            if value is not None and hasattr(announcement, key):
                setattr(announcement, key, value)
        session.add(announcement)
        await session.flush()
        return announcement

    @staticmethod
    async def get_active_announcements_for_user(
        session: AsyncSession,
        user_id: uuid.UUID,
        user_plan: str,
    ) -> list[Announcement]:
        """Return active announcements visible to a given user."""
        now = datetime.now(timezone.utc)
        query = (
            select(Announcement)
            .where(Announcement.is_active.is_(True))
            .where(
                or_(
                    Announcement.starts_at.is_(None),
                    Announcement.starts_at <= now,
                )
            )
            .where(
                or_(
                    Announcement.expires_at.is_(None),
                    Announcement.expires_at > now,
                )
            )
        )
        announcements = (await session.execute(query)).scalars().all()

        # Filter out announcements the user has dismissed
        dismissed_q = select(AnnouncementDismissal.announcement_id).where(
            AnnouncementDismissal.user_id == user_id
        )
        dismissed_ids = set(
            (await session.execute(dismissed_q)).scalars().all()
        )
        announcements = [a for a in announcements if a.id not in dismissed_ids]

        # Filter by target_plans (if set)
        filtered = []
        for a in announcements:
            if a.target_plans and user_plan not in a.target_plans:
                continue
            filtered.append(a)
        return filtered

    @staticmethod
    async def dismiss_announcement(
        session: AsyncSession,
        announcement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        dismissal = AnnouncementDismissal(
            announcement_id=announcement_id,
            user_id=user_id,
        )
        session.add(dismissal)
        await session.flush()


# =============================================================================
# AdminOperationsRepository
# =============================================================================

class AdminOperationsRepository:
    @staticmethod
    async def list_health_alerts(
        session: AsyncSession,
        *,
        is_resolved: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SystemHealthAlert], int]:
        query = select(SystemHealthAlert)
        count_q = select(func.count()).select_from(SystemHealthAlert)
        if is_resolved is not None:
            query = query.where(SystemHealthAlert.is_resolved == is_resolved)
            count_q = count_q.where(SystemHealthAlert.is_resolved == is_resolved)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(SystemHealthAlert.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def list_error_logs(
        session: AsyncSession,
        *,
        level: str | None = None,
        is_resolved: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AppErrorLog], int]:
        query = select(AppErrorLog)
        count_q = select(func.count()).select_from(AppErrorLog)
        if level:
            query = query.where(AppErrorLog.level == level)
            count_q = count_q.where(AppErrorLog.level == level)
        if is_resolved is not None:
            query = query.where(AppErrorLog.is_resolved == is_resolved)
            count_q = count_q.where(AppErrorLog.is_resolved == is_resolved)
        total = (await session.execute(count_q)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(AppErrorLog.created_at.desc()).offset(offset).limit(page_size)
        rows = (await session.execute(query)).scalars().all()
        return list(rows), total

    @staticmethod
    async def resolve_error_log(
        session: AsyncSession, error_id: uuid.UUID,
    ) -> AppErrorLog | None:
        query = select(AppErrorLog).where(AppErrorLog.id == error_id)
        result = await session.execute(query)
        log = result.scalar_one_or_none()
        if log:
            log.is_resolved = True
            session.add(log)
            await session.flush()
        return log

    @staticmethod
    async def get_system_metrics(session: AsyncSession) -> dict[str, Any]:
        from app.modules.users.models import User
        from app.modules.organizations.models import Organization
        from app.modules.dependencies.models import Dependency
        from app.modules.incidents.models import Incident

        total_users = (await session.execute(
            select(func.count()).select_from(User)
        )).scalar() or 0
        total_orgs = (await session.execute(
            select(func.count()).select_from(Organization)
        )).scalar() or 0
        total_deps = (await session.execute(
            select(func.count()).select_from(Dependency)
        )).scalar() or 0
        open_incidents = (await session.execute(
            select(func.count()).select_from(Incident).where(
                Incident.status == "open"
            )
        )).scalar() or 0
        open_tickets = (await session.execute(
            select(func.count()).select_from(FeedbackTicket).where(
                FeedbackTicket.status == "open"
            )
        )).scalar() or 0

        return {
            "total_users": total_users,
            "total_orgs": total_orgs,
            "total_dependencies": total_deps,
            "total_incidents_open": open_incidents,
            "total_tickets_open": open_tickets,
            "db_pool_size": 10,
            "db_pool_checked_out": 0,
            "db_pool_overflow": 0,
        }
