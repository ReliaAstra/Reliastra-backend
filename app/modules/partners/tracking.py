"""Click tracking and partner attribution.

Two ideas govern this module:

**Clicks are analytics, never money.** A click writes a
:class:`PartnerClickEvent` and may create an attribution touch, but it can
never by itself produce a commission. Duplicate and bot traffic is flagged
rather than rejected, so the raw record stays honest while reported counts
stay meaningful.

**Attribution is last eligible partner touch.** Within a configurable window
(default 90 days) the most recent *eligible* touch owns the customer.
Eligibility means: the partner can earn (active, not terminated) and the
touch has not expired. Rows carry ``model``/``position``/``weight_bps`` so a
multi-touch model can be introduced later by recomputing weights, without a
schema change.

UTM parameters are captured for analytics only. They are stored on the click
and the attribution but are never consulted when deciding *who owns* a
conversion — a ``utm_source`` cannot take a customer away from the partner
whose link was actually used.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException
from app.modules.partners import economics
from app.modules.partners.constants import (
    EARNING_STATUSES,
    MAX_UTM_VALUE_LENGTH,
    UTM_FIELDS,
    AttributionModel,
    AttributionStatus,
    CampaignStatus,
    EarningMethod,
    TouchpointType,
)
from app.modules.partners.geo import GeoService
from app.modules.partners.models import (
    Partner,
    PartnerAttribution,
    PartnerCampaign,
    PartnerClickEvent,
    PartnerReferralLink,
)
from app.modules.partners.repository import (
    AttributionRepository,
    CampaignRepository,
    ClickRepository,
    PartnerRepository,
    ReferralLinkRepository,
)
from app.modules.partners.utils import (
    generate_visitor_id,
    hash_ip,
    looks_like_bot,
    truncate,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ResolvedReferral:
    """Outcome of resolving a public ``/r/{partner_code}`` request."""

    __slots__ = (
        "partner",
        "campaign",
        "link",
        "visitor_id",
        "destination_path",
        "attribution",
        "click",
        "expires_at",
    )

    def __init__(
        self,
        *,
        partner: Partner,
        campaign: PartnerCampaign | None,
        link: PartnerReferralLink | None,
        visitor_id: str,
        destination_path: str,
        attribution: PartnerAttribution | None,
        click: PartnerClickEvent | None,
        expires_at: datetime,
    ) -> None:
        self.partner = partner
        self.campaign = campaign
        self.link = link
        self.visitor_id = visitor_id
        self.destination_path = destination_path
        self.attribution = attribution
        self.click = click
        self.expires_at = expires_at


class TrackingService:
    """Resolves referral links, records clicks and maintains attribution."""

    # ─────────────────────────── resolution ──────────────────────────

    async def resolve_referral(
        self,
        session: AsyncSession,
        *,
        partner_code: str,
        campaign_code: str | None = None,
        destination_path: str | None = None,
        visitor_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
        utm: dict[str, str] | None = None,
        record_click: bool = True,
    ) -> ResolvedReferral:
        """Resolve a public referral link and (optionally) record the click.

        Raises 404 for unknown codes. A *known but non-earning* partner
        (suspended/terminated) still resolves so the visitor is not stranded
        on a dead link — but no attribution touch is created, so nothing can
        later be owed.
        """
        partner = await PartnerRepository.get_by_code(session, partner_code)
        if partner is None:
            raise ResourceNotFoundException(
                "Referral link not found", details={"partner_code": partner_code}
            )

        campaign = None
        if campaign_code:
            campaign = await CampaignRepository.get_by_code(
                session, partner.id, campaign_code
            )
            if campaign is not None and not self._campaign_is_live(campaign):
                # An expired or paused campaign still credits the partner —
                # only the campaign-level association is dropped.
                logger.info(
                    "Campaign %s is not live; attributing to partner only",
                    campaign.campaign_code,
                )
                campaign = None

        link = await ReferralLinkRepository.get_default(session, partner.id)

        resolved_destination = (
            destination_path
            or (campaign.destination_path if campaign else None)
            or (link.destination_path if link else None)
            or "/"
        )

        visitor = visitor_id or generate_visitor_id()
        now = _now()
        expires_at = economics.attribution_expiry(now)

        can_earn = partner.status in EARNING_STATUSES

        click = None
        attribution = None
        if record_click:
            click = await self.record_click(
                session,
                partner=partner,
                campaign=campaign,
                link=link,
                visitor_id=visitor,
                ip=ip,
                user_agent=user_agent,
                referer=referer,
                utm=utm,
            )
            if can_earn:
                attribution = await self.record_touch(
                    session,
                    partner=partner,
                    campaign=campaign,
                    link=link,
                    click=click,
                    visitor_id=visitor,
                    utm=utm,
                    country_code=click.country_code if click else None,
                    occurred_at=now,
                )
                expires_at = _aware(attribution.expires_at) or expires_at

        return ResolvedReferral(
            partner=partner,
            campaign=campaign,
            link=link,
            visitor_id=visitor,
            destination_path=resolved_destination,
            attribution=attribution,
            click=click,
            expires_at=expires_at,
        )

    @staticmethod
    def _campaign_is_live(campaign: PartnerCampaign) -> bool:
        if campaign.status != CampaignStatus.ACTIVE.value:
            return False
        now = _now()
        starts_at = _aware(campaign.starts_at)
        ends_at = _aware(campaign.ends_at)
        if starts_at and now < starts_at:
            return False
        if ends_at and now >= ends_at:
            return False
        return True

    # ────────────────────────────── clicks ───────────────────────────

    async def record_click(
        self,
        session: AsyncSession,
        *,
        partner: Partner,
        campaign: PartnerCampaign | None,
        link: PartnerReferralLink | None,
        visitor_id: str,
        ip: str | None,
        user_agent: str | None,
        referer: str | None,
        utm: dict[str, str] | None,
    ) -> PartnerClickEvent:
        """Persist one click.

        Duplicate detection is per (partner, campaign, visitor) inside the
        configured dedup window; duplicates are still written but flagged so
        the raw event stream remains complete for later analysis.
        """
        now = _now()
        window_start = now - timedelta(
            seconds=max(0, settings.PARTNER_CLICK_DEDUP_WINDOW_SECONDS)
        )
        is_duplicate = await ClickRepository.recent_duplicate_exists(
            session,
            partner_id=partner.id,
            visitor_id=visitor_id,
            since=window_start,
            campaign_id=campaign.id if campaign else None,
        )
        is_bot = looks_like_bot(user_agent)

        geo = await GeoService.resolve(session, ip)
        cleaned_utm = self._clean_utm(utm)

        click = PartnerClickEvent(
            partner_id=partner.id,
            campaign_id=campaign.id if campaign else None,
            link_id=link.id if link else None,
            visitor_id=visitor_id,
            ip_hash=hash_ip(ip),
            user_agent=truncate(user_agent, 500),
            referer=truncate(referer, 500),
            utm_source=cleaned_utm.get("utm_source"),
            utm_medium=cleaned_utm.get("utm_medium"),
            utm_campaign=cleaned_utm.get("utm_campaign"),
            utm_term=cleaned_utm.get("utm_term"),
            utm_content=cleaned_utm.get("utm_content"),
            country_code=geo.country_code,
            country_name=geo.country_name,
            is_duplicate=is_duplicate,
            is_bot=is_bot,
            created_at=now,
        )
        await ClickRepository.add(session, click)

        # Counters are denormalised for fast listing only; they are never a
        # financial source of truth.
        if not is_duplicate and not is_bot:
            partner.total_click_count = (partner.total_click_count or 0) + 1
            if campaign is not None:
                campaign.click_count = (campaign.click_count or 0) + 1
            if link is not None:
                link.click_count = (link.click_count or 0) + 1
                link.last_clicked_at = now
        await session.flush()
        return click

    @staticmethod
    def _clean_utm(utm: dict[str, str] | None) -> dict[str, str]:
        if not utm:
            return {}
        return {
            field: str(utm[field])[:MAX_UTM_VALUE_LENGTH]
            for field in UTM_FIELDS
            if utm.get(field)
        }

    # ──────────────────────────── attribution ────────────────────────

    async def record_touch(
        self,
        session: AsyncSession,
        *,
        partner: Partner,
        campaign: PartnerCampaign | None,
        link: PartnerReferralLink | None,
        click: PartnerClickEvent | None,
        visitor_id: str,
        utm: dict[str, str] | None,
        country_code: str | None,
        occurred_at: datetime | None = None,
        touchpoint_type: str = TouchpointType.CLICK.value,
    ) -> PartnerAttribution:
        """Record a partner touch and make it the owning (last) touch.

        Earlier active touches are marked ``superseded`` and their weight
        zeroed. The full history is retained: switching to a multi-touch
        model later is a matter of recomputing ``weight_bps`` across the
        preserved rows.
        """
        occurred_at = _aware(occurred_at) or _now()
        position = (
            await AttributionRepository.max_position_for_visitor(session, visitor_id)
            + 1
        )

        previous = await AttributionRepository.supersede_active_for_visitor(
            session, visitor_id
        )
        for row in previous:
            row.status = AttributionStatus.SUPERSEDED.value
            row.weight_bps = 0

        attribution = PartnerAttribution(
            partner_id=partner.id,
            campaign_id=campaign.id if campaign else None,
            link_id=link.id if link else None,
            click_event_id=click.id if click else None,
            visitor_id=visitor_id,
            model=AttributionModel.LAST_TOUCH.value,
            touchpoint_type=touchpoint_type,
            position=position,
            weight_bps=10_000,
            status=AttributionStatus.ACTIVE.value,
            occurred_at=occurred_at,
            expires_at=economics.attribution_expiry(occurred_at),
            utm=self._clean_utm(utm) or None,
            country_code=country_code,
        )
        await AttributionRepository.add(session, attribution)
        return attribution

    async def bind_signup(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        visitor_id: str | None,
        partner_code: str | None = None,
        campaign_code: str | None = None,
        email: str | None = None,
    ) -> PartnerAttribution | None:
        """Attach an existing (or freshly resolved) attribution to a new user.

        Called from registration. Two entry paths are supported:

        * ``visitor_id`` — the anonymous cookie captured at click time. This
          is the normal path and preserves last-touch ordering.
        * ``partner_code`` — an explicit code typed into the signup form when
          no click was recorded (offline referral, word of mouth).

        Returns ``None`` when there is nothing to attribute; registration
        must never fail because attribution did not apply.
        """
        attribution: PartnerAttribution | None = None
        now = _now()

        if visitor_id:
            attribution = await AttributionRepository.get_active_for_visitor(
                session, visitor_id, now=now
            )

        if attribution is None and partner_code:
            partner = await PartnerRepository.get_by_code(session, partner_code)
            if partner is None or partner.status not in EARNING_STATUSES:
                return None
            campaign = None
            if campaign_code:
                campaign = await CampaignRepository.get_by_code(
                    session, partner.id, campaign_code
                )
            attribution = await self.record_touch(
                session,
                partner=partner,
                campaign=campaign,
                link=None,
                click=None,
                visitor_id=visitor_id or generate_visitor_id(),
                utm=None,
                country_code=None,
                occurred_at=now,
                touchpoint_type=TouchpointType.SIGNUP.value,
            )

        if attribution is None:
            return None

        partner = await PartnerRepository.get_by_id(session, attribution.partner_id)
        if partner is None or partner.status not in EARNING_STATUSES:
            return None

        # Self-referral guard: a partner cannot attribute their own signup.
        if partner.user_id == user_id:
            attribution.status = AttributionStatus.VOIDED.value
            attribution.notes = "self_referral"
            attribution.weight_bps = 0
            await session.flush()
            logger.warning(
                "Voided self-referral attribution for partner %s", partner.id
            )
            return None

        attribution.user_id = user_id
        attribution.organization_id = organization_id
        await session.flush()

        partner.total_signup_count = (partner.total_signup_count or 0) + 1
        if attribution.link_id:
            link = await ReferralLinkRepository.get_owned(
                session, attribution.link_id, partner.id
            )
            if link is not None:
                link.signup_count = (link.signup_count or 0) + 1
        if attribution.campaign_id:
            campaign = await CampaignRepository.get_owned(
                session, attribution.campaign_id, partner.id
            )
            if campaign is not None:
                campaign.signup_count = (campaign.signup_count or 0) + 1

        await AuditLogService.log_event(
            session,
            event_type="partner.attribution.signup",
            user_id=user_id,
            org_id=organization_id,
            resource_type="partner_attribution",
            resource_id=str(attribution.id),
            payload={"partner_id": str(partner.id)},
        )
        await session.flush()
        return attribution

    async def convert_attribution(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
    ):
        """Promote an attributed signup into an earning relationship.

        Invoked on the first collected payment for an organisation. If the
        attribution window has already elapsed without a conversion, nothing
        is created — an expired touch does not earn.
        """
        from app.modules.partners.service import partner_service

        now = _aware(occurred_at) or _now()
        attribution = None
        if user_id:
            attribution = await AttributionRepository.get_active_for_user(
                session, user_id
            )
        if attribution is None:
            return None

        expires_at = _aware(attribution.expires_at)
        if expires_at is not None and now > expires_at:
            attribution.status = AttributionStatus.EXPIRED.value
            await session.flush()
            return None

        partner = await PartnerRepository.get_by_id(session, attribution.partner_id)
        if partner is None or partner.status not in EARNING_STATUSES:
            return None

        attribution.converted_at = attribution.converted_at or now
        attribution.organization_id = attribution.organization_id or organization_id

        relationship = await partner_service.ensure_relationship(
            session,
            partner_id=partner.id,
            organization_id=organization_id,
            earning_method=EarningMethod.REFER.value,
            started_at=now,
            attribution_id=attribution.id,
            campaign_id=attribution.campaign_id,
        )
        if attribution.campaign_id:
            campaign = await CampaignRepository.get_owned(
                session, attribution.campaign_id, partner.id
            )
            if campaign is not None:
                campaign.conversion_count = (campaign.conversion_count or 0) + 1
        await session.flush()
        return relationship

    async def expire_stale_attributions(
        self, session: AsyncSession, *, limit: int = 5000
    ) -> int:
        """Mark unconverted touches past their window as expired."""
        now = _now()
        stale = await AttributionRepository.expire_stale(session, now=now, limit=limit)
        for row in stale:
            row.status = AttributionStatus.EXPIRED.value
            row.weight_bps = 0
        await session.flush()
        return len(stale)


tracking_service = TrackingService()

__all__ = ["ResolvedReferral", "TrackingService", "tracking_service"]
