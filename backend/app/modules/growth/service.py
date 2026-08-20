from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.growth.schemas import (
    GrowthFunnelResponse,
    ReferralStatItem,
    TopVendorStat,
)

logger = logging.getLogger(__name__)

_PERIOD_DELTAS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


class GrowthService:
    """Aggregate growth and funnel analytics from across the platform."""

    async def get_funnel(
        self,
        session: AsyncSession,
        period: str = "30d",
    ) -> GrowthFunnelResponse:
        """Return a full growth funnel for the given time period."""
        delta = _PERIOD_DELTAS.get(period)
        if delta is None:
            from app.core.exceptions import ValidationException

            raise ValidationException(
                f"Invalid period '{period}'. Supported: {', '.join(_PERIOD_DELTAS)}"
            )
        since = datetime.now(timezone.utc) - delta

        badge_impressions = await self._count_badge_impressions(session, since)
        badge_clicks = await self._count_lead_captures(session, since, source="badge_click")
        vendor_page_views = await self._count_lead_captures(session, since, source="vendor_page")
        vendor_submissions = await self._count_vendor_submissions(session, since)
        evidence_gated_views = await self._count_lead_captures(session, since, source="evidence_gate")
        evidence_downloads = await self._count_evidence_downloads(session, since)
        evidence_conversions = await self._count_evidence_conversions(session, since)
        referral_signups = await self._count_referral_signups(session, since)
        total_new_users = await self._count_new_users(session, since)
        total_new_orgs = await self._count_new_orgs(session, since)

        conversion_rates: dict[str, float] = {}
        if badge_impressions > 0:
            conversion_rates["badge_to_click"] = round(badge_clicks / badge_impressions, 4)
        if vendor_page_views > 0:
            conversion_rates["view_to_submission"] = round(
                vendor_submissions / vendor_page_views, 4
            )
        if evidence_gated_views > 0:
            conversion_rates["evidence_view_to_download"] = round(
                evidence_downloads / evidence_gated_views, 4
            )
        if evidence_downloads > 0:
            conversion_rates["evidence_download_to_conversion"] = round(
                evidence_conversions / evidence_downloads, 4
            )
        if total_new_users > 0:
            conversion_rates["referral_rate"] = round(
                referral_signups / total_new_users, 4
            )

        return GrowthFunnelResponse(
            period=period,
            badge_impressions=badge_impressions,
            badge_clicks=badge_clicks,
            vendor_page_views=vendor_page_views,
            vendor_submissions=vendor_submissions,
            evidence_gated_views=evidence_gated_views,
            evidence_downloads=evidence_downloads,
            evidence_conversions=evidence_conversions,
            referral_signups=referral_signups,
            total_new_users=total_new_users,
            total_new_orgs=total_new_orgs,
            conversion_rates=conversion_rates,
        )

    async def get_top_vendors(
        self,
        session: AsyncSession,
        sort_by: str = "views",
        limit: int = 20,
    ) -> list[TopVendorStat]:
        """Return top vendors by various engagement metrics."""
        valid_sort = {"views", "badge_embeds", "submissions", "evidence_downloads"}
        if sort_by not in valid_sort:
            from app.core.exceptions import ValidationException

            raise ValidationException(
                f"Invalid sort_by '{sort_by}'. Supported: {', '.join(sorted(valid_sort))}"
            )
        return await self._aggregate_top_vendors(session, sort_by, limit)

    async def get_referral_stats(self, session: AsyncSession) -> dict:
        """Aggregate referral statistics across all referrers."""
        from app.modules.referrals.models import Referral, ReferralCode
        from app.modules.users.models import User

        stats: list[ReferralStatItem] = []

        stmt = (
            select(
                ReferralCode.user_id,
                func.count(Referral.id).label("total_referrals"),
                func.sum(
                    func.case(
                        (Referral.activated_at.is_not(None), 1),
                        else_=0,
                    )
                ).label("active_referrals"),
            )
            .select_from(ReferralCode)
            .join(Referral, ReferralCode.code == Referral.referral_code)
            .group_by(ReferralCode.user_id)
            .order_by(func.count(Referral.id).desc())
            .limit(50)
        )

        result = await session.execute(stmt)
        rows = result.all()

        for row in rows:
            user_id = row.user_id
            total = int(row.total_referrals)
            active = int(row.active_referrals) if row.active_referrals else 0

            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            display_name = user.full_name if user else "Unknown"

            conv_rate = round(active / total, 4) if total > 0 else 0.0

            stats.append(
                ReferralStatItem(
                    user_id=user_id,
                    display_name=display_name,
                    total_referrals=total,
                    active_referrals=active,
                    conversion_rate=conv_rate,
                )
            )

        total_referrals_all = sum(s.total_referrals for s in stats)
        total_active_all = sum(s.active_referrals for s in stats)

        return {
            "top_referrers": [s.model_dump() for s in stats],
            "summary": {
                "total_referrers": len(stats),
                "total_referrals": total_referrals_all,
                "total_active": total_active_all,
                "overall_conversion_rate": (
                    round(total_active_all / total_referrals_all, 4)
                    if total_referrals_all > 0
                    else 0.0
                ),
            },
        }

    # ------------------------------------------------------------------
    # Private helpers — raw SQLAlchemy queries against existing tables
    # ------------------------------------------------------------------

    @staticmethod
    async def _count_badge_impressions(session: AsyncSession, since: datetime) -> int:
        from app.modules.badges.models import BadgeImpression

        result = await session.execute(
            select(func.count()).select_from(BadgeImpression).where(
                BadgeImpression.created_at >= since
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_lead_captures(
        session: AsyncSession,
        since: datetime,
        source: str | None = None,
    ) -> int:
        from app.modules.evidence_gate.models import LeadCaptureEvent

        stmt = select(func.count()).select_from(LeadCaptureEvent).where(
            LeadCaptureEvent.created_at >= since
        )
        if source:
            stmt = stmt.where(LeadCaptureEvent.source == source)
        result = await session.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def _count_vendor_submissions(session: AsyncSession, since: datetime) -> int:
        from app.modules.vendor_submissions.models import VendorSubmission

        result = await session.execute(
            select(func.count()).select_from(VendorSubmission).where(
                VendorSubmission.created_at >= since
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_evidence_downloads(session: AsyncSession, since: datetime) -> int:
        from app.modules.evidence_gate.models import EvidenceGateToken

        result = await session.execute(
            select(func.count()).select_from(EvidenceGateToken).where(
                EvidenceGateToken.downloaded_at >= since
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_evidence_conversions(session: AsyncSession, since: datetime) -> int:
        from app.modules.evidence_gate.models import LeadCaptureEvent

        result = await session.execute(
            select(func.count()).select_from(LeadCaptureEvent).where(
                LeadCaptureEvent.created_at >= since,
                LeadCaptureEvent.converted_to_signup.is_(True),
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_referral_signups(session: AsyncSession, since: datetime) -> int:
        from app.modules.referrals.models import Referral

        result = await session.execute(
            select(func.count()).select_from(Referral).where(
                Referral.created_at >= since,
                Referral.activated_at.is_not(None),
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_new_users(session: AsyncSession, since: datetime) -> int:
        from app.modules.users.models import User

        result = await session.execute(
            select(func.count()).select_from(User).where(
                User.created_at >= since
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_new_orgs(session: AsyncSession, since: datetime) -> int:
        from app.modules.organizations.models import Organization

        result = await session.execute(
            select(func.count()).select_from(Organization).where(
                Organization.created_at >= since
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _aggregate_top_vendors(
        session: AsyncSession,
        sort_by: str,
        limit: int,
    ) -> list[TopVendorStat]:
        """Aggregate vendor engagement stats across multiple tables."""
        from app.modules.badges.models import BadgeImpression
        from app.modules.evidence_gate.models import (
            EvidenceGateToken,
            LeadCaptureEvent,
        )
        from app.modules.vendor_submissions.models import VendorSubmission

        vendors_result = await session.execute(
            select(VendorSubmission.vendor_name).distinct().limit(200)
        )
        vendor_names = [row[0] for row in vendors_result.all()]

        stats: list[TopVendorStat] = []

        for vname in vendor_names:
            badge_result = await session.execute(
                select(func.count()).select_from(BadgeImpression).where(
                    BadgeImpression.vendor_name == vname
                )
            )
            badge_embeds = badge_result.scalar() or 0

            view_result = await session.execute(
                select(func.count()).select_from(LeadCaptureEvent).where(
                    LeadCaptureEvent.vendor_name == vname,
                    LeadCaptureEvent.source == "vendor_page",
                )
            )
            views = view_result.scalar() or 0

            sub_result = await session.execute(
                select(func.count()).select_from(VendorSubmission).where(
                    VendorSubmission.vendor_name == vname
                )
            )
            submissions = sub_result.scalar() or 0

            dl_result = await session.execute(
                select(func.count())
                .select_from(EvidenceGateToken)
                .join(
                    LeadCaptureEvent,
                    EvidenceGateToken.email == LeadCaptureEvent.email,
                )
                .where(
                    LeadCaptureEvent.vendor_name == vname,
                    EvidenceGateToken.downloaded_at.is_not(None),
                )
            )
            evidence_downloads = dl_result.scalar() or 0

            stats.append(
                TopVendorStat(
                    vendor_name=vname,
                    views=views,
                    badge_embeds=badge_embeds,
                    submissions=submissions,
                    evidence_downloads=evidence_downloads,
                )
            )

        sort_key_map = {
            "views": lambda s: s.views,
            "badge_embeds": lambda s: s.badge_embeds,
            "submissions": lambda s: s.submissions,
            "evidence_downloads": lambda s: s.evidence_downloads,
        }
        stats.sort(key=sort_key_map[sort_by], reverse=True)
        return stats[:limit]


growth_service = GrowthService()
