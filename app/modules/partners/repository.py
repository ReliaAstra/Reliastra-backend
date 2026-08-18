"""Data access for the Partner Network.

Static-method repositories, matching the platform convention
(:mod:`app.modules.status_pages.repository`). Repositories never commit —
the request-scoped session (or the task runner) owns the transaction — and
they never contain business rules. All soft-deletable entities are filtered
on ``is_deleted`` here so that no caller can accidentally resurrect a
deleted row.

Every ownership-scoped read takes ``partner_id`` as a mandatory argument.
There is intentionally no "get by id" that skips the ownership filter for
partner-facing use; the admin repositories are separate and explicitly
named, which makes a cross-partner data leak a visible code change rather
than a forgotten ``where`` clause.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.partners.constants import (
    CommissionStatus,
    LEAD_OPEN_STATUSES,
    LedgerEntryType,
    PartnerStatus,
)
from app.modules.partners.models import (
    GeoIpCache,
    Partner,
    PartnerApplication,
    PartnerAttribution,
    PartnerCampaign,
    PartnerClaimEvidence,
    PartnerClickEvent,
    PartnerCommission,
    PartnerCommissionEvent,
    PartnerCustomerRelationship,
    PartnerDeploymentClaim,
    PartnerFraudFlag,
    PartnerGeoDaily,
    PartnerLead,
    PartnerPayout,
    PartnerPayoutAccount,
    PartnerPayoutItem,
    PartnerProgramContent,
    PartnerReferralLink,
    PartnerRiskAssessment,
    PartnerSettlement,
    PartnerTierHistory,
)


async def _count(session: AsyncSession, stmt: Select) -> int:
    """Total row count for a SELECT, ignoring its ordering/limits."""
    subq = stmt.order_by(None).subquery()
    result = await session.execute(select(func.count()).select_from(subq))
    return int(result.scalar_one())


# ═════════════════════════════ Partners ══════════════════════════════════


class PartnerRepository:
    """Partner accounts and applications."""

    @staticmethod
    async def get_by_id(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> Partner | None:
        result = await session.execute(
            select(Partner).where(
                Partner.id == partner_id, Partner.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_id(
        session: AsyncSession, user_id: uuid.UUID
    ) -> Partner | None:
        result = await session.execute(
            select(Partner).where(
                Partner.user_id == user_id, Partner.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        session: AsyncSession, partner_code: str
    ) -> Partner | None:
        """Case-insensitive lookup — partner codes are shared verbally and
        typed by hand, so ``/r/abc12345`` must resolve like ``/r/ABC12345``."""
        result = await session.execute(
            select(Partner).where(
                func.upper(Partner.partner_code) == partner_code.upper(),
                Partner.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Partner | None:
        result = await session.execute(
            select(Partner).where(
                func.lower(Partner.slug) == slug.lower(),
                Partner.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def code_exists(session: AsyncSession, partner_code: str) -> bool:
        result = await session.execute(
            select(Partner.id).where(
                func.upper(Partner.partner_code) == partner_code.upper()
            )
        )
        return result.first() is not None

    @staticmethod
    async def slug_exists(session: AsyncSession, slug: str) -> bool:
        result = await session.execute(
            select(Partner.id).where(func.lower(Partner.slug) == slug.lower())
        )
        return result.first() is not None

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        status: str | None = None,
        tier: str | None = None,
        partner_type: str | None = None,
        country_code: str | None = None,
        risk_band: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Partner], int]:
        stmt = select(Partner).where(Partner.is_deleted.is_(False))
        if status:
            stmt = stmt.where(Partner.status == status)
        if tier:
            stmt = stmt.where(Partner.tier == tier)
        if partner_type:
            stmt = stmt.where(Partner.partner_type == partner_type)
        if country_code:
            stmt = stmt.where(Partner.country_code == country_code.upper())
        if risk_band:
            stmt = stmt.where(Partner.risk_band == risk_band)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Partner.display_name).like(pattern),
                    func.lower(Partner.partner_code).like(pattern),
                    func.lower(Partner.contact_email).like(pattern),
                )
            )
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(Partner.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_public_directory(
        session: AsyncSession,
        *,
        country_code: str | None = None,
        partner_type: str | None = None,
        tier: str | None = None,
        expertise: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 24,
    ) -> tuple[list[Partner], int]:
        """Only opted-in, active partners appear in the public directory."""
        stmt = select(Partner).where(
            Partner.is_deleted.is_(False),
            Partner.is_publicly_listed.is_(True),
            Partner.status == PartnerStatus.ACTIVE.value,
        )
        if country_code:
            stmt = stmt.where(Partner.country_code == country_code.upper())
        if partner_type:
            stmt = stmt.where(Partner.partner_type == partner_type)
        if tier:
            stmt = stmt.where(Partner.tier == tier)
        if expertise:
            stmt = stmt.where(Partner.expertise.contains([expertise]))
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Partner.display_name).like(pattern),
                    func.lower(Partner.headline).like(pattern),
                )
            )
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(Partner.tier.desc(), Partner.display_name.asc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_active_ids(session: AsyncSession) -> list[uuid.UUID]:
        result = await session.execute(
            select(Partner.id).where(
                Partner.is_deleted.is_(False),
                Partner.status == PartnerStatus.ACTIVE.value,
            )
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def add_tier_history(
        session: AsyncSession, entry: PartnerTierHistory
    ) -> PartnerTierHistory:
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def list_tier_history(
        session: AsyncSession, partner_id: uuid.UUID, limit: int = 50
    ) -> list[PartnerTierHistory]:
        result = await session.execute(
            select(PartnerTierHistory)
            .where(PartnerTierHistory.partner_id == partner_id)
            .order_by(PartnerTierHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class PartnerApplicationRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, application_id: uuid.UUID
    ) -> PartnerApplication | None:
        result = await session.execute(
            select(PartnerApplication).where(PartnerApplication.id == application_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_owned(
        session: AsyncSession, application_id: uuid.UUID, user_id: uuid.UUID
    ) -> PartnerApplication | None:
        result = await session.execute(
            select(PartnerApplication).where(
                PartnerApplication.id == application_id,
                PartnerApplication.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_for_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> PartnerApplication | None:
        """An applicant may only have one in-flight application."""
        result = await session.execute(
            select(PartnerApplication)
            .where(
                PartnerApplication.user_id == user_id,
                PartnerApplication.status.in_(["submitted", "under_review"]),
            )
            .order_by(PartnerApplication.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> list[PartnerApplication]:
        result = await session.execute(
            select(PartnerApplication)
            .where(PartnerApplication.user_id == user_id)
            .order_by(PartnerApplication.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerApplication], int]:
        stmt = select(PartnerApplication)
        if status:
            stmt = stmt.where(PartnerApplication.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerApplication.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total


# ═══════════════════════ Campaigns & referral links ══════════════════════


class CampaignRepository:
    @staticmethod
    async def get_owned(
        session: AsyncSession, campaign_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerCampaign | None:
        """Ownership is part of the query, never a post-hoc check."""
        result = await session.execute(
            select(PartnerCampaign).where(
                PartnerCampaign.id == campaign_id,
                PartnerCampaign.partner_id == partner_id,
                PartnerCampaign.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        session: AsyncSession, partner_id: uuid.UUID, campaign_code: str
    ) -> PartnerCampaign | None:
        result = await session.execute(
            select(PartnerCampaign).where(
                PartnerCampaign.partner_id == partner_id,
                func.upper(PartnerCampaign.campaign_code) == campaign_code.upper(),
                PartnerCampaign.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerCampaign], int]:
        stmt = select(PartnerCampaign).where(
            PartnerCampaign.partner_id == partner_id,
            PartnerCampaign.is_deleted.is_(False),
        )
        if status:
            stmt = stmt.where(PartnerCampaign.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerCampaign.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def count_for_partner(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> int:
        result = await session.execute(
            select(func.count(PartnerCampaign.id)).where(
                PartnerCampaign.partner_id == partner_id,
                PartnerCampaign.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one())


class ReferralLinkRepository:
    @staticmethod
    async def get_owned(
        session: AsyncSession, link_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerReferralLink | None:
        result = await session.execute(
            select(PartnerReferralLink).where(
                PartnerReferralLink.id == link_id,
                PartnerReferralLink.partner_id == partner_id,
                PartnerReferralLink.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> PartnerReferralLink | None:
        result = await session.execute(
            select(PartnerReferralLink).where(
                PartnerReferralLink.partner_id == partner_id,
                PartnerReferralLink.is_default.is_(True),
                PartnerReferralLink.is_deleted.is_(False),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerReferralLink], int]:
        stmt = select(PartnerReferralLink).where(
            PartnerReferralLink.partner_id == partner_id,
            PartnerReferralLink.is_deleted.is_(False),
        )
        if campaign_id:
            stmt = stmt.where(PartnerReferralLink.campaign_id == campaign_id)
        if status:
            stmt = stmt.where(PartnerReferralLink.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(
                PartnerReferralLink.is_default.desc(),
                PartnerReferralLink.created_at.desc(),
            )
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def count_for_campaign(
        session: AsyncSession, campaign_id: uuid.UUID
    ) -> int:
        result = await session.execute(
            select(func.count(PartnerReferralLink.id)).where(
                PartnerReferralLink.campaign_id == campaign_id,
                PartnerReferralLink.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one())


# ═════════════════════ Clicks, attribution, customers ════════════════════


class ClickRepository:
    @staticmethod
    async def add(session: AsyncSession, event: PartnerClickEvent) -> PartnerClickEvent:
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def recent_duplicate_exists(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        visitor_id: str,
        since: datetime,
        campaign_id: uuid.UUID | None = None,
    ) -> bool:
        """Has this visitor already clicked this link inside the dedup window?"""
        stmt = select(PartnerClickEvent.id).where(
            PartnerClickEvent.partner_id == partner_id,
            PartnerClickEvent.visitor_id == visitor_id,
            PartnerClickEvent.created_at >= since,
        )
        if campaign_id is not None:
            stmt = stmt.where(PartnerClickEvent.campaign_id == campaign_id)
        else:
            stmt = stmt.where(PartnerClickEvent.campaign_id.is_(None))
        result = await session.execute(stmt.limit(1))
        return result.first() is not None

    @staticmethod
    async def count_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        since: datetime | None = None,
        include_bots: bool = False,
    ) -> int:
        stmt = select(func.count(PartnerClickEvent.id)).where(
            PartnerClickEvent.partner_id == partner_id,
            PartnerClickEvent.is_duplicate.is_(False),
        )
        if not include_bots:
            stmt = stmt.where(PartnerClickEvent.is_bot.is_(False))
        if since:
            stmt = stmt.where(PartnerClickEvent.created_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one())

    @staticmethod
    async def daily_series(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> list[tuple[date, int, int]]:
        """(day, clicks, unique visitors) for a partner over a window."""
        day = func.date_trunc("day", PartnerClickEvent.created_at).label("day")
        stmt = (
            select(
                day,
                func.count(PartnerClickEvent.id),
                func.count(func.distinct(PartnerClickEvent.visitor_id)),
            )
            .where(
                PartnerClickEvent.partner_id == partner_id,
                PartnerClickEvent.created_at >= start,
                PartnerClickEvent.created_at < end,
                PartnerClickEvent.is_duplicate.is_(False),
                PartnerClickEvent.is_bot.is_(False),
            )
            .group_by(day)
            .order_by(day)
        )
        result = await session.execute(stmt)
        return [(row[0].date(), int(row[1]), int(row[2])) for row in result.all()]

    @staticmethod
    async def country_breakdown(
        session: AsyncSession,
        *,
        start: datetime,
        end: datetime,
        partner_id: uuid.UUID | None = None,
    ) -> list[tuple[str | None, str | None, int, int]]:
        stmt = (
            select(
                PartnerClickEvent.country_code,
                func.max(PartnerClickEvent.country_name),
                func.count(PartnerClickEvent.id),
                func.count(func.distinct(PartnerClickEvent.visitor_id)),
            )
            .where(
                PartnerClickEvent.created_at >= start,
                PartnerClickEvent.created_at < end,
                PartnerClickEvent.is_duplicate.is_(False),
                PartnerClickEvent.is_bot.is_(False),
            )
            .group_by(PartnerClickEvent.country_code)
            .order_by(func.count(PartnerClickEvent.id).desc())
        )
        if partner_id:
            stmt = stmt.where(PartnerClickEvent.partner_id == partner_id)
        result = await session.execute(stmt)
        return [(r[0], r[1], int(r[2]), int(r[3])) for r in result.all()]

    @staticmethod
    async def campaign_breakdown(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> list[tuple[uuid.UUID | None, int, int]]:
        stmt = (
            select(
                PartnerClickEvent.campaign_id,
                func.count(PartnerClickEvent.id),
                func.count(func.distinct(PartnerClickEvent.visitor_id)),
            )
            .where(
                PartnerClickEvent.partner_id == partner_id,
                PartnerClickEvent.created_at >= start,
                PartnerClickEvent.created_at < end,
                PartnerClickEvent.is_duplicate.is_(False),
                PartnerClickEvent.is_bot.is_(False),
            )
            .group_by(PartnerClickEvent.campaign_id)
        )
        result = await session.execute(stmt)
        return [(r[0], int(r[1]), int(r[2])) for r in result.all()]


class AttributionRepository:
    @staticmethod
    async def add(
        session: AsyncSession, attribution: PartnerAttribution
    ) -> PartnerAttribution:
        session.add(attribution)
        await session.flush()
        return attribution

    @staticmethod
    async def get_active_for_visitor(
        session: AsyncSession, visitor_id: str, *, now: datetime
    ) -> PartnerAttribution | None:
        """The last eligible touch for an anonymous visitor.

        "Eligible" = active status and still inside the attribution window.
        Ordering by ``occurred_at DESC`` is what makes this last-touch.
        """
        result = await session.execute(
            select(PartnerAttribution)
            .where(
                PartnerAttribution.visitor_id == visitor_id,
                PartnerAttribution.user_id.is_(None),
                PartnerAttribution.status == "active",
                PartnerAttribution.expires_at > now,
            )
            .order_by(PartnerAttribution.occurred_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def get_active_for_user(
        session: AsyncSession, user_id: uuid.UUID
    ) -> PartnerAttribution | None:
        result = await session.execute(
            select(PartnerAttribution)
            .where(
                PartnerAttribution.user_id == user_id,
                PartnerAttribution.status == "active",
            )
            .order_by(PartnerAttribution.occurred_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_visitor(
        session: AsyncSession, visitor_id: str, limit: int = 50
    ) -> list[PartnerAttribution]:
        """Full touch history — the basis for future multi-touch models."""
        result = await session.execute(
            select(PartnerAttribution)
            .where(PartnerAttribution.visitor_id == visitor_id)
            .order_by(PartnerAttribution.occurred_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def max_position_for_visitor(
        session: AsyncSession, visitor_id: str
    ) -> int:
        result = await session.execute(
            select(func.coalesce(func.max(PartnerAttribution.position), 0)).where(
                PartnerAttribution.visitor_id == visitor_id
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def expire_stale(
        session: AsyncSession, *, now: datetime, limit: int = 5000
    ) -> list[PartnerAttribution]:
        result = await session.execute(
            select(PartnerAttribution)
            .where(
                PartnerAttribution.status == "active",
                PartnerAttribution.expires_at <= now,
                PartnerAttribution.converted_at.is_(None),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def supersede_active_for_visitor(
        session: AsyncSession, visitor_id: str, *, exclude_id: uuid.UUID | None = None
    ) -> list[PartnerAttribution]:
        """Return prior active touches so the caller can mark them superseded."""
        stmt = select(PartnerAttribution).where(
            PartnerAttribution.visitor_id == visitor_id,
            PartnerAttribution.status == "active",
            PartnerAttribution.converted_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(PartnerAttribution.id != exclude_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_signups(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(PartnerAttribution.id)).where(
            PartnerAttribution.partner_id == partner_id,
            PartnerAttribution.user_id.isnot(None),
        )
        if since:
            stmt = stmt.where(PartnerAttribution.occurred_at >= since)
        result = await session.execute(stmt)
        return int(result.scalar_one())


class RelationshipRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, relationship_id: uuid.UUID
    ) -> PartnerCustomerRelationship | None:
        result = await session.execute(
            select(PartnerCustomerRelationship).where(
                PartnerCustomerRelationship.id == relationship_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_owned(
        session: AsyncSession, relationship_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerCustomerRelationship | None:
        result = await session.execute(
            select(PartnerCustomerRelationship).where(
                PartnerCustomerRelationship.id == relationship_id,
                PartnerCustomerRelationship.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_org_and_method(
        session: AsyncSession,
        organization_id: uuid.UUID,
        partner_id: uuid.UUID,
        earning_method: str,
    ) -> PartnerCustomerRelationship | None:
        result = await session.execute(
            select(PartnerCustomerRelationship).where(
                PartnerCustomerRelationship.organization_id == organization_id,
                PartnerCustomerRelationship.partner_id == partner_id,
                PartnerCustomerRelationship.earning_method == earning_method,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_for_org(
        session: AsyncSession, organization_id: uuid.UUID
    ) -> list[PartnerCustomerRelationship]:
        """Every partner with a live claim on this organisation's revenue."""
        result = await session.execute(
            select(PartnerCustomerRelationship)
            .where(
                PartnerCustomerRelationship.organization_id == organization_id,
                PartnerCustomerRelationship.status == "active",
            )
            .order_by(PartnerCustomerRelationship.started_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        earning_method: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerCustomerRelationship], int]:
        stmt = select(PartnerCustomerRelationship).where(
            PartnerCustomerRelationship.partner_id == partner_id
        )
        if status:
            stmt = stmt.where(PartnerCustomerRelationship.status == status)
        if earning_method:
            stmt = stmt.where(
                PartnerCustomerRelationship.earning_method == earning_method
            )
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerCustomerRelationship.started_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def count_active(session: AsyncSession, partner_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.count(PartnerCustomerRelationship.id)).where(
                PartnerCustomerRelationship.partner_id == partner_id,
                PartnerCustomerRelationship.status == "active",
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def list_expiring(
        session: AsyncSession, *, now: datetime, limit: int = 1000
    ) -> list[PartnerCustomerRelationship]:
        result = await session.execute(
            select(PartnerCustomerRelationship)
            .where(
                PartnerCustomerRelationship.status == "active",
                PartnerCustomerRelationship.eligible_until.isnot(None),
                PartnerCustomerRelationship.eligible_until <= now,
            )
            .limit(limit)
        )
        return list(result.scalars().all())


# ═══════════════════════════ Commission ledger ═══════════════════════════


class CommissionRepository:
    """Append-only ledger access.

    Note the absence of any ``delete`` or bulk ``update`` helper: financial
    history is never removed or silently rewritten. Status changes go
    through the service layer, which also writes the audit event.
    """

    @staticmethod
    async def get_by_id(
        session: AsyncSession, commission_id: uuid.UUID
    ) -> PartnerCommission | None:
        result = await session.execute(
            select(PartnerCommission).where(PartnerCommission.id == commission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_owned(
        session: AsyncSession, commission_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerCommission | None:
        result = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.id == commission_id,
                PartnerCommission.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        entry_type: str,
        idempotency_key: str,
    ) -> PartnerCommission | None:
        """The read half of commission idempotency (the DB unique constraint
        is the authoritative half)."""
        result = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.entry_type == entry_type,
                PartnerCommission.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def add(
        session: AsyncSession, commission: PartnerCommission
    ) -> PartnerCommission:
        session.add(commission)
        await session.flush()
        return commission

    @staticmethod
    async def add_event(
        session: AsyncSession, event: PartnerCommissionEvent
    ) -> PartnerCommissionEvent:
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_events(
        session: AsyncSession, commission_id: uuid.UUID
    ) -> list[PartnerCommissionEvent]:
        result = await session.execute(
            select(PartnerCommissionEvent)
            .where(PartnerCommissionEvent.commission_id == commission_id)
            .order_by(PartnerCommissionEvent.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        entry_type: str | None = None,
        period_month: str | None = None,
        organization_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerCommission], int]:
        stmt = select(PartnerCommission).where(
            PartnerCommission.partner_id == partner_id
        )
        if status:
            stmt = stmt.where(PartnerCommission.status == status)
        if entry_type:
            stmt = stmt.where(PartnerCommission.entry_type == entry_type)
        if period_month:
            stmt = stmt.where(PartnerCommission.period_month == period_month)
        if organization_id:
            stmt = stmt.where(PartnerCommission.organization_id == organization_id)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerCommission.earned_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID | None = None,
        status: str | None = None,
        period_month: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerCommission], int]:
        stmt = select(PartnerCommission)
        if partner_id:
            stmt = stmt.where(PartnerCommission.partner_id == partner_id)
        if status:
            stmt = stmt.where(PartnerCommission.status == status)
        if period_month:
            stmt = stmt.where(PartnerCommission.period_month == period_month)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerCommission.earned_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def balance_by_status(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> dict[str, int]:
        """Authoritative balances, summed straight from the ledger.

        Cached aggregates on ``partners`` exist for listing performance, but
        every number a partner is shown as money comes from here.
        """
        result = await session.execute(
            select(
                PartnerCommission.status,
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
            )
            .where(PartnerCommission.partner_id == partner_id)
            .group_by(PartnerCommission.status)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    @staticmethod
    async def payable_total(
        session: AsyncSession, partner_id: uuid.UUID, currency: str
    ) -> int:
        result = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.amount_minor), 0)).where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.status == CommissionStatus.PAYABLE.value,
                PartnerCommission.currency == currency,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def list_payable(
        session: AsyncSession,
        partner_id: uuid.UUID,
        currency: str,
        *,
        limit: int = 1000,
    ) -> list[PartnerCommission]:
        """Payable rows locked for update, so two concurrent payout requests
        cannot both claim the same commission."""
        result = await session.execute(
            select(PartnerCommission)
            .where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.status == CommissionStatus.PAYABLE.value,
                PartnerCommission.currency == currency,
                PartnerCommission.payout_id.is_(None),
            )
            .order_by(PartnerCommission.earned_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_due_for_release(
        session: AsyncSession, *, now: datetime, limit: int = 1000
    ) -> list[PartnerCommission]:
        """Pending commissions whose holding period has elapsed."""
        result = await session.execute(
            select(PartnerCommission)
            .where(
                PartnerCommission.status == CommissionStatus.PENDING.value,
                PartnerCommission.payable_at.isnot(None),
                PartnerCommission.payable_at <= now,
            )
            .order_by(PartnerCommission.payable_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_source(
        session: AsyncSession,
        *,
        source_reference: str,
        entry_type: str = LedgerEntryType.COMMISSION.value,
    ) -> list[PartnerCommission]:
        """All commissions generated by one payment — used when that payment
        is later refunded or charged back."""
        result = await session.execute(
            select(PartnerCommission).where(
                PartnerCommission.source_reference == source_reference,
                PartnerCommission.entry_type == entry_type,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_relationship(
        session: AsyncSession,
        relationship_id: uuid.UUID,
        *,
        statuses: list[str] | None = None,
    ) -> list[PartnerCommission]:
        stmt = select(PartnerCommission).where(
            PartnerCommission.relationship_id == relationship_id
        )
        if statuses:
            stmt = stmt.where(PartnerCommission.status.in_(statuses))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def applied_bps_for_payment(
        session: AsyncSession, *, source_reference: str
    ) -> int:
        """Total bps already committed against one payment.

        Feeds the global 50% ceiling when multiple partners have a claim on
        the same customer.
        """
        result = await session.execute(
            select(func.coalesce(func.sum(PartnerCommission.rate_bps), 0)).where(
                PartnerCommission.source_reference == source_reference,
                PartnerCommission.entry_type == LedgerEntryType.COMMISSION.value,
                PartnerCommission.status != CommissionStatus.REVERSED.value,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def period_totals(
        session: AsyncSession, partner_id: uuid.UUID, period_month: str
    ) -> list[tuple[str, int, int, int]]:
        """(entry_type, sum(amount), count, sum(source)) for a settlement."""
        result = await session.execute(
            select(
                PartnerCommission.entry_type,
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.source_amount_minor), 0),
            )
            .where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.period_month == period_month,
            )
            .group_by(PartnerCommission.entry_type)
        )
        return [(r[0], int(r[1]), int(r[2]), int(r[3])) for r in result.all()]

    @staticmethod
    async def partners_with_activity_in_period(
        session: AsyncSession, period_month: str
    ) -> list[uuid.UUID]:
        result = await session.execute(
            select(PartnerCommission.partner_id)
            .where(PartnerCommission.period_month == period_month)
            .group_by(PartnerCommission.partner_id)
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def next_release_at(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> datetime | None:
        result = await session.execute(
            select(func.min(PartnerCommission.payable_at)).where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.status == CommissionStatus.PENDING.value,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def daily_series(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> list[tuple[date, int, int, int]]:
        """(day, conversions, revenue, commission)."""
        day = func.date_trunc("day", PartnerCommission.earned_at).label("day")
        result = await session.execute(
            select(
                day,
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.source_amount_minor), 0),
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
            )
            .where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.earned_at >= start,
                PartnerCommission.earned_at < end,
                PartnerCommission.entry_type == LedgerEntryType.COMMISSION.value,
            )
            .group_by(day)
            .order_by(day)
        )
        return [
            (r[0].date(), int(r[1]), int(r[2]), int(r[3])) for r in result.all()
        ]

    @staticmethod
    async def campaign_revenue(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> list[tuple[uuid.UUID | None, int, int, int]]:
        result = await session.execute(
            select(
                PartnerCommission.campaign_id,
                func.count(PartnerCommission.id),
                func.coalesce(func.sum(PartnerCommission.source_amount_minor), 0),
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
            )
            .where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.earned_at >= start,
                PartnerCommission.earned_at < end,
            )
            .group_by(PartnerCommission.campaign_id)
        )
        return [(r[0], int(r[1]), int(r[2]), int(r[3])) for r in result.all()]

    @staticmethod
    async def lifetime_totals(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> tuple[int, int]:
        """(lifetime revenue, lifetime net commission) from the ledger."""
        result = await session.execute(
            select(
                func.coalesce(func.sum(PartnerCommission.source_amount_minor), 0),
                func.coalesce(func.sum(PartnerCommission.amount_minor), 0),
            ).where(
                PartnerCommission.partner_id == partner_id,
                PartnerCommission.status != CommissionStatus.REVERSED.value,
            )
        )
        row = result.one()
        return int(row[0]), int(row[1])


class SettlementRepository:
    @staticmethod
    async def get(
        session: AsyncSession, partner_id: uuid.UUID, period_month: str
    ) -> PartnerSettlement | None:
        result = await session.execute(
            select(PartnerSettlement).where(
                PartnerSettlement.partner_id == partner_id,
                PartnerSettlement.period_month == period_month,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def add(
        session: AsyncSession, settlement: PartnerSettlement
    ) -> PartnerSettlement:
        session.add(settlement)
        await session.flush()
        return settlement

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        page: int = 1,
        size: int = 24,
    ) -> tuple[list[PartnerSettlement], int]:
        stmt = select(PartnerSettlement).where(
            PartnerSettlement.partner_id == partner_id
        )
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerSettlement.period_month.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        period_month: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerSettlement], int]:
        stmt = select(PartnerSettlement)
        if period_month:
            stmt = stmt.where(PartnerSettlement.period_month == period_month)
        if status:
            stmt = stmt.where(PartnerSettlement.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerSettlement.period_month.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total


# ══════════════════════════════ Payouts ══════════════════════════════════


class PayoutRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, payout_id: uuid.UUID
    ) -> PartnerPayout | None:
        result = await session.execute(
            select(PartnerPayout).where(PartnerPayout.id == payout_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_owned(
        session: AsyncSession, payout_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerPayout | None:
        result = await session.execute(
            select(PartnerPayout).where(
                PartnerPayout.id == payout_id,
                PartnerPayout.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession, partner_id: uuid.UUID, idempotency_key: str
    ) -> PartnerPayout | None:
        result = await session.execute(
            select(PartnerPayout).where(
                PartnerPayout.partner_id == partner_id,
                PartnerPayout.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_for_partner(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> PartnerPayout | None:
        """A partner may only have one payout in flight at a time."""
        result = await session.execute(
            select(PartnerPayout)
            .where(
                PartnerPayout.partner_id == partner_id,
                PartnerPayout.status.in_(["requested", "approved", "processing"]),
            )
            .order_by(PartnerPayout.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def add(session: AsyncSession, payout: PartnerPayout) -> PartnerPayout:
        session.add(payout)
        await session.flush()
        return payout

    @staticmethod
    async def add_item(
        session: AsyncSession, item: PartnerPayoutItem
    ) -> PartnerPayoutItem:
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def list_items(
        session: AsyncSession, payout_id: uuid.UUID
    ) -> list[PartnerPayoutItem]:
        result = await session.execute(
            select(PartnerPayoutItem).where(PartnerPayoutItem.payout_id == payout_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerPayout], int]:
        stmt = select(PartnerPayout).where(PartnerPayout.partner_id == partner_id)
        if status:
            stmt = stmt.where(PartnerPayout.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerPayout.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        status: str | None = None,
        partner_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerPayout], int]:
        stmt = select(PartnerPayout)
        if status:
            stmt = stmt.where(PartnerPayout.status == status)
        if partner_id:
            stmt = stmt.where(PartnerPayout.partner_id == partner_id)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerPayout.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def reference_exists(session: AsyncSession, reference: str) -> bool:
        result = await session.execute(
            select(PartnerPayout.id).where(PartnerPayout.reference == reference)
        )
        return result.first() is not None


class PayoutAccountRepository:
    @staticmethod
    async def get_owned(
        session: AsyncSession, account_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerPayoutAccount | None:
        result = await session.execute(
            select(PartnerPayoutAccount).where(
                PartnerPayoutAccount.id == account_id,
                PartnerPayoutAccount.partner_id == partner_id,
                PartnerPayoutAccount.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_default(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> PartnerPayoutAccount | None:
        result = await session.execute(
            select(PartnerPayoutAccount)
            .where(
                PartnerPayoutAccount.partner_id == partner_id,
                PartnerPayoutAccount.is_default.is_(True),
                PartnerPayoutAccount.is_deleted.is_(False),
            )
            .order_by(PartnerPayoutAccount.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_partner(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> list[PartnerPayoutAccount]:
        result = await session.execute(
            select(PartnerPayoutAccount)
            .where(
                PartnerPayoutAccount.partner_id == partner_id,
                PartnerPayoutAccount.is_deleted.is_(False),
            )
            .order_by(
                PartnerPayoutAccount.is_default.desc(),
                PartnerPayoutAccount.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def clear_defaults(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> None:
        for account in await PayoutAccountRepository.list_for_partner(
            session, partner_id
        ):
            account.is_default = False
        await session.flush()


# ═══════════════════════════ Leads & claims ══════════════════════════════


class LeadRepository:
    @staticmethod
    async def get_owned(
        session: AsyncSession, lead_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerLead | None:
        result = await session.execute(
            select(PartnerLead).where(
                PartnerLead.id == lead_id,
                PartnerLead.partner_id == partner_id,
                PartnerLead.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, lead_id: uuid.UUID
    ) -> PartnerLead | None:
        result = await session.execute(
            select(PartnerLead).where(
                PartnerLead.id == lead_id, PartnerLead.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_open_by_email_hash(
        session: AsyncSession, email_hash: str, *, now: datetime
    ) -> PartnerLead | None:
        """Duplicate/exclusivity check across ALL partners.

        Returns the row without exposing it to the caller's partner — the
        service only uses its existence to reject a duplicate submission.
        """
        result = await session.execute(
            select(PartnerLead)
            .where(
                PartnerLead.contact_email_hash == email_hash,
                PartnerLead.is_deleted.is_(False),
                PartnerLead.status.in_(list(LEAD_OPEN_STATUSES)),
                or_(
                    PartnerLead.exclusive_until.is_(None),
                    PartnerLead.exclusive_until > now,
                ),
            )
            .order_by(PartnerLead.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerLead], int]:
        stmt = select(PartnerLead).where(
            PartnerLead.partner_id == partner_id,
            PartnerLead.is_deleted.is_(False),
        )
        if status:
            stmt = stmt.where(PartnerLead.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerLead.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        status: str | None = None,
        partner_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerLead], int]:
        stmt = select(PartnerLead).where(PartnerLead.is_deleted.is_(False))
        if status:
            stmt = stmt.where(PartnerLead.status == status)
        if partner_id:
            stmt = stmt.where(PartnerLead.partner_id == partner_id)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerLead.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def count_open(session: AsyncSession, partner_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.count(PartnerLead.id)).where(
                PartnerLead.partner_id == partner_id,
                PartnerLead.is_deleted.is_(False),
                PartnerLead.status.in_(list(LEAD_OPEN_STATUSES)),
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def list_stale(
        session: AsyncSession, *, cutoff: datetime, limit: int = 500
    ) -> list[PartnerLead]:
        result = await session.execute(
            select(PartnerLead)
            .where(
                PartnerLead.is_deleted.is_(False),
                PartnerLead.status.in_(list(LEAD_OPEN_STATUSES)),
                PartnerLead.created_at < cutoff,
            )
            .limit(limit)
        )
        return list(result.scalars().all())


class ClaimRepository:
    @staticmethod
    async def get_owned(
        session: AsyncSession, claim_id: uuid.UUID, partner_id: uuid.UUID
    ) -> PartnerDeploymentClaim | None:
        result = await session.execute(
            select(PartnerDeploymentClaim).where(
                PartnerDeploymentClaim.id == claim_id,
                PartnerDeploymentClaim.partner_id == partner_id,
                PartnerDeploymentClaim.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, claim_id: uuid.UUID
    ) -> PartnerDeploymentClaim | None:
        result = await session.execute(
            select(PartnerDeploymentClaim).where(
                PartnerDeploymentClaim.id == claim_id,
                PartnerDeploymentClaim.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_partner(
        session: AsyncSession,
        partner_id: uuid.UUID,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerDeploymentClaim], int]:
        stmt = select(PartnerDeploymentClaim).where(
            PartnerDeploymentClaim.partner_id == partner_id,
            PartnerDeploymentClaim.is_deleted.is_(False),
        )
        if status:
            stmt = stmt.where(PartnerDeploymentClaim.status == status)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerDeploymentClaim.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def list_admin(
        session: AsyncSession,
        *,
        status: str | None = None,
        partner_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerDeploymentClaim], int]:
        stmt = select(PartnerDeploymentClaim).where(
            PartnerDeploymentClaim.is_deleted.is_(False)
        )
        if status:
            stmt = stmt.where(PartnerDeploymentClaim.status == status)
        if partner_id:
            stmt = stmt.where(PartnerDeploymentClaim.partner_id == partner_id)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerDeploymentClaim.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def count_pending(session: AsyncSession, partner_id: uuid.UUID) -> int:
        result = await session.execute(
            select(func.count(PartnerDeploymentClaim.id)).where(
                PartnerDeploymentClaim.partner_id == partner_id,
                PartnerDeploymentClaim.is_deleted.is_(False),
                PartnerDeploymentClaim.status.in_(["submitted", "under_review"]),
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def add_evidence(
        session: AsyncSession, evidence: PartnerClaimEvidence
    ) -> PartnerClaimEvidence:
        session.add(evidence)
        await session.flush()
        return evidence

    @staticmethod
    async def list_evidence(
        session: AsyncSession, claim_id: uuid.UUID
    ) -> list[PartnerClaimEvidence]:
        result = await session.execute(
            select(PartnerClaimEvidence)
            .where(PartnerClaimEvidence.claim_id == claim_id)
            .order_by(PartnerClaimEvidence.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_evidence_for_claims(
        session: AsyncSession, claim_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[PartnerClaimEvidence]]:
        """Batched fetch — avoids an N+1 when listing claims."""
        if not claim_ids:
            return {}
        result = await session.execute(
            select(PartnerClaimEvidence)
            .where(PartnerClaimEvidence.claim_id.in_(claim_ids))
            .order_by(PartnerClaimEvidence.created_at.asc())
        )
        grouped: dict[uuid.UUID, list[PartnerClaimEvidence]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.claim_id, []).append(row)
        return grouped


# ═══════════════════════════════ Fraud ═══════════════════════════════════


class FraudRepository:
    @staticmethod
    async def add_assessment(
        session: AsyncSession, assessment: PartnerRiskAssessment
    ) -> PartnerRiskAssessment:
        session.add(assessment)
        await session.flush()
        return assessment

    @staticmethod
    async def latest_assessment(
        session: AsyncSession, partner_id: uuid.UUID
    ) -> PartnerRiskAssessment | None:
        result = await session.execute(
            select(PartnerRiskAssessment)
            .where(PartnerRiskAssessment.partner_id == partner_id)
            .order_by(PartnerRiskAssessment.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def list_assessments(
        session: AsyncSession, partner_id: uuid.UUID, limit: int = 50
    ) -> list[PartnerRiskAssessment]:
        result = await session.execute(
            select(PartnerRiskAssessment)
            .where(PartnerRiskAssessment.partner_id == partner_id)
            .order_by(PartnerRiskAssessment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_flag(
        session: AsyncSession, flag: PartnerFraudFlag
    ) -> PartnerFraudFlag:
        session.add(flag)
        await session.flush()
        return flag

    @staticmethod
    async def get_flag(
        session: AsyncSession, flag_id: uuid.UUID
    ) -> PartnerFraudFlag | None:
        result = await session.execute(
            select(PartnerFraudFlag).where(PartnerFraudFlag.id == flag_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_flag(
        session: AsyncSession, partner_id: uuid.UUID, signal: str
    ) -> PartnerFraudFlag | None:
        """Prevents the fraud job from re-raising the same open flag."""
        result = await session.execute(
            select(PartnerFraudFlag)
            .where(
                PartnerFraudFlag.partner_id == partner_id,
                PartnerFraudFlag.signal == signal,
                PartnerFraudFlag.status.in_(["open", "investigating"]),
            )
            .order_by(PartnerFraudFlag.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def list_flags(
        session: AsyncSession,
        *,
        status: str | None = None,
        partner_id: uuid.UUID | None = None,
        severity: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PartnerFraudFlag], int]:
        stmt = select(PartnerFraudFlag)
        if status:
            stmt = stmt.where(PartnerFraudFlag.status == status)
        if partner_id:
            stmt = stmt.where(PartnerFraudFlag.partner_id == partner_id)
        if severity:
            stmt = stmt.where(PartnerFraudFlag.severity == severity)
        total = await _count(session, stmt)
        stmt = (
            stmt.order_by(PartnerFraudFlag.created_at.desc())
            .offset(max(0, (page - 1) * size))
            .limit(size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total


# ════════════════════════════════ Geo ════════════════════════════════════


class GeoRepository:
    @staticmethod
    async def get_cached(
        session: AsyncSession, ip_hash: str
    ) -> GeoIpCache | None:
        result = await session.execute(
            select(GeoIpCache).where(GeoIpCache.ip_hash == ip_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_cached(
        session: AsyncSession, entry: GeoIpCache
    ) -> GeoIpCache:
        existing = await GeoRepository.get_cached(session, entry.ip_hash)
        if existing:
            existing.country_code = entry.country_code
            existing.country_name = entry.country_name
            existing.source = entry.source
            existing.looked_up_at = entry.looked_up_at
            await session.flush()
            return existing
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def cache_stats(session: AsyncSession) -> tuple[int, int, int]:
        """(total cached, distinct resolved countries, unresolved rows)."""
        result = await session.execute(
            select(
                func.count(GeoIpCache.id),
                func.count(func.distinct(GeoIpCache.country_code)),
                func.count(GeoIpCache.id).filter(GeoIpCache.country_code.is_(None)),
            )
        )
        row = result.one()
        return int(row[0]), int(row[1]), int(row[2])

    @staticmethod
    async def upsert_daily(
        session: AsyncSession,
        *,
        day: date,
        country_code: str,
        partner_id: uuid.UUID | None,
        country_name: str | None,
        click_count: int,
        unique_visitor_count: int,
        signup_count: int,
        conversion_count: int,
        revenue_minor: int,
        commission_minor: int,
        currency: str,
    ) -> PartnerGeoDaily:
        result = await session.execute(
            select(PartnerGeoDaily).where(
                PartnerGeoDaily.day == day,
                PartnerGeoDaily.country_code == country_code,
                (
                    PartnerGeoDaily.partner_id == partner_id
                    if partner_id is not None
                    else PartnerGeoDaily.partner_id.is_(None)
                ),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = PartnerGeoDaily(
                day=day, country_code=country_code, partner_id=partner_id
            )
            session.add(row)
        row.country_name = country_name
        row.click_count = click_count
        row.unique_visitor_count = unique_visitor_count
        row.signup_count = signup_count
        row.conversion_count = conversion_count
        row.revenue_minor = revenue_minor
        row.commission_minor = commission_minor
        row.currency = currency
        await session.flush()
        return row

    @staticmethod
    async def country_totals(
        session: AsyncSession,
        *,
        start: date,
        end: date,
        partner_id: uuid.UUID | None = None,
    ) -> list[tuple[str, str | None, int, int, int, int, int, int]]:
        conditions = [PartnerGeoDaily.day >= start, PartnerGeoDaily.day <= end]
        if partner_id is not None:
            conditions.append(PartnerGeoDaily.partner_id == partner_id)
        else:
            conditions.append(PartnerGeoDaily.partner_id.is_(None))
        result = await session.execute(
            select(
                PartnerGeoDaily.country_code,
                func.max(PartnerGeoDaily.country_name),
                func.coalesce(func.sum(PartnerGeoDaily.click_count), 0),
                func.coalesce(func.sum(PartnerGeoDaily.unique_visitor_count), 0),
                func.coalesce(func.sum(PartnerGeoDaily.signup_count), 0),
                func.coalesce(func.sum(PartnerGeoDaily.conversion_count), 0),
                func.coalesce(func.sum(PartnerGeoDaily.revenue_minor), 0),
                func.coalesce(func.sum(PartnerGeoDaily.commission_minor), 0),
            )
            .where(and_(*conditions))
            .group_by(PartnerGeoDaily.country_code)
            .order_by(func.sum(PartnerGeoDaily.click_count).desc())
        )
        return [
            (
                r[0],
                r[1],
                int(r[2]),
                int(r[3]),
                int(r[4]),
                int(r[5]),
                int(r[6]),
                int(r[7]),
            )
            for r in result.all()
        ]


# ═════════════════════════ Program content ═══════════════════════════════


class ProgramContentRepository:
    @staticmethod
    async def list_published(
        session: AsyncSession, *, locale: str = "en", section: str | None = None
    ) -> list[PartnerProgramContent]:
        stmt = select(PartnerProgramContent).where(
            PartnerProgramContent.is_published.is_(True),
            PartnerProgramContent.locale == locale,
        )
        if section:
            stmt = stmt.where(PartnerProgramContent.section == section)
        result = await session.execute(
            stmt.order_by(
                PartnerProgramContent.section.asc(),
                PartnerProgramContent.sort_order.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get(
        session: AsyncSession, key: str, locale: str = "en"
    ) -> PartnerProgramContent | None:
        result = await session.execute(
            select(PartnerProgramContent).where(
                PartnerProgramContent.key == key,
                PartnerProgramContent.locale == locale,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        session: AsyncSession,
        *,
        key: str,
        locale: str,
        section: str,
        title: str | None,
        body: str | None,
        payload: dict | None,
        sort_order: int,
        is_published: bool,
        version: str | None,
        updated_by_id: uuid.UUID | None,
    ) -> PartnerProgramContent:
        row = await ProgramContentRepository.get(session, key, locale)
        if row is None:
            row = PartnerProgramContent(key=key, locale=locale)
            session.add(row)
        row.section = section
        row.title = title
        row.body = body
        row.payload = payload
        row.sort_order = sort_order
        row.is_published = is_published
        row.version = version
        row.updated_by_id = updated_by_id
        await session.flush()
        return row


__all__ = [
    "AttributionRepository",
    "CampaignRepository",
    "ClaimRepository",
    "ClickRepository",
    "CommissionRepository",
    "FraudRepository",
    "GeoRepository",
    "LeadRepository",
    "PartnerApplicationRepository",
    "PartnerRepository",
    "PayoutAccountRepository",
    "PayoutRepository",
    "ProgramContentRepository",
    "ReferralLinkRepository",
    "RelationshipRepository",
    "SettlementRepository",
]
