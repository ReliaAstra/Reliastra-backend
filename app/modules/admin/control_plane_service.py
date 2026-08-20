"""Admin control-plane aggregation service.

Composes existing admin repositories/services into high-leverage operational
endpoints (overview, attention, customers, revenue, growth, product, etc.).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.permissions import get_plan_price_usd
from app.core.security import create_access_token
from app.infrastructure.email import email_client
from app.modules.admin.control_plane_schemas import (
    AdminOverviewResponse,
    AdminSearchResponse,
    AttentionItem,
    AttentionResponse,
    CommunicationsOverviewResponse,
    ComponentHealth,
    CustomerDetailResponse,
    CustomerImpersonateResponse,
    CustomerListItem,
    CustomerListResponse,
    CustomerOrgSnapshot,
    GrowthFunnelResponse,
    GrowthFunnelStage,
    GrowthOverviewResponse,
    GrowthReferralsResponse,
    OperationsOverviewResponse,
    OverviewBusinessSection,
    OverviewCommunicationsSection,
    OverviewGrowthSection,
    OverviewProductSection,
    OverviewSupportSection,
    OverviewSystemSection,
    ProductActivationResponse,
    ProductEngagementResponse,
    ProductFeatureItem,
    ProductFeaturesResponse,
    ProductOverviewResponse,
    ProductVendorItem,
    ProductVendorsResponse,
    RevenueAttentionResponse,
    RevenueDataPoint,
    RevenueSummaryResponse,
    RevenueTimeseriesResponse,
    SearchHit,
    SupportOverviewResponse,
    SupportTicketWorkspaceResponse,
)
from app.modules.admin.models import (
    Announcement,
    EmailCampaign,
    FeedbackTicket,
    InAppNotification,
    PlanChangeHistory,
)
from app.modules.admin.repository import (
    AdminAnalyticsRepository,
    AdminBusinessRepository,
    AdminFeedbackRepository,
    AdminOperationsRepository,
    AdminUserRepository,
)
from app.modules.admin.service import (
    IMPERSONATION_TOKEN_TTL_MINUTES,
    admin_audit_service,
    admin_business_service,
    admin_feedback_service,
    admin_operations_service,
    admin_user_service,
)

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "365d": 365,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100.0, 2)


class AdminControlPlaneService:
    """High-leverage operational aggregates for the admin console."""

    # ──────────────────────────────────────────────────────────────────────
    # Overview + Attention
    # ──────────────────────────────────────────────────────────────────────

    async def get_overview(self, session: AsyncSession) -> AdminOverviewResponse:
        business_raw = await AdminBusinessRepository.get_summary(session)
        engagement = await AdminAnalyticsRepository.get_engagement(session)
        metrics = await AdminOperationsRepository.get_system_metrics(session)
        support_stats = await AdminFeedbackRepository.get_ticket_stats(session)
        health = await admin_operations_service.health_check(session)
        engines = await admin_operations_service.check_engines(session)

        mrr = float(business_raw.get("mrr") or 0.0)
        paying = int(business_raw.get("active_subscriptions") or 0)
        users = int(business_raw.get("total_users") or 0)
        orgs = int(business_raw.get("total_organizations") or 0)
        new_signups = int(business_raw.get("new_signups_7d") or 0)
        churned = int(business_raw.get("churned_7d") or 0)

        # Communications counts
        drafts = await self._count_where(session, EmailCampaign, EmailCampaign.status == "draft")
        scheduled = await self._count_where(
            session, EmailCampaign, EmailCampaign.status == "scheduled"
        )
        active_campaigns = await self._count_where(
            session, EmailCampaign, EmailCampaign.status.in_(["sent", "sending"])
        )
        announcements_active = await self._count_where(
            session, Announcement, Announcement.is_active.is_(True)
        )

        # Support urgency
        urgent = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                FeedbackTicket.priority.in_(["urgent", "critical", "high"]),
            ),
        )
        unassigned = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                FeedbackTicket.assigned_to.is_(None),
            ),
        )

        # Product metrics
        checks_today = await self._count_checks_since(
            session, _now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        open_incidents = int(metrics.get("total_incidents_open") or 0)
        dependencies = int(metrics.get("total_dependencies") or 0)

        health_map = {c.component: c for c in health.checks}
        db_h = health_map.get("database")
        redis_h = health_map.get("redis")

        def _comp(item) -> ComponentHealth:
            if item is None:
                return ComponentHealth(status="unknown", last_checked=_now())
            status = "healthy" if item.status == "ok" else (
                "degraded" if item.status == "degraded" else "error"
            )
            return ComponentHealth(
                status=status,
                latency_ms=item.latency_ms,
                last_checked=_now(),
                error=item.message if status != "healthy" else None,
                message=item.message,
            )

        engine_list = engines.get("engines") or []
        worker_status = "healthy"
        if any(e.get("status") not in ("running", "idle", "ok") for e in engine_list):
            worker_status = "degraded"

        actions = await self._collect_attention_items(
            session,
            urgent_tickets=urgent,
            unassigned_tickets=unassigned,
            open_incidents=open_incidents,
            health=health,
            engines=engine_list,
        )

        return AdminOverviewResponse(
            business=OverviewBusinessSection(
                users=users,
                organizations=orgs,
                active_users=int(engagement.get("dau") or 0),
                active_organizations=paying,  # best available proxy
                paying_organizations=paying,
                mrr=mrr,
                arr_estimate=round(mrr * 12, 2),
                new_signups=new_signups,
                new_paying_customers=0,
                churn_count=churned,
                churn_rate=round(churned / max(paying, 1) * 100, 2),
            ),
            growth=OverviewGrowthSection(
                signup_growth=0.0,
                customer_growth=0.0,
                mrr_growth=0.0,
                conversion_rate=round(paying / max(orgs, 1) * 100, 2),
            ),
            product=OverviewProductSection(
                monitors=dependencies,
                active_monitors=dependencies,
                dependencies=dependencies,
                checks_today=checks_today,
                incidents=open_incidents,
                open_incidents=open_incidents,
            ),
            support=OverviewSupportSection(
                open_tickets=int(support_stats.get("open_tickets") or 0),
                urgent_tickets=urgent,
                unassigned_tickets=unassigned,
                average_response_time_hours=float(
                    support_stats.get("avg_resolution_hours") or 0.0
                ),
            ),
            communications=OverviewCommunicationsSection(
                active_campaigns=active_campaigns,
                scheduled_campaigns=scheduled,
                draft_campaigns=drafts,
                recent_announcements=announcements_active,
            ),
            system=OverviewSystemSection(
                api_health=ComponentHealth(status="healthy", last_checked=_now()),
                database_health=_comp(db_h),
                redis_health=_comp(redis_h),
                worker_health=ComponentHealth(
                    status=worker_status, last_checked=_now()
                ),
                scheduler_health=ComponentHealth(
                    status=worker_status, last_checked=_now()
                ),
            ),
            actions_required=actions,
            generated_at=_now(),
        )

    async def get_attention(self, session: AsyncSession) -> AttentionResponse:
        support_stats = await AdminFeedbackRepository.get_ticket_stats(session)
        urgent = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                FeedbackTicket.priority.in_(["urgent", "critical", "high"]),
            ),
        )
        unassigned = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                FeedbackTicket.assigned_to.is_(None),
            ),
        )
        metrics = await AdminOperationsRepository.get_system_metrics(session)
        health = await admin_operations_service.health_check(session)
        engines = (await admin_operations_service.check_engines(session)).get("engines") or []
        churn = await AdminBusinessRepository.get_churn_signals(session, limit=50)
        high_churn = [c for c in churn if c.get("risk_level") == "high"]

        # Pending partner payouts (best-effort)
        pending_payouts = 0
        try:
            from app.modules.partners.models import PartnerPayout

            pending_payouts = await self._count_where(
                session,
                PartnerPayout,
                PartnerPayout.status.in_(["pending", "processing", "requested"]),
            )
        except Exception:
            pending_payouts = 0

        items = await self._collect_attention_items(
            session,
            urgent_tickets=urgent,
            unassigned_tickets=unassigned,
            open_incidents=int(metrics.get("total_incidents_open") or 0),
            health=health,
            engines=engines,
            high_churn_count=len(high_churn),
            pending_payouts=pending_payouts,
            open_tickets=int(support_stats.get("open_tickets") or 0),
        )

        return AttentionResponse(
            items=items,
            critical_count=sum(1 for i in items if i.priority == "critical"),
            high_count=sum(1 for i in items if i.priority == "high"),
            normal_count=sum(1 for i in items if i.priority == "normal"),
            generated_at=_now(),
        )

    async def _collect_attention_items(
        self,
        session: AsyncSession,
        *,
        urgent_tickets: int = 0,
        unassigned_tickets: int = 0,
        open_incidents: int = 0,
        health=None,
        engines: list[dict[str, Any]] | None = None,
        high_churn_count: int = 0,
        pending_payouts: int = 0,
        open_tickets: int = 0,
    ) -> list[AttentionItem]:
        items: list[AttentionItem] = []

        if urgent_tickets > 0:
            items.append(
                AttentionItem(
                    type="urgent_support",
                    priority="critical",
                    count=urgent_tickets,
                    title=f"{urgent_tickets} urgent support ticket(s)",
                    description="Tickets marked urgent/critical/high that still need attention.",
                    target_resource="support_ticket",
                    href="/v1/admin/support/tickets?priority=urgent",
                )
            )

        if unassigned_tickets > 0:
            items.append(
                AttentionItem(
                    type="unassigned_support",
                    priority="high",
                    count=unassigned_tickets,
                    title=f"{unassigned_tickets} unassigned ticket(s)",
                    description="Open tickets with no assignee.",
                    target_resource="support_ticket",
                    href="/v1/admin/support/tickets?status=open",
                )
            )

        if open_incidents > 0:
            items.append(
                AttentionItem(
                    type="open_incidents",
                    priority="high" if open_incidents >= 5 else "normal",
                    count=open_incidents,
                    title=f"{open_incidents} open incident(s)",
                    description="Customer-facing incidents currently open.",
                    target_resource="incident",
                )
            )

        if high_churn_count > 0:
            items.append(
                AttentionItem(
                    type="churn_risk",
                    priority="high",
                    count=high_churn_count,
                    title=f"{high_churn_count} high-value customer(s) at churn risk",
                    description="Paying orgs with low recent activity.",
                    target_resource="customer",
                    href="/v1/admin/customers/churn-risk",
                )
            )

        if pending_payouts > 0:
            items.append(
                AttentionItem(
                    type="pending_partner_payouts",
                    priority="normal",
                    count=pending_payouts,
                    title=f"{pending_payouts} pending partner payout(s)",
                    description="Partner payouts awaiting processing.",
                    target_resource="partner_payout",
                    href="/v1/admin/partners/payouts",
                )
            )

        if health is not None:
            for check in health.checks:
                if check.status != "ok":
                    items.append(
                        AttentionItem(
                            type="system_health",
                            priority="critical",
                            count=1,
                            title=f"{check.component} unhealthy",
                            description=check.message or f"{check.component} status={check.status}",
                            target_resource="operations",
                            href="/v1/admin/operations/overview",
                        )
                    )

        for eng in engines or []:
            status = eng.get("status")
            if status not in ("running", "idle", "ok", None):
                items.append(
                    AttentionItem(
                        type="failed_worker",
                        priority="critical",
                        count=1,
                        title=f"Worker '{eng.get('name')}' is {status}",
                        description=eng.get("last_error") or "Background worker needs attention.",
                        target_resource="operations",
                        href="/v1/admin/operations/overview",
                    )
                )

        # Unresolved error logs
        try:
            from app.modules.admin.models import AppErrorLog

            unresolved = await self._count_where(
                session, AppErrorLog, AppErrorLog.is_resolved.is_(False)
            )
            if unresolved > 0:
                items.append(
                    AttentionItem(
                        type="unresolved_errors",
                        priority="high" if unresolved >= 10 else "normal",
                        count=unresolved,
                        title=f"{unresolved} unresolved error log(s)",
                        description="Application errors awaiting triage.",
                        target_resource="error_log",
                        href="/v1/admin/operations/errors",
                    )
                )
        except Exception:
            pass

        priority_rank = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        items.sort(key=lambda i: (priority_rank.get(i.priority, 9), -i.count))
        return items

    # ──────────────────────────────────────────────────────────────────────
    # Global search
    # ──────────────────────────────────────────────────────────────────────

    async def search(
        self, session: AsyncSession, q: str, *, limit: int = 8
    ) -> AdminSearchResponse:
        q = (q or "").strip()
        if len(q) < 2:
            return AdminSearchResponse(query=q, total=0)

        pattern = f"%{q}%"
        customers: list[SearchHit] = []
        organizations: list[SearchHit] = []
        tickets: list[SearchHit] = []
        partners: list[SearchHit] = []
        campaigns: list[SearchHit] = []

        from app.modules.users.models import User
        from app.modules.organizations.models import Organization

        user_rows = (
            await session.execute(
                select(User)
                .where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
                .order_by(User.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for u in user_rows:
            customers.append(
                SearchHit(
                    resource_type="customer",
                    id=str(u.id),
                    title=u.full_name or u.email,
                    subtitle=u.email,
                    href=f"/v1/admin/customers/{u.id}",
                    meta={"is_active": u.is_active},
                )
            )

        org_rows = (
            await session.execute(
                select(Organization)
                .where(Organization.name.ilike(pattern))
                .order_by(Organization.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for o in org_rows:
            organizations.append(
                SearchHit(
                    resource_type="organization",
                    id=str(o.id),
                    title=o.name,
                    subtitle=o.plan,
                    href=f"/v1/admin/customers?search={o.name}",
                    meta={"plan": o.plan},
                )
            )

        ticket_rows = (
            await session.execute(
                select(FeedbackTicket)
                .where(
                    or_(
                        FeedbackTicket.subject.ilike(pattern),
                        FeedbackTicket.email.ilike(pattern),
                        FeedbackTicket.ticket_number.ilike(pattern),
                    )
                )
                .order_by(FeedbackTicket.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for t in ticket_rows:
            tickets.append(
                SearchHit(
                    resource_type="ticket",
                    id=str(t.id),
                    title=f"{t.ticket_number}: {t.subject}",
                    subtitle=f"{t.status} · {t.priority}",
                    href=f"/v1/admin/support/tickets/{t.id}",
                    meta={"status": t.status, "priority": t.priority},
                )
            )

        try:
            from app.modules.partners.models import PartnerProfile
            from app.modules.users.repository import UserRepository

            partner_rows = (
                await session.execute(
                    select(PartnerProfile).limit(50)
                )
            ).scalars().all()
            matched = 0
            for p in partner_rows:
                if matched >= limit:
                    break
                user = await UserRepository.get_by_id(session, p.user_id)
                email = (user.email if user else "") or ""
                if q.lower() in email.lower() or q.lower() in str(p.id).lower():
                    partners.append(
                        SearchHit(
                            resource_type="partner",
                            id=str(p.id),
                            title=email or str(p.id),
                            subtitle=p.status,
                            href=f"/v1/admin/partners/{p.id}",
                            meta={"status": p.status},
                        )
                    )
                    matched += 1
        except Exception:
            pass

        campaign_rows = (
            await session.execute(
                select(EmailCampaign)
                .where(
                    or_(
                        EmailCampaign.campaign_name.ilike(pattern),
                        EmailCampaign.subject.ilike(pattern),
                    )
                )
                .order_by(EmailCampaign.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for c in campaign_rows:
            campaigns.append(
                SearchHit(
                    resource_type="campaign",
                    id=str(c.id),
                    title=c.campaign_name,
                    subtitle=c.status,
                    href=f"/v1/admin/communications/campaigns/{c.id}",
                    meta={"status": c.status},
                )
            )

        total = (
            len(customers)
            + len(organizations)
            + len(tickets)
            + len(partners)
            + len(campaigns)
        )
        return AdminSearchResponse(
            query=q,
            customers=customers,
            organizations=organizations,
            tickets=tickets,
            partners=partners,
            campaigns=campaigns,
            total=total,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Customers
    # ──────────────────────────────────────────────────────────────────────

    async def list_customers(
        self,
        session: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        plan: str | None = None,
        segment: str | None = None,
        health: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "created_at_desc",
    ) -> CustomerListResponse:
        from app.modules.users.models import User

        is_active = None
        if status == "active":
            is_active = True
        elif status in ("inactive", "deactivated"):
            is_active = False

        # segment reserved for future filters (founding program removed)
        _ = segment

        query = select(User)
        count_q = select(func.count()).select_from(User)
        filters = []
        if search:
            pattern = f"%{search}%"
            filters.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
        if is_active is not None:
            filters.append(User.is_active == is_active)
        if created_from is not None:
            filters.append(User.created_at >= created_from)
        if created_to is not None:
            filters.append(User.created_at <= created_to)
        for f in filters:
            query = query.where(f)
            count_q = count_q.where(f)

        total = (await session.execute(count_q)).scalar() or 0
        if sort == "created_at_asc":
            query = query.order_by(User.created_at.asc())
        elif sort == "name":
            query = query.order_by(User.full_name.asc())
        else:
            query = query.order_by(User.created_at.desc())

        offset = (page - 1) * page_size
        users = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()

        items: list[CustomerListItem] = []
        for u in users:
            orgs = await AdminUserRepository.get_user_orgs(session, u.id)
            primary = orgs[0] if orgs else None
            org_plan = primary["plan"] if primary else None
            if plan and org_plan != plan:
                continue
            org_id = primary["org_id"] if primary else None

            cust_health = self._derive_health(
                is_active=u.is_active,
                last_activity_at=getattr(u, "last_activity_at", None),
                plan=org_plan,
            )
            if health and cust_health != health:
                continue

            mrr = float(get_plan_price_usd(org_plan)) if org_plan and org_plan != "free" else 0.0
            items.append(
                CustomerListItem(
                    customer_id=u.id,
                    email=u.email,
                    full_name=u.full_name,
                    is_active=u.is_active,
                    source=u.source,
                    plan=org_plan,
                    org_id=org_id,
                    org_name=primary["org_name"] if primary else None,
                    health=cust_health,
                    mrr=mrr,
                    last_activity_at=getattr(u, "last_activity_at", None),
                    created_at=u.created_at,
                )
            )

        return CustomerListResponse(
            items=items, total=total, page=page, page_size=page_size
        )

    async def get_customer_detail(
        self, session: AsyncSession, customer_id: uuid.UUID
    ) -> CustomerDetailResponse:
        from app.modules.users.repository import UserRepository
        from app.modules.organizations.models import Organization, OrganizationMember
        from app.modules.billing.models import Subscription
        from app.modules.dependencies.models import Dependency
        from app.modules.incidents.models import Incident

        user = await UserRepository.get_by_id(session, customer_id)
        if not user:
            raise ResourceNotFoundException("Customer not found")

        org_rows = (
            await session.execute(
                select(Organization, OrganizationMember.role)
                .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
                .where(OrganizationMember.user_id == customer_id)
            )
        ).all()

        org_snapshots: list[CustomerOrgSnapshot] = []
        total_deps = 0
        total_incidents = 0
        open_incidents = 0
        total_mrr = 0.0
        primary: CustomerOrgSnapshot | None = None
        subscription_payload: dict[str, Any] | None = None

        for org, role in org_rows:
            member_count = (
                await session.execute(
                    select(func.count())
                    .select_from(OrganizationMember)
                    .where(OrganizationMember.org_id == org.id)
                )
            ).scalar() or 0
            dep_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Dependency)
                    .where(Dependency.org_id == org.id)
                )
            ).scalar() or 0
            open_inc = (
                await session.execute(
                    select(func.count())
                    .select_from(Incident)
                    .where(Incident.org_id == org.id, Incident.status == "open")
                )
            ).scalar() or 0
            all_inc = (
                await session.execute(
                    select(func.count())
                    .select_from(Incident)
                    .where(Incident.org_id == org.id)
                )
            ).scalar() or 0

            sub = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.organization_id == org.id)
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            billing_status = sub.status if sub else None
            org_mrr = (
                float(get_plan_price_usd(org.plan))
                if org.plan and org.plan != "free"
                else 0.0
            )
            open_tickets = (
                await session.execute(
                    select(func.count())
                    .select_from(FeedbackTicket)
                    .where(
                        FeedbackTicket.user_id == customer_id,
                        FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                    )
                )
            ).scalar() or 0

            snap = CustomerOrgSnapshot(
                org_id=org.id,
                org_name=org.name,
                role=role,
                plan=org.plan,
                mrr=org_mrr,
                billing_status=billing_status,
                member_count=member_count,
                dependency_count=dep_count,
                open_incidents=open_inc,
                open_tickets=open_tickets,
            )
            org_snapshots.append(snap)
            total_deps += dep_count
            total_incidents += all_inc
            open_incidents += open_inc
            total_mrr += org_mrr
            if primary is None or role == "owner":
                primary = snap
                if sub:
                    subscription_payload = {
                        "id": str(sub.id),
                        "plan": sub.plan,
                        "status": sub.status,
                        "organization_id": str(sub.organization_id),
                    }

        activity_logs, _ = await AdminUserRepository.list_activity(
            session, customer_id, page=1, page_size=10
        )
        recent_activity = [
            {
                "id": str(a.id),
                "action": a.action,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activity_logs
        ]

        tickets, ticket_total = await AdminFeedbackRepository.list_tickets(
            session, search=user.email, page=1, page_size=5
        )
        # Prefer user_id match when available
        user_tickets = (
            await session.execute(
                select(FeedbackTicket)
                .where(FeedbackTicket.user_id == customer_id)
                .order_by(FeedbackTicket.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
        ticket_source = user_tickets or tickets
        recent_tickets = [
            {
                "id": str(t.id),
                "ticket_number": t.ticket_number,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in ticket_source
        ]
        open_support = sum(
            1
            for t in ticket_source
            if t.status in ("open", "in_progress", "pending")
        )

        plan = primary.plan if primary else None
        health = self._derive_health(
            is_active=user.is_active,
            last_activity_at=getattr(user, "last_activity_at", None),
            plan=plan,
        )

        return CustomerDetailResponse(
            customer_id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_email_verified=bool(getattr(user, "is_email_verified", False)),
            is_system_admin=bool(getattr(user, "is_system_admin", False)),
            avatar_url=getattr(user, "avatar_url", None),
            auth_provider=getattr(user, "auth_provider", None),
            source=user.source,
            admin_note=getattr(user, "admin_note", None),
            health=health,
            last_login_at=getattr(user, "last_login_at", None),
            last_activity_at=getattr(user, "last_activity_at", None),
            login_count=int(getattr(user, "login_count", 0) or 0),
            created_at=user.created_at,
            updated_at=getattr(user, "updated_at", None),
            organizations=org_snapshots,
            primary_org=primary,
            plan=plan,
            mrr=total_mrr,
            billing_status=primary.billing_status if primary else None,
            subscription=subscription_payload,
            dependencies=total_deps,
            monitors=total_deps,
            incidents=total_incidents,
            open_incidents=open_incidents,
            support_tickets=ticket_total if not user_tickets else len(user_tickets),
            open_support_tickets=open_support,
            recent_activity=recent_activity,
            recent_tickets=recent_tickets,
        )

    async def update_customer(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        full_name: str | None = None,
        admin_note: str | None = None,
        source: str | None = None,
    ) -> CustomerDetailResponse:
        kwargs: dict[str, Any] = {}
        if full_name is not None:
            kwargs["full_name"] = full_name
        if admin_note is not None:
            kwargs["admin_note"] = admin_note
        if source is not None:
            kwargs["source"] = source
        await admin_user_service.update_user(
            session,
            customer_id,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            ip_address=ip_address,
            user_agent=user_agent,
            **kwargs,
        )
        return await self.get_customer_detail(session, customer_id)

    async def impersonate_customer(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        reason: str,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerImpersonateResponse:
        from app.modules.users.repository import UserRepository
        import jwt as _jwt
        from app.config import settings

        user = await UserRepository.get_by_id(session, customer_id)
        if not user:
            raise ResourceNotFoundException("Customer not found")
        if not user.is_active:
            raise ValidationException("Cannot impersonate an inactive customer")
        if not reason or len(reason.strip()) < 3:
            raise ValidationException("Impersonation reason is required")

        token = create_access_token(
            subject=str(customer_id),
            additional_claims={
                "impersonator_id": str(admin_user_id),
                "impersonated_user_id": str(customer_id),
                "type": "impersonation",
                "reason": reason.strip()[:200],
                # Explicit: no refresh token for impersonation sessions
                "refresh": False,
            },
        )
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        payload["exp"] = int(
            (
                _now() + timedelta(minutes=IMPERSONATION_TOKEN_TTL_MINUTES)
            ).timestamp()
        )
        token = _jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        await admin_audit_service.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="impersonate_customer",
            entity_type="customer",
            entity_id=str(customer_id),
            details={"reason": reason.strip()},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return CustomerImpersonateResponse(
            token=token,
            impersonated_user_id=customer_id,
            impersonated_email=user.email,
            expires_in_seconds=IMPERSONATION_TOKEN_TTL_MINUTES * 60,
            impersonator_id=admin_user_id,
            reason=reason.strip(),
            no_refresh_token=True,
        )

    async def change_customer_plan(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        plan: str,
        reason: str | None,
        org_id: uuid.UUID | None,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.organizations.repository import OrganizationRepository
        from app.modules.organizations.models import Organization, OrganizationMember

        if org_id is None:
            orgs = await AdminUserRepository.get_user_orgs(session, customer_id)
            if not orgs:
                raise ResourceNotFoundException(
                    "Customer has no organization to apply plan to"
                )
            # Prefer owner org
            owner = next((o for o in orgs if o["role"] == "owner"), orgs[0])
            org_id = owner["org_id"]

        org = await OrganizationRepository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        # Ensure customer is a member of the org
        membership = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.org_id == org_id,
                    OrganizationMember.user_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ValidationException("Customer is not a member of the target organization")

        from_plan = org.plan
        await OrganizationRepository.update(session, org, plan=plan)

        change = PlanChangeHistory(
            org_id=org_id,
            changed_by=admin_user_id,
            from_plan=from_plan,
            to_plan=plan,
            reason=reason,
            admin_note=f"Admin plan change by {admin_email} for customer {customer_id}",
        )
        session.add(change)
        await session.flush()

        await admin_audit_service.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="override_plan",
            entity_type="organization",
            entity_id=str(org_id),
            details={
                "from_plan": from_plan,
                "to_plan": plan,
                "reason": reason,
                "customer_id": str(customer_id),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "customer_id": str(customer_id),
            "org_id": str(org_id),
            "from_plan": from_plan,
            "to_plan": plan,
            "message": f"Plan changed from {from_plan} to {plan}",
        }

    async def email_customer(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        subject: str,
        body: str,
        html_body: str | None,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, customer_id)
        if not user:
            raise ResourceNotFoundException("Customer not found")

        success = email_client.send_email(
            to_email=user.email,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        await admin_audit_service.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="send_email_to_customer",
            entity_type="customer",
            entity_id=str(customer_id),
            details={"subject": subject, "success": success},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {"success": success, "customer_id": str(customer_id)}

    async def deactivate_customer(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        reason: str,
        admin_user_id: uuid.UUID,
        admin_email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerDetailResponse:
        from app.modules.users.repository import UserRepository

        user = await UserRepository.get_by_id(session, customer_id)
        if not user:
            raise ResourceNotFoundException("Customer not found")
        if customer_id == admin_user_id:
            raise ValidationException("Cannot deactivate your own admin account")

        await UserRepository.update(session, user, is_active=False)
        note = getattr(user, "admin_note", None) or ""
        stamp = f"[deactivated {_now().isoformat()}] {reason}"
        new_note = f"{note}\n{stamp}".strip() if note else stamp
        await UserRepository.update(session, user, admin_note=new_note)

        await admin_audit_service.log_action(
            session,
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            action="deactivate_customer",
            entity_type="customer",
            entity_id=str(customer_id),
            details={"reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.get_customer_detail(session, customer_id)

    async def get_customer_activity(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        logs, total = await AdminUserRepository.list_activity(
            session, customer_id, page=page, page_size=page_size
        )
        return {
            "items": [
                {
                    "id": str(a.id),
                    "action": a.action,
                    "details": a.details,
                    "ip_address": a.ip_address,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in logs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_recent_customers(
        self, session: AsyncSession, *, limit: int = 20
    ) -> dict[str, Any]:
        signups = await admin_business_service.get_recent_signups(session, limit=limit)
        return {
            "items": [
                {
                    "customer_id": s.user_id,
                    "email": s.email,
                    "full_name": s.full_name,
                    "org_name": s.org_name,
                    "plan": s.plan,
                    "source": s.source,
                    "created_at": s.created_at,
                }
                for s in signups.items
            ]
        }

    async def get_churn_risk(
        self, session: AsyncSession, *, limit: int = 20
    ) -> dict[str, Any]:
        signals = await admin_business_service.get_churn_signals(session, limit=limit)
        return {
            "items": [
                {
                    "org_id": s.org_id,
                    "org_name": s.org_name,
                    "plan": s.plan,
                    "last_activity_at": s.last_activity_at,
                    "subscription_status": s.subscription_status,
                    "risk_level": s.risk_level,
                    "health": "at_risk" if s.risk_level == "high" else "healthy",
                }
                for s in signals.items
            ]
        }

    # ──────────────────────────────────────────────────────────────────────
    # Revenue
    # ──────────────────────────────────────────────────────────────────────

    async def get_revenue_summary(self, session: AsyncSession) -> RevenueSummaryResponse:
        summary = await AdminBusinessRepository.get_summary(session)
        mrr = float(summary.get("mrr") or 0.0)
        paying = int(summary.get("active_subscriptions") or 0)
        arpu = round(mrr / max(paying, 1), 2)
        return RevenueSummaryResponse(
            mrr=mrr,
            mrr_growth=0.0,  # requires historical snapshots
            arr_estimate=round(mrr * 12, 2),
            new_mrr=0.0,
            expansion_mrr=0.0,
            contraction_mrr=0.0,
            churned_mrr=0.0,
            net_new_mrr=0.0,
            paying_customers=paying,
            arpu=arpu,
            currency="USD",
        )

    async def get_revenue_timeseries(
        self,
        session: AsyncSession,
        *,
        period: str = "30d",
        granularity: str = "day",
    ) -> RevenueTimeseriesResponse:
        days = _PERIOD_DAYS.get(period, 30)
        if granularity == "week":
            # sample weekly points
            raw = await AdminBusinessRepository.get_mrr_timeseries(session, days=days)
            points = [
                RevenueDataPoint(date=p["date"], mrr=p["mrr"])
                for i, p in enumerate(raw)
                if i % 7 == 0 or i == len(raw) - 1
            ]
        elif granularity == "month":
            raw = await AdminBusinessRepository.get_mrr_timeseries(session, days=days)
            points = [
                RevenueDataPoint(date=p["date"], mrr=p["mrr"])
                for i, p in enumerate(raw)
                if i % 30 == 0 or i == len(raw) - 1
            ]
        else:
            raw = await AdminBusinessRepository.get_mrr_timeseries(session, days=days)
            points = [RevenueDataPoint(date=p["date"], mrr=p["mrr"]) for p in raw]

        return RevenueTimeseriesResponse(
            period=period, granularity=granularity, data_points=points
        )

    async def get_revenue_attention(
        self, session: AsyncSession
    ) -> RevenueAttentionResponse:
        churn = await AdminBusinessRepository.get_churn_signals(session, limit=20)
        high_value = [
            AttentionItem(
                type="high_value_churn",
                priority="high" if c.get("risk_level") == "high" else "normal",
                count=1,
                title=f"{c.get('org_name')} at churn risk",
                description=f"Plan={c.get('plan')} risk={c.get('risk_level')}",
                target_resource="organization",
                target_id=str(c.get("org_id")),
                href="/v1/admin/customers/churn-risk",
            )
            for c in churn
            if c.get("risk_level") in ("high", "medium")
        ]
        items = list(high_value)
        return RevenueAttentionResponse(
            failed_payments=[],  # requires payment-provider failure events
            revenue_drop_alerts=[],
            unusual_mrr_changes=[],
            high_value_churn=high_value,
            items=items,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Growth
    # ──────────────────────────────────────────────────────────────────────

    async def get_growth_overview(
        self, session: AsyncSession, *, period: str = "30d"
    ) -> GrowthOverviewResponse:
        days = _PERIOD_DAYS.get(period, 30)
        since = _now() - timedelta(days=days)

        from app.modules.users.models import User
        from app.modules.organizations.models import Organization
        from app.modules.dependencies.models import Dependency
        from app.modules.billing.models import Subscription

        signups = (
            await session.execute(
                select(func.count()).select_from(User).where(User.created_at >= since)
            )
        ).scalar() or 0

        activated_orgs = (
            await session.execute(
                select(func.count(func.distinct(Dependency.org_id))).select_from(Dependency)
            )
        ).scalar() or 0

        paying = (
            await session.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "active")
            )
        ).scalar() or 0

        total_orgs = (
            await session.execute(select(func.count()).select_from(Organization))
        ).scalar() or 0

        engagement = await AdminAnalyticsRepository.get_engagement(session)
        funnel = await AdminAnalyticsRepository.get_growth_funnel(session)
        activated_users = next(
            (s["count"] for s in funnel if s["stage"] == "organizations"), 0
        )

        return GrowthOverviewResponse(
            signups=signups,
            activated_users=activated_users,
            activated_organizations=activated_orgs,
            paying_customers=paying,
            conversion_rate=round(paying / max(total_orgs, 1) * 100, 2),
            mrr_growth=0.0,
            retention_summary={},
            engagement=engagement,
            period=period,
        )

    async def get_growth_funnel(
        self, session: AsyncSession, *, period: str = "30d"
    ) -> GrowthFunnelResponse:
        stages_raw = await AdminAnalyticsRepository.get_growth_funnel(session)

        # Enrich with available activation stages
        from app.modules.users.models import User
        from app.modules.organizations.models import Organization
        from app.modules.dependencies.models import Dependency
        from app.modules.billing.models import Subscription
        from app.modules.checks.models import CheckResult

        total_users = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar() or 0
        verified = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.is_email_verified.is_(True))
            )
        ).scalar() or 0
        total_orgs = (
            await session.execute(select(func.count()).select_from(Organization))
        ).scalar() or 0
        deps = (
            await session.execute(
                select(func.count(func.distinct(Dependency.org_id))).select_from(Dependency)
            )
        ).scalar() or 0
        monitoring = (
            await session.execute(
                select(func.count(func.distinct(CheckResult.org_id))).select_from(
                    CheckResult
                )
            )
        ).scalar() or 0
        paid = (
            await session.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "active")
            )
        ).scalar() or 0

        stage_defs = [
            ("signup", total_users),
            ("verified", verified),
            ("organization", total_orgs),
            ("dependency_added", deps),
            ("monitoring_started", monitoring),
            ("activated", monitoring),
            ("paid", paid),
        ]
        stages: list[GrowthFunnelStage] = []
        prev = None
        for name, count in stage_defs:
            conv = None
            if prev is not None and prev > 0:
                conv = round(count / prev, 4)
            stages.append(
                GrowthFunnelStage(
                    stage=name, count=count, conversion_from_previous=conv
                )
            )
            prev = count

        # Attach PLG funnel when available
        plg = None
        try:
            from app.modules.growth.service import growth_service

            plg_funnel = await growth_service.get_funnel(session, period=period)
            plg = plg_funnel.model_dump()
        except Exception as exc:
            logger.debug("PLG funnel unavailable: %s", exc)

        return GrowthFunnelResponse(period=period, stages=stages, plg=plg)

    async def get_growth_retention(
        self, session: AsyncSession, *, weeks: int = 4
    ) -> dict[str, Any]:
        cohorts = await AdminAnalyticsRepository.get_retention_cohorts(session, weeks)
        return {"cohorts": cohorts, "weeks": weeks}

    async def get_growth_referrals(self, session: AsyncSession) -> GrowthReferralsResponse:
        try:
            from app.modules.growth.service import growth_service

            data = await growth_service.get_referral_stats(session)
            return GrowthReferralsResponse(
                summary=data.get("summary") or {},
                top_referrers=data.get("top_referrers") or [],
            )
        except Exception as exc:
            logger.warning("Referral stats unavailable: %s", exc)
            return GrowthReferralsResponse()

    # ──────────────────────────────────────────────────────────────────────
    # Product
    # ──────────────────────────────────────────────────────────────────────

    async def get_product_overview(self, session: AsyncSession) -> ProductOverviewResponse:
        engagement = await AdminAnalyticsRepository.get_engagement(session)
        features = await AdminAnalyticsRepository.get_feature_adoption(session)
        vendors = await AdminAnalyticsRepository.get_vendor_coverage(session)
        ttv = await AdminAnalyticsRepository.get_time_to_value(session)
        metrics = await AdminOperationsRepository.get_system_metrics(session)
        checks_today = await self._count_checks_since(
            session, _now().replace(hour=0, minute=0, second=0, microsecond=0)
        )

        return ProductOverviewResponse(
            active_users=int(engagement.get("dau") or 0),
            active_organizations=int(metrics.get("total_orgs") or 0),
            active_monitors=int(metrics.get("total_dependencies") or 0),
            checks=0,
            checks_today=checks_today,
            incidents=int(metrics.get("total_incidents_open") or 0),
            open_incidents=int(metrics.get("total_incidents_open") or 0),
            dependencies=int(metrics.get("total_dependencies") or 0),
            vendor_coverage_top=vendors[:5],
            feature_adoption=features,
            time_to_value={"buckets": ttv},
            engagement=engagement,
        )

    async def get_product_features(self, session: AsyncSession) -> ProductFeaturesResponse:
        raw = await AdminAnalyticsRepository.get_feature_adoption(session)
        features = [
            ProductFeatureItem(
                feature=f.get("feature", "unknown"),
                eligible=int(f.get("total_users") or 0),
                adopted=int(f.get("active_users") or 0),
                adoption_rate=round(
                    (f.get("active_users") or 0) / max(f.get("total_users") or 1, 1), 4
                ),
            )
            for f in raw
        ]
        return ProductFeaturesResponse(features=features)

    async def get_product_vendors(
        self, session: AsyncSession, *, limit: int = 20
    ) -> ProductVendorsResponse:
        coverage = await AdminAnalyticsRepository.get_vendor_coverage(session)
        # Merge PLG top-vendor stats when available
        plg_map: dict[str, Any] = {}
        try:
            from app.modules.growth.service import growth_service

            top = await growth_service.get_top_vendors(session, sort_by="views", limit=limit)
            plg_map = {t.vendor_name: t for t in top}
        except Exception:
            pass

        items: list[ProductVendorItem] = []
        seen: set[str] = set()
        for v in coverage[:limit]:
            name = v.get("vendor_name") or "unknown"
            seen.add(name)
            plg = plg_map.get(name)
            items.append(
                ProductVendorItem(
                    vendor=name,
                    organizations_using=int(v.get("monitoring_orgs") or 0),
                    coverage_percentage=float(v.get("coverage_pct") or 0.0),
                    incidents=0,
                    monitoring_volume=int(v.get("monitoring_orgs") or 0),
                    views=plg.views if plg else None,
                    badge_embeds=plg.badge_embeds if plg else None,
                    submissions=plg.submissions if plg else None,
                    evidence_downloads=plg.evidence_downloads if plg else None,
                )
            )
        for name, plg in plg_map.items():
            if name in seen:
                continue
            items.append(
                ProductVendorItem(
                    vendor=name,
                    organizations_using=0,
                    coverage_percentage=0.0,
                    views=plg.views,
                    badge_embeds=plg.badge_embeds,
                    submissions=plg.submissions,
                    evidence_downloads=plg.evidence_downloads,
                )
            )
        return ProductVendorsResponse(vendors=items[:limit])

    async def get_product_engagement(
        self, session: AsyncSession
    ) -> ProductEngagementResponse:
        m = await AdminAnalyticsRepository.get_engagement(session)
        dau = int(m.get("dau") or 0)
        mau = int(m.get("mau") or 0)
        return ProductEngagementResponse(
            dau=dau,
            wau=int(m.get("wau") or 0),
            mau=mau,
            stickiness=round(dau / max(mau, 1), 4),
        )

    async def get_product_activation(
        self, session: AsyncSession
    ) -> ProductActivationResponse:
        buckets = await AdminAnalyticsRepository.get_time_to_value(session)
        funnel = await AdminAnalyticsRepository.get_growth_funnel(session)
        signups = next((s["count"] for s in funnel if s["stage"] == "signups"), 0)
        monitoring = next(
            (s["count"] for s in funnel if s["stage"] == "dependencies_monitored"), 0
        )
        # Fallback activation rate from org-level monitoring coverage
        from app.modules.organizations.models import Organization
        from app.modules.checks.models import CheckResult

        total_orgs = (
            await session.execute(select(func.count()).select_from(Organization))
        ).scalar() or 0
        orgs_with_checks = (
            await session.execute(
                select(func.count(func.distinct(CheckResult.org_id))).select_from(
                    CheckResult
                )
            )
        ).scalar() or 0
        activation_rate = round(orgs_with_checks / max(total_orgs, 1), 4)

        return ProductActivationResponse(
            median_time_to_first_check_hours=None,
            p25_hours=None,
            p50_hours=None,
            p75_hours=None,
            activation_rate=activation_rate,
            buckets=buckets,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Support
    # ──────────────────────────────────────────────────────────────────────

    async def get_support_overview(self, session: AsyncSession) -> SupportOverviewResponse:
        stats = await AdminFeedbackRepository.get_ticket_stats(session)
        open_count = int(stats.get("open_tickets") or 0)
        by_priority = stats.get("by_priority") or {}
        urgent = int(by_priority.get("urgent") or 0) + int(
            by_priority.get("critical") or 0
        ) + int(by_priority.get("high") or 0)

        unassigned = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status.in_(["open", "in_progress", "pending"]),
                FeedbackTicket.assigned_to.is_(None),
            ),
        )
        waiting_customer = await self._count_where(
            session, FeedbackTicket, FeedbackTicket.status == "waiting_on_customer"
        )
        waiting_agent = await self._count_where(
            session, FeedbackTicket, FeedbackTicket.status == "waiting_on_agent"
        )
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        resolved_today = await self._count_where(
            session,
            FeedbackTicket,
            and_(
                FeedbackTicket.status == "resolved",
                FeedbackTicket.resolved_at >= today_start,
            ),
        )

        queue = {
            "critical": int(by_priority.get("critical") or 0),
            "urgent": int(by_priority.get("urgent") or 0),
            "high": int(by_priority.get("high") or 0),
            "normal": int(by_priority.get("normal") or 0),
            "low": int(by_priority.get("low") or 0),
        }

        return SupportOverviewResponse(
            open=open_count,
            urgent=urgent,
            unassigned=unassigned,
            waiting_on_customer=waiting_customer,
            waiting_on_agent=waiting_agent,
            resolved_today=resolved_today,
            average_first_response_hours=0.0,
            average_resolution_hours=float(stats.get("avg_resolution_hours") or 0.0),
            sla_breaches=0,
            queue=queue,
            by_category=stats.get("by_category") or {},
        )

    async def get_support_ticket_workspace(
        self, session: AsyncSession, ticket_id: uuid.UUID
    ) -> SupportTicketWorkspaceResponse:
        detail = await admin_feedback_service.get_ticket(session, ticket_id)
        ticket = detail.ticket
        messages = [m.model_dump(mode="json") for m in detail.messages]

        customer_payload = None
        org_payload = None
        subscription_payload = None
        recent_activity: list[dict[str, Any]] = []
        related_incidents: list[dict[str, Any]] = []

        if ticket.user_id:
            try:
                cust = await self.get_customer_detail(session, ticket.user_id)
                customer_payload = {
                    "customer_id": str(cust.customer_id),
                    "email": cust.email,
                    "full_name": cust.full_name,
                    "is_active": cust.is_active,
                    "plan": cust.plan,
                    "mrr": cust.mrr,
                    "health": cust.health,
                    "billing_status": cust.billing_status,
                }
                if cust.primary_org:
                    org_payload = cust.primary_org.model_dump(mode="json")
                subscription_payload = cust.subscription
                recent_activity = cust.recent_activity
            except Exception as exc:
                logger.debug("Could not load customer for ticket: %s", exc)

        return SupportTicketWorkspaceResponse(
            ticket=ticket.model_dump(mode="json"),
            messages=messages,
            customer=customer_payload,
            organization=org_payload,
            subscription=subscription_payload,
            recent_customer_activity=recent_activity,
            related_incidents=related_incidents,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Communications
    # ──────────────────────────────────────────────────────────────────────

    async def get_communications_overview(
        self, session: AsyncSession
    ) -> CommunicationsOverviewResponse:
        total = await self._count(session, EmailCampaign)
        drafts = await self._count_where(
            session, EmailCampaign, EmailCampaign.status == "draft"
        )
        scheduled = await self._count_where(
            session, EmailCampaign, EmailCampaign.status == "scheduled"
        )
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = await self._count_where(
            session,
            EmailCampaign,
            and_(
                EmailCampaign.status == "sent",
                EmailCampaign.sent_at >= today_start,
            ),
        )
        notifications = await self._count(session, InAppNotification)
        announcements_total = await self._count(session, Announcement)
        announcements_active = await self._count_where(
            session, Announcement, Announcement.is_active.is_(True)
        )

        # Aggregate delivery stats from recent campaigns
        recent = (
            await session.execute(
                select(EmailCampaign)
                .where(EmailCampaign.status == "sent")
                .order_by(EmailCampaign.sent_at.desc())
                .limit(10)
            )
        ).scalars().all()
        delivery = {
            "recent_campaigns": len(recent),
            "recipients": sum(c.recipient_count or 0 for c in recent),
            "sent": sum(c.sent_count or 0 for c in recent),
            "opened": sum(c.opened_count or 0 for c in recent),
            "clicked": sum(c.clicked_count or 0 for c in recent),
            "bounced": sum(c.bounced_count or 0 for c in recent),
            "failed": sum(c.failed_count or 0 for c in recent),
        }

        return CommunicationsOverviewResponse(
            campaigns_total=total,
            drafts=drafts,
            scheduled=scheduled,
            sent_today=sent_today,
            notifications=notifications,
            announcements_active=announcements_active,
            announcements_total=announcements_total,
            recent_delivery_stats=delivery,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Operations
    # ──────────────────────────────────────────────────────────────────────

    async def get_operations_overview(
        self, session: AsyncSession
    ) -> OperationsOverviewResponse:
        import time as _time
        from sqlalchemy import text
        from app.db.session import get_engine

        now = _now()
        overall = "healthy"

        # API — if we are serving this request, API is up
        api = ComponentHealth(status="healthy", latency_ms=0.0, last_checked=now)

        # Database
        try:
            engine = get_engine()
            start = _time.monotonic()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db = ComponentHealth(
                status="healthy",
                latency_ms=round((_time.monotonic() - start) * 1000, 2),
                last_checked=now,
            )
        except Exception as exc:
            overall = "degraded"
            db = ComponentHealth(
                status="error", last_checked=now, error=str(exc)
            )

        # Redis
        try:
            from app.infrastructure.redis_client import safe_redis_ping

            start = _time.monotonic()
            ok = await safe_redis_ping()
            if ok:
                redis = ComponentHealth(
                    status="healthy",
                    latency_ms=round((_time.monotonic() - start) * 1000, 2),
                    last_checked=now,
                )
            else:
                overall = "degraded"
                redis = ComponentHealth(
                    status="error", last_checked=now, error="Redis ping failed"
                )
        except Exception as exc:
            overall = "degraded"
            redis = ComponentHealth(
                status="error", last_checked=now, error=str(exc)
            )

        engines_payload = await admin_operations_service.check_engines(session)
        engines = engines_payload.get("engines") or []
        worker_status = "healthy"
        for e in engines:
            if e.get("status") not in ("running", "idle", "ok"):
                worker_status = "degraded"
                overall = "degraded"
                break
        workers = ComponentHealth(status=worker_status, last_checked=now)
        scheduler = ComponentHealth(status=worker_status, last_checked=now)
        check_engine = ComponentHealth(status=worker_status, last_checked=now)

        # Billing / email / storage — configuration presence checks
        from app.config import settings

        billing_ok = bool(getattr(settings, "PAYSTACK_SECRET_KEY", "") or "")
        billing = ComponentHealth(
            status="healthy" if billing_ok else "unknown",
            last_checked=now,
            message=None if billing_ok else "Billing provider not configured",
        )
        smtp_host = getattr(settings, "SMTP_HOST", "") or ""
        # localhost is the default dev value — treat as unknown in that case
        email_cfg = bool(smtp_host) and smtp_host not in ("localhost", "127.0.0.1")
        email = ComponentHealth(
            status="healthy" if email_cfg else "unknown",
            last_checked=now,
            message=None if email_cfg else "SMTP not configured for production",
        )
        storage_ok = bool(getattr(settings, "SUPABASE_S3_BUCKET", "") or "")
        storage = ComponentHealth(
            status="healthy" if storage_ok else "unknown",
            last_checked=now,
            message=None if storage_ok else "Object storage not configured",
        )

        return OperationsOverviewResponse(
            api=api,
            database=db,
            redis=redis,
            workers=workers,
            scheduler=scheduler,
            check_engine=check_engine,
            billing=billing,
            email=email,
            storage=storage,
            overall=overall,
            engines=engines,
            generated_at=now,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _derive_health(
        *,
        is_active: bool,
        last_activity_at: datetime | None,
        plan: str | None,
    ) -> str:
        if not is_active:
            return "inactive"
        if last_activity_at is None:
            return "unknown"
        age = _now() - (
            last_activity_at
            if last_activity_at.tzinfo
            else last_activity_at.replace(tzinfo=timezone.utc)
        )
        if age > timedelta(days=30) and plan and plan != "free":
            return "at_risk"
        if age > timedelta(days=60):
            return "churning"
        return "healthy"

    @staticmethod
    async def _count(session: AsyncSession, model) -> int:
        return int(
            (await session.execute(select(func.count()).select_from(model))).scalar()
            or 0
        )

    @staticmethod
    async def _count_where(session: AsyncSession, model, *conditions) -> int:
        q = select(func.count()).select_from(model)
        for c in conditions:
            q = q.where(c)
        return int((await session.execute(q)).scalar() or 0)

    @staticmethod
    async def _count_checks_since(session: AsyncSession, since: datetime) -> int:
        try:
            from app.modules.checks.models import CheckResult

            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(CheckResult)
                        .where(CheckResult.executed_at >= since)
                    )
                ).scalar()
                or 0
            )
        except Exception:
            return 0


admin_control_plane_service = AdminControlPlaneService()
