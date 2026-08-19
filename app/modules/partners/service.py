"""Core partner domain service: applications, profiles, tiers, campaigns,
links, leads, deployment claims, dashboard and analytics.

All business rules live here (and in the sibling commission/payout/fraud
services); routers only translate HTTP to service calls. Ownership is
enforced by loading rows through ownership-scoped repository methods, so a
caller cannot reach another partner's data even by guessing an id.

Services flush but never commit — the request-scoped session
(:func:`app.db.session.get_db`) or the Celery task body owns the
transaction boundary, exactly as elsewhere in this codebase.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log import AuditLogService
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    ResourceNotFoundException,
    ValidationException,
)
from app.modules.organizations.models import Organization
from app.modules.partners import economics
from app.modules.partners.constants import (
    CLAIM_TRANSITIONS,
    EARNING_STATUSES,
    LEAD_TRANSITIONS,
    MAX_CAMPAIGNS_PER_PARTNER,
    MAX_LINKS_PER_CAMPAIGN,
    TIER_CAPABILITIES,
    TIER_ORDER,
    TIER_REQUIREMENTS,
    ApplicationStatus,
    CampaignStatus,
    ClaimStatus,
    CommissionStatus,
    EarningMethod,
    LeadStatus,
    LinkStatus,
    PartnerStatus,
    PartnerTier,
    RelationshipStatus,
)
from app.modules.partners.landing import build_program_landing
from app.modules.partners.links import ReferralLinkService
from app.modules.partners.models import (
    Partner,
    PartnerApplication,
    PartnerCampaign,
    PartnerClaimEvidence,
    PartnerCustomerRelationship,
    PartnerDeploymentClaim,
    PartnerLead,
    PartnerReferralLink,
    PartnerTierHistory,
)
from app.modules.partners.repository import (
    CampaignRepository,
    ClaimRepository,
    ClickRepository,
    CommissionRepository,
    LeadRepository,
    PartnerApplicationRepository,
    PartnerRepository,
    ProgramContentRepository,
    ReferralLinkRepository,
    RelationshipRepository,
)
from app.modules.partners.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    ClaimReviewRequest,
    CountryStatsItem,
    DeploymentClaimCreate,
    LeadCreate,
    PartnerAnalyticsResponse,
    PartnerApplicationCreate,
    PartnerCapabilities,
    PartnerDashboardResponse,
    PartnerProfileUpdate,
    PartnerProgramResponse,
    PartnerResponse,
    ReferralLinkCreate,
    ReferralLinkResponse,
    ReferredCustomerItem,
    TimeseriesPoint,
)
from app.modules.partners.utils import (
    generate_campaign_code,
    generate_link_token,
    generate_partner_code,
    hash_email,
    is_reserved_code,
    mask_email,
    slugify,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """Normalise naive datetimes read back from the DB to UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class PartnerService:
    """Partner lifecycle and self-service surface."""

    # ───────────────────────── applications ──────────────────────────

    async def apply(
        self,
        session: AsyncSession,
        user: User,
        payload: PartnerApplicationCreate,
        *,
        organization_id: uuid.UUID | None = None,
    ) -> PartnerApplication:
        """Submit a partner application.

        Guarded against the two ways this gets abused in practice: applying
        twice while a review is in flight, and applying when already an
        approved partner.
        """
        if not payload.accept_agreement:
            raise ValidationException(
                "The partner agreement must be accepted to apply",
                details={"field": "accept_agreement"},
            )

        existing_partner = await PartnerRepository.get_by_user_id(session, user.id)
        if existing_partner is not None:
            raise ConflictException(
                "This account is already registered as a partner",
                details={"partner_id": str(existing_partner.id)},
            )

        open_application = await PartnerApplicationRepository.get_open_for_user(
            session, user.id
        )
        if open_application is not None:
            raise ConflictException(
                "An application is already under review",
                details={"application_id": str(open_application.id)},
            )

        now = _now()
        application = PartnerApplication(
            user_id=user.id,
            organization_id=organization_id,
            status=ApplicationStatus.SUBMITTED.value,
            partner_type=payload.partner_type.value,
            display_name=payload.display_name.strip(),
            legal_name=payload.legal_name,
            contact_email=str(payload.contact_email).lower(),
            country_code=payload.country_code,
            website_url=payload.website_url,
            intended_methods=[m.value for m in payload.intended_methods] or None,
            audience_description=payload.audience_description,
            estimated_monthly_reach=payload.estimated_monthly_reach,
            experience=payload.experience,
            motivation=payload.motivation,
            answers=payload.answers,
            agreement_version=payload.agreement_version,
            agreement_accepted_at=now,
            submitted_at=now,
        )
        session.add(application)
        await session.flush()

        await AuditLogService.log_event(
            session,
            event_type="partner.application.submitted",
            user_id=user.id,
            org_id=organization_id,
            resource_type="partner_application",
            resource_id=str(application.id),
            payload={"partner_type": application.partner_type},
        )

        # Config-gated auto-approval exists for low-touch programs and
        # non-production environments; it is off by default.
        if settings.PARTNER_AUTO_APPROVE_APPLICATIONS:
            await self.approve_application(
                session,
                application,
                reviewer_id=None,
                tier=PartnerTier.EXPLORER,
                notes="Auto-approved by configuration",
            )

        return application

    async def list_my_applications(
        self, session: AsyncSession, user: User
    ) -> list[PartnerApplication]:
        return await PartnerApplicationRepository.list_for_user(session, user.id)

    async def approve_application(
        self,
        session: AsyncSession,
        application: PartnerApplication,
        *,
        reviewer_id: uuid.UUID | None,
        tier: PartnerTier | None = None,
        notes: str | None = None,
    ) -> Partner:
        """Approve an application and materialise the partner account."""
        if application.status in {
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.REJECTED.value,
            ApplicationStatus.WITHDRAWN.value,
        }:
            raise ConflictException(
                f"Application is already {application.status}",
                details={"status": application.status},
            )

        existing = await PartnerRepository.get_by_user_id(
            session, application.user_id
        )
        if existing is not None:
            raise ConflictException("A partner already exists for this user")

        now = _now()
        partner = Partner(
            user_id=application.user_id,
            organization_id=application.organization_id,
            partner_code=await self._unique_partner_code(session),
            slug=await self._unique_slug(session, application.display_name),
            display_name=application.display_name,
            legal_name=application.legal_name,
            partner_type=application.partner_type,
            tier=(tier or PartnerTier.EXPLORER).value,
            status=PartnerStatus.ACTIVE.value,
            country_code=application.country_code,
            website_url=application.website_url,
            contact_email=application.contact_email,
            payout_currency=settings.PARTNER_DEFAULT_CURRENCY,
            agreement_version=application.agreement_version,
            agreement_accepted_at=application.agreement_accepted_at,
            approved_at=now,
            is_publicly_listed=False,
        )
        session.add(partner)
        await session.flush()

        application.status = ApplicationStatus.APPROVED.value
        application.reviewed_at = now
        application.reviewed_by_id = reviewer_id
        application.review_notes = notes
        application.partner_id = partner.id

        await PartnerRepository.add_tier_history(
            session,
            PartnerTierHistory(
                partner_id=partner.id,
                from_tier=None,
                to_tier=partner.tier,
                reason="application_approved",
                changed_by_id=reviewer_id,
                is_automatic=reviewer_id is None,
            ),
        )

        # Every partner gets a working default link immediately — the whole
        # point of approval is that they can start sharing.
        await self._ensure_default_link(session, partner)

        await AuditLogService.log_event(
            session,
            event_type="partner.application.approved",
            user_id=reviewer_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"partner_code": partner.partner_code, "tier": partner.tier},
        )
        return partner

    async def reject_application(
        self,
        session: AsyncSession,
        application: PartnerApplication,
        *,
        reviewer_id: uuid.UUID | None,
        reason: str | None,
        notes: str | None = None,
    ) -> PartnerApplication:
        if application.status in {
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.REJECTED.value,
        }:
            raise ConflictException(f"Application is already {application.status}")
        application.status = ApplicationStatus.REJECTED.value
        application.reviewed_at = _now()
        application.reviewed_by_id = reviewer_id
        application.rejection_reason = reason
        application.review_notes = notes
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.application.rejected",
            user_id=reviewer_id,
            resource_type="partner_application",
            resource_id=str(application.id),
            payload={"reason": reason},
        )
        return application

    # ───────────────────────── identity helpers ──────────────────────

    async def _unique_partner_code(self, session: AsyncSession) -> str:
        for _ in range(12):
            code = generate_partner_code()
            if is_reserved_code(code):
                continue
            if not await PartnerRepository.code_exists(session, code):
                return code
        raise ConflictException("Unable to allocate a unique partner code")

    async def _unique_slug(self, session: AsyncSession, display_name: str) -> str:
        base = slugify(display_name)
        if is_reserved_code(base):
            base = f"{base}-partner"
        candidate = base
        for suffix in range(1, 50):
            if not await PartnerRepository.slug_exists(session, candidate):
                return candidate
            candidate = f"{base}-{suffix}"
        return f"{base}-{uuid.uuid4().hex[:6]}"

    # ─────────────────────── partner resolution ──────────────────────

    async def get_partner_for_user(
        self, session: AsyncSession, user: User
    ) -> Partner:
        """Resolve the caller's partner account or fail loudly.

        The partner is *always* derived from the authenticated user; no
        endpoint accepts a partner id from the client.
        """
        partner = await PartnerRepository.get_by_user_id(session, user.id)
        if partner is None:
            raise ResourceNotFoundException(
                "No partner account exists for this user",
                details={"hint": "Submit an application at POST /v1/partners/apply"},
            )
        return partner

    @staticmethod
    def ensure_can_earn(partner: Partner) -> None:
        """Guard for actions that create or grow financial exposure."""
        if partner.status not in EARNING_STATUSES:
            raise ForbiddenException(
                f"Partner account is {partner.status} and cannot perform this action",
                details={"status": partner.status},
            )

    # ────────────────────────── profile ──────────────────────────────

    def to_response(self, partner: Partner) -> PartnerResponse:
        return PartnerResponse(
            id=partner.id,
            partner_code=partner.partner_code,
            slug=partner.slug,
            display_name=partner.display_name,
            legal_name=partner.legal_name,
            partner_type=partner.partner_type,
            tier=partner.tier,
            status=partner.status,
            headline=partner.headline,
            bio=partner.bio,
            website_url=partner.website_url,
            logo_url=partner.logo_url,
            country_code=partner.country_code,
            expertise=partner.expertise,
            languages=partner.languages,
            is_publicly_listed=partner.is_publicly_listed,
            contact_email=partner.contact_email,
            payout_currency=partner.payout_currency,
            referral_url=ReferralLinkService.build(partner.partner_code),
            lifetime_revenue_minor=partner.lifetime_revenue_minor,
            lifetime_commission_minor=partner.lifetime_commission_minor,
            active_customer_count=partner.active_customer_count,
            total_click_count=partner.total_click_count,
            total_signup_count=partner.total_signup_count,
            agreement_accepted_at=partner.agreement_accepted_at,
            approved_at=partner.approved_at,
            created_at=partner.created_at,
        )

    async def update_profile(
        self, session: AsyncSession, partner: Partner, payload: PartnerProfileUpdate
    ) -> Partner:
        data = payload.model_dump(exclude_unset=True)
        if "contact_email" in data and data["contact_email"]:
            data["contact_email"] = str(data["contact_email"]).lower()
        for field, value in data.items():
            setattr(partner, field, value)
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.profile.updated",
            user_id=partner.user_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"fields": sorted(data.keys())},
        )
        return partner

    def capabilities(self, partner: Partner) -> PartnerCapabilities:
        """Tier capabilities — never a commission multiplier.

        Tiers unlock *capabilities* (co-marketing, custom terms, dedicated
        support). Earning rates are per-method and identical across tiers,
        which is what keeps the economics predictable.
        """
        order = sorted(TIER_ORDER.items(), key=lambda item: item[1])
        current_rank = TIER_ORDER.get(partner.tier, 0)
        next_tier = next(
            (name for name, rank in order if rank == current_rank + 1), None
        )
        return PartnerCapabilities(
            tier=partner.tier,
            capabilities=list(TIER_CAPABILITIES.get(partner.tier, [])),
            next_tier=next_tier,
            next_tier_requirements=(
                TIER_REQUIREMENTS.get(next_tier) if next_tier else None
            ),
        )

    async def tier_history(
        self, session: AsyncSession, partner: Partner
    ) -> list[PartnerTierHistory]:
        return await PartnerRepository.list_tier_history(session, partner.id)

    # ───────────────────────────── tiers ─────────────────────────────

    async def evaluate_tier(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        changed_by_id: uuid.UUID | None = None,
    ) -> PartnerTierHistory | None:
        """Recompute the earned tier from ledger-backed metrics.

        Promotion only. Demotion is deliberately *not* automatic: dropping a
        partner's standing is a relationship decision, so it stays an
        explicit admin action.
        """
        active_customers = await RelationshipRepository.count_active(
            session, partner.id
        )
        lifetime_revenue, lifetime_commission = (
            await CommissionRepository.lifetime_totals(session, partner.id)
        )

        partner.active_customer_count = active_customers
        partner.lifetime_revenue_minor = lifetime_revenue
        partner.lifetime_commission_minor = lifetime_commission
        partner.aggregates_updated_at = _now()
        partner.tier_evaluated_at = _now()

        earned = PartnerTier.EXPLORER.value
        for tier, rank in sorted(TIER_ORDER.items(), key=lambda item: item[1]):
            requirement = TIER_REQUIREMENTS.get(tier, {})
            if (
                active_customers >= requirement.get("active_customers", 0)
                and lifetime_revenue >= requirement.get("lifetime_revenue_minor", 0)
            ):
                earned = tier

        # The agency tier reflects a business relationship rather than pure
        # volume, so automation never assigns or removes it.
        if partner.tier == PartnerTier.AGENCY.value:
            await session.flush()
            return None

        if TIER_ORDER.get(earned, 0) <= TIER_ORDER.get(partner.tier, 0):
            await session.flush()
            return None

        previous = partner.tier
        partner.tier = earned
        entry = await PartnerRepository.add_tier_history(
            session,
            PartnerTierHistory(
                partner_id=partner.id,
                from_tier=previous,
                to_tier=earned,
                reason="metrics_threshold_met",
                changed_by_id=changed_by_id,
                is_automatic=changed_by_id is None,
                metrics_snapshot={
                    "active_customers": active_customers,
                    "lifetime_revenue_minor": lifetime_revenue,
                    "lifetime_commission_minor": lifetime_commission,
                },
            ),
        )
        await AuditLogService.log_event(
            session,
            event_type="partner.tier.changed",
            user_id=changed_by_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"from": previous, "to": earned, "automatic": changed_by_id is None},
        )
        return entry

    async def set_tier(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        tier: PartnerTier,
        reason: str,
        changed_by_id: uuid.UUID,
    ) -> PartnerTierHistory:
        previous = partner.tier
        partner.tier = tier.value
        partner.tier_evaluated_at = _now()
        entry = await PartnerRepository.add_tier_history(
            session,
            PartnerTierHistory(
                partner_id=partner.id,
                from_tier=previous,
                to_tier=tier.value,
                reason=reason,
                changed_by_id=changed_by_id,
                is_automatic=False,
            ),
        )
        await AuditLogService.log_event(
            session,
            event_type="partner.tier.changed",
            user_id=changed_by_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"from": previous, "to": tier.value, "reason": reason},
        )
        return entry

    async def set_status(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        status: str,
        reason: str | None,
        changed_by_id: uuid.UUID,
    ) -> Partner:
        valid = {s.value for s in PartnerStatus}
        if status not in valid:
            raise ValidationException(
                f"Unknown partner status: {status}",
                details={"allowed": sorted(valid)},
            )
        previous = partner.status
        now = _now()
        partner.status = status
        if status == PartnerStatus.SUSPENDED.value:
            partner.suspended_at = now
            partner.suspension_reason = reason
            # Suspension freezes money movement but never destroys accrued
            # ledger entries.
            partner.commissions_held = True
        elif status == PartnerStatus.TERMINATED.value:
            partner.terminated_at = now
            partner.suspension_reason = reason
            partner.commissions_held = True
            partner.is_publicly_listed = False
        elif status == PartnerStatus.ACTIVE.value:
            partner.suspended_at = None
            partner.suspension_reason = None
            partner.commissions_held = False
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.status.changed",
            user_id=changed_by_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"from": previous, "to": status, "reason": reason},
        )
        return partner

    async def set_custom_rates(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        custom_rate_bps: dict[str, int],
        reason: str,
        changed_by_id: uuid.UUID,
    ) -> Partner:
        """Negotiated per-method rates, clamped to the platform ceiling.

        Existing relationships keep their snapshotted rate, so changing this
        never rewrites historical economics.
        """
        ceiling = economics.max_total_rate_bps()
        cleaned: dict[str, int] = {}
        for method, bps in custom_rate_bps.items():
            key = method.value if hasattr(method, "value") else str(method)
            if key not in {m.value for m in EarningMethod}:
                raise ValidationException(f"Unknown earning method: {key}")
            cleaned[key] = min(int(bps), ceiling)
        previous = partner.custom_rate_bps
        partner.custom_rate_bps = cleaned or None
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.rates.updated",
            user_id=changed_by_id,
            resource_type="partner",
            resource_id=str(partner.id),
            payload={"from": previous, "to": cleaned, "reason": reason},
        )
        return partner

    # ──────────────────────────── campaigns ──────────────────────────

    async def create_campaign(
        self, session: AsyncSession, partner: Partner, payload: CampaignCreate
    ) -> PartnerCampaign:
        self.ensure_can_earn(partner)
        count = await CampaignRepository.count_for_partner(session, partner.id)
        if count >= MAX_CAMPAIGNS_PER_PARTNER:
            raise ConflictException(
                f"Campaign limit reached ({MAX_CAMPAIGNS_PER_PARTNER})"
            )

        code = payload.campaign_code or generate_campaign_code()
        if await CampaignRepository.get_by_code(session, partner.id, code):
            if payload.campaign_code:
                raise ConflictException(
                    "A campaign with this code already exists",
                    details={"campaign_code": code},
                )
            code = generate_campaign_code(8)

        if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
            raise ValidationException("ends_at must be after starts_at")

        campaign = PartnerCampaign(
            partner_id=partner.id,
            campaign_code=code,
            name=payload.name.strip(),
            description=payload.description,
            status=CampaignStatus.ACTIVE.value,
            destination_path=payload.destination_path,
            default_utm=payload.default_utm,
            channel=payload.channel,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        session.add(campaign)
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.campaign.created",
            user_id=partner.user_id,
            resource_type="partner_campaign",
            resource_id=str(campaign.id),
            payload={"campaign_code": campaign.campaign_code},
        )
        return campaign

    async def get_owned_campaign(
        self, session: AsyncSession, partner: Partner, campaign_id: uuid.UUID
    ) -> PartnerCampaign:
        campaign = await CampaignRepository.get_owned(session, campaign_id, partner.id)
        if campaign is None:
            # 404 rather than 403: existence of another partner's campaign is
            # itself information we do not disclose.
            raise ResourceNotFoundException("Campaign not found")
        return campaign

    async def update_campaign(
        self,
        session: AsyncSession,
        partner: Partner,
        campaign_id: uuid.UUID,
        payload: CampaignUpdate,
    ) -> PartnerCampaign:
        campaign = await self.get_owned_campaign(session, partner, campaign_id)
        data = payload.model_dump(exclude_unset=True)
        if "status" in data and data["status"] is not None:
            data["status"] = (
                data["status"].value
                if hasattr(data["status"], "value")
                else data["status"]
            )
        for field, value in data.items():
            setattr(campaign, field, value)
        await session.flush()
        return campaign

    async def delete_campaign(
        self, session: AsyncSession, partner: Partner, campaign_id: uuid.UUID
    ) -> None:
        """Soft delete. Attribution and commissions already earned through
        this campaign remain intact and auditable."""
        campaign = await self.get_owned_campaign(session, partner, campaign_id)
        campaign.is_deleted = True
        campaign.deleted_at = _now()
        campaign.status = CampaignStatus.ARCHIVED.value
        for link in (
            await ReferralLinkRepository.list_for_partner(
                session, partner.id, campaign_id=campaign.id, size=MAX_LINKS_PER_CAMPAIGN
            )
        )[0]:
            link.status = LinkStatus.ARCHIVED.value
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.campaign.deleted",
            user_id=partner.user_id,
            resource_type="partner_campaign",
            resource_id=str(campaign.id),
        )

    def campaign_to_response(
        self, partner: Partner, campaign: PartnerCampaign
    ) -> CampaignResponse:
        return CampaignResponse(
            id=campaign.id,
            campaign_code=campaign.campaign_code,
            name=campaign.name,
            description=campaign.description,
            status=campaign.status,
            destination_path=campaign.destination_path,
            default_utm=campaign.default_utm,
            channel=campaign.channel,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            referral_url=ReferralLinkService.build_for_campaign(
                partner.partner_code, campaign
            ),
            click_count=campaign.click_count,
            unique_visitor_count=campaign.unique_visitor_count,
            signup_count=campaign.signup_count,
            conversion_count=campaign.conversion_count,
            attributed_revenue_minor=campaign.attributed_revenue_minor,
            created_at=campaign.created_at,
        )

    # ────────────────────────── referral links ───────────────────────

    async def _ensure_default_link(
        self, session: AsyncSession, partner: Partner
    ) -> PartnerReferralLink:
        existing = await ReferralLinkRepository.get_default(session, partner.id)
        if existing is not None:
            return existing
        link = PartnerReferralLink(
            partner_id=partner.id,
            link_token=await self._unique_link_token(session),
            label="Default link",
            status=LinkStatus.ACTIVE.value,
            is_default=True,
        )
        session.add(link)
        await session.flush()
        return link

    async def _unique_link_token(self, session: AsyncSession) -> str:
        from sqlalchemy import select

        for _ in range(12):
            token = generate_link_token()
            result = await session.execute(
                select(PartnerReferralLink.id).where(
                    PartnerReferralLink.link_token == token
                )
            )
            if result.first() is None:
                return token
        raise ConflictException("Unable to allocate a unique link token")

    async def create_link(
        self, session: AsyncSession, partner: Partner, payload: ReferralLinkCreate
    ) -> PartnerReferralLink:
        self.ensure_can_earn(partner)
        campaign = None
        if payload.campaign_id:
            campaign = await self.get_owned_campaign(
                session, partner, payload.campaign_id
            )
            existing_links = await ReferralLinkRepository.count_for_campaign(
                session, campaign.id
            )
            if existing_links >= MAX_LINKS_PER_CAMPAIGN:
                raise ConflictException(
                    f"Link limit reached for this campaign ({MAX_LINKS_PER_CAMPAIGN})"
                )

        link = PartnerReferralLink(
            partner_id=partner.id,
            campaign_id=campaign.id if campaign else None,
            link_token=await self._unique_link_token(session),
            label=payload.label,
            status=LinkStatus.ACTIVE.value,
            destination_path=payload.destination_path,
            utm=payload.utm,
            expires_at=payload.expires_at,
            is_default=False,
        )
        session.add(link)
        await session.flush()
        return link

    async def get_owned_link(
        self, session: AsyncSession, partner: Partner, link_id: uuid.UUID
    ) -> PartnerReferralLink:
        link = await ReferralLinkRepository.get_owned(session, link_id, partner.id)
        if link is None:
            raise ResourceNotFoundException("Referral link not found")
        return link

    async def update_link(
        self,
        session: AsyncSession,
        partner: Partner,
        link_id: uuid.UUID,
        payload,
    ) -> PartnerReferralLink:
        link = await self.get_owned_link(session, partner, link_id)
        data = payload.model_dump(exclude_unset=True)
        if "status" in data and data["status"] is not None:
            data["status"] = (
                data["status"].value
                if hasattr(data["status"], "value")
                else data["status"]
            )
        for field, value in data.items():
            setattr(link, field, value)
        await session.flush()
        return link

    async def delete_link(
        self, session: AsyncSession, partner: Partner, link_id: uuid.UUID
    ) -> None:
        link = await self.get_owned_link(session, partner, link_id)
        if link.is_default:
            raise ValidationException("The default referral link cannot be deleted")
        link.is_deleted = True
        link.deleted_at = _now()
        link.status = LinkStatus.ARCHIVED.value
        await session.flush()

    async def link_to_response(
        self, session: AsyncSession, partner: Partner, link: PartnerReferralLink
    ) -> ReferralLinkResponse:
        campaign = None
        if link.campaign_id:
            campaign = await CampaignRepository.get_owned(
                session, link.campaign_id, partner.id
            )
        url = ReferralLinkService.build_for_link(partner.partner_code, link, campaign)
        return ReferralLinkResponse(
            id=link.id,
            link_token=link.link_token,
            label=link.label,
            status=link.status,
            is_default=link.is_default,
            campaign_id=link.campaign_id,
            campaign_code=campaign.campaign_code if campaign else None,
            destination_path=link.destination_path,
            utm=link.utm,
            url=url,
            short_url=None,
            qr_payload=url,
            click_count=link.click_count,
            unique_visitor_count=link.unique_visitor_count,
            signup_count=link.signup_count,
            last_clicked_at=link.last_clicked_at,
            expires_at=link.expires_at,
            created_at=link.created_at,
        )

    # ──────────────────────────── customers ──────────────────────────

    async def list_referred_customers(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ReferredCustomerItem], int]:
        """Referred customers, always with masked contact details."""
        from sqlalchemy import select

        relationships, total = await RelationshipRepository.list_for_partner(
            session, partner.id, status=status, page=page, size=size
        )
        if not relationships:
            return [], total

        org_ids = [rel.organization_id for rel in relationships]
        user_ids = [rel.customer_user_id for rel in relationships if rel.customer_user_id]

        orgs = {
            org.id: org
            for org in (
                await session.execute(
                    select(Organization).where(Organization.id.in_(org_ids))
                )
            )
            .scalars()
            .all()
        }
        users = {}
        if user_ids:
            users = {
                user.id: user
                for user in (
                    await session.execute(select(User).where(User.id.in_(user_ids)))
                )
                .scalars()
                .all()
            }

        items: list[ReferredCustomerItem] = []
        for rel in relationships:
            org = orgs.get(rel.organization_id)
            user = users.get(rel.customer_user_id) if rel.customer_user_id else None
            items.append(
                ReferredCustomerItem(
                    relationship_id=rel.id,
                    organization_name=getattr(org, "name", None),
                    masked_email=mask_email(getattr(user, "email", None)),
                    country_code=None,
                    earning_method=rel.earning_method,
                    status=rel.status,
                    plan=getattr(org, "plan", None),
                    started_at=rel.started_at,
                    eligible_until=rel.eligible_until,
                    total_revenue_minor=rel.total_revenue_minor,
                    total_commission_minor=rel.total_commission_minor,
                    currency=rel.currency,
                )
            )
        return items, total

    # ──────────────────────────── dashboard ──────────────────────────

    async def dashboard(
        self, session: AsyncSession, partner: Partner
    ) -> PartnerDashboardResponse:
        """Partner home view.

        Every money figure is summed live from the immutable ledger; the
        cached counters on ``partners`` are only used for non-financial
        engagement metrics.
        """
        now = _now()
        window_start = now - timedelta(days=30)

        balances = await CommissionRepository.balance_by_status(session, partner.id)
        payable = balances.get(CommissionStatus.PAYABLE.value, 0)
        minimum = economics.payout_minimum_minor(partner.min_payout_minor)

        clicks = await ClickRepository.count_for_partner(
            session, partner.id, since=window_start
        )
        signups = await self._signup_count(session, partner.id, since=window_start)
        conversions = len(
            await CommissionRepository.list_for_partner(
                session, partner.id, page=1, size=1
            )
        )
        series = await CommissionRepository.daily_series(
            session, partner.id, start=window_start, end=now
        )
        conversions = sum(row[1] for row in series)

        lifetime_revenue, lifetime_commission = (
            await CommissionRepository.lifetime_totals(session, partner.id)
        )

        return PartnerDashboardResponse(
            partner_id=partner.id,
            partner_code=partner.partner_code,
            tier=partner.tier,
            status=partner.status,
            referral_url=ReferralLinkService.build(partner.partner_code),
            currency=partner.payout_currency,
            clicks_30d=clicks,
            signups_30d=signups,
            conversions_30d=conversions,
            active_customers=await RelationshipRepository.count_active(
                session, partner.id
            ),
            pending_commission_minor=balances.get(CommissionStatus.PENDING.value, 0),
            held_commission_minor=balances.get(CommissionStatus.HELD.value, 0),
            payable_commission_minor=payable,
            paid_commission_minor=balances.get(CommissionStatus.PAID.value, 0),
            reversed_commission_minor=balances.get(CommissionStatus.REVERSED.value, 0),
            lifetime_commission_minor=lifetime_commission,
            lifetime_revenue_minor=lifetime_revenue,
            next_payout_eligible=(
                payable >= minimum
                and not partner.commissions_held
                and partner.status == PartnerStatus.ACTIVE.value
            ),
            min_payout_minor=minimum,
            open_leads=await LeadRepository.count_open(session, partner.id),
            pending_claims=await ClaimRepository.count_pending(session, partner.id),
        )

    async def _signup_count(
        self, session: AsyncSession, partner_id: uuid.UUID, *, since: datetime
    ) -> int:
        from app.modules.partners.repository import AttributionRepository

        return await AttributionRepository.count_signups(
            session, partner_id, since=since
        )

    async def analytics(
        self,
        session: AsyncSession,
        partner: Partner,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> PartnerAnalyticsResponse:
        today = _now().date()
        to_date = to_date or today
        from_date = from_date or (to_date - timedelta(days=29))
        if from_date > to_date:
            raise ValidationException("from_date must not be after to_date")
        if (to_date - from_date).days > 366:
            raise ValidationException("The maximum analytics range is 366 days")

        start = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(
            to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )

        click_rows = await ClickRepository.daily_series(
            session, partner.id, start=start, end=end
        )
        commission_rows = await CommissionRepository.daily_series(
            session, partner.id, start=start, end=end
        )

        by_day: dict[date, TimeseriesPoint] = {}
        for day, clicks, uniques in click_rows:
            by_day[day] = TimeseriesPoint(
                day=day, clicks=clicks, unique_visitors=uniques
            )
        for day, conversions, revenue, commission in commission_rows:
            point = by_day.get(day) or TimeseriesPoint(day=day)
            point = point.model_copy(
                update={
                    "conversions": conversions,
                    "revenue_minor": revenue,
                    "commission_minor": commission,
                }
            )
            by_day[day] = point

        series = [by_day[key] for key in sorted(by_day)]
        totals = TimeseriesPoint(
            day=to_date,
            clicks=sum(p.clicks for p in series),
            unique_visitors=sum(p.unique_visitors for p in series),
            signups=sum(p.signups for p in series),
            conversions=sum(p.conversions for p in series),
            revenue_minor=sum(p.revenue_minor for p in series),
            commission_minor=sum(p.commission_minor for p in series),
        )

        campaign_clicks = await ClickRepository.campaign_breakdown(
            session, partner.id, start=start, end=end
        )
        campaign_revenue = await CommissionRepository.campaign_revenue(
            session, partner.id, start=start, end=end
        )
        revenue_by_campaign = {row[0]: row for row in campaign_revenue}
        by_campaign = [
            {
                "campaign_id": str(campaign_id) if campaign_id else None,
                "clicks": clicks,
                "unique_visitors": uniques,
                "conversions": revenue_by_campaign.get(campaign_id, (None, 0, 0, 0))[1],
                "revenue_minor": revenue_by_campaign.get(campaign_id, (None, 0, 0, 0))[2],
                "commission_minor": revenue_by_campaign.get(
                    campaign_id, (None, 0, 0, 0)
                )[3],
            }
            for campaign_id, clicks, uniques in campaign_clicks
        ]

        country_rows = await ClickRepository.country_breakdown(
            session, start=start, end=end, partner_id=partner.id
        )
        by_country = [
            CountryStatsItem(
                country_code=code or "??",
                country_name=name,
                clicks=clicks,
                unique_visitors=uniques,
                currency=partner.payout_currency,
            ).model_dump()
            for code, name, clicks, uniques in country_rows
        ]

        return PartnerAnalyticsResponse(
            from_date=from_date,
            to_date=to_date,
            currency=partner.payout_currency,
            totals=totals,
            series=series,
            by_campaign=by_campaign,
            by_country=by_country,
        )

    # ─────────────────────────────── leads ───────────────────────────

    async def create_lead(
        self, session: AsyncSession, partner: Partner, payload: LeadCreate
    ) -> PartnerLead:
        """Register a lead introduction.

        Deduplication is deliberately based on a keyed hash of the email and
        is checked across *all* partners: two partners cannot both claim the
        same prospect while an introduction is open. The rejecting response
        never reveals who holds the existing claim.
        """
        self.ensure_can_earn(partner)
        if not payload.consent_confirmed:
            raise ValidationException(
                "Prospect consent must be confirmed before submitting an introduction",
                details={"field": "consent_confirmed"},
            )

        email_hash = hash_email(str(payload.contact_email))
        now = _now()
        duplicate = await LeadRepository.find_open_by_email_hash(
            session, email_hash, now=now
        )
        if duplicate is not None:
            # Deliberately identical for every duplicate, whoever owns the
            # existing lead. Distinguishing "yours" from "someone else's" would
            # turn this endpoint into an oracle for probing which prospects are
            # already claimed across the partner network.
            raise ConflictException(
                "This prospect already has an open introduction",
                details={},
            )

        lead = PartnerLead(
            partner_id=partner.id,
            status=LeadStatus.SUBMITTED.value,
            company_name=payload.company_name.strip(),
            contact_name=payload.contact_name.strip(),
            contact_email=str(payload.contact_email).lower(),
            contact_email_hash=email_hash,
            contact_phone=payload.contact_phone,
            contact_title=payload.contact_title,
            country_code=payload.country_code,
            company_size=payload.company_size,
            industry=payload.industry,
            use_case=payload.use_case,
            estimated_value_minor=payload.estimated_value_minor,
            currency=payload.currency.upper(),
            notes=payload.notes,
            consent_confirmed=True,
            consent_confirmed_at=now,
            # Exclusivity mirrors the Year-1 introduce window.
            exclusive_until=economics.introduce_window_end(now),
        )
        session.add(lead)
        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.lead.submitted",
            user_id=partner.user_id,
            resource_type="partner_lead",
            resource_id=str(lead.id),
            payload={"company_name": lead.company_name},
        )
        return lead

    async def get_owned_lead(
        self, session: AsyncSession, partner: Partner, lead_id: uuid.UUID
    ) -> PartnerLead:
        lead = await LeadRepository.get_owned(session, lead_id, partner.id)
        if lead is None:
            raise ResourceNotFoundException("Lead not found")
        return lead

    async def transition_lead(
        self,
        session: AsyncSession,
        lead: PartnerLead,
        *,
        new_status: str,
        actor_id: uuid.UUID | None,
        reason: str | None = None,
        converted_organization_id: uuid.UUID | None = None,
    ) -> PartnerLead:
        allowed = LEAD_TRANSITIONS.get(lead.status, frozenset())
        if new_status not in allowed:
            raise ConflictException(
                f"Cannot move a lead from {lead.status} to {new_status}",
                details={"allowed": sorted(allowed)},
            )

        now = _now()
        lead.status = new_status
        lead.reviewed_by_id = actor_id
        if new_status == LeadStatus.ACCEPTED.value:
            lead.accepted_at = now
        elif new_status == LeadStatus.CONTACTED.value:
            lead.contacted_at = now
        elif new_status == LeadStatus.QUALIFIED.value:
            lead.qualified_at = now
        elif new_status == LeadStatus.REJECTED.value:
            lead.rejection_reason = reason
            lead.closed_at = now
        elif new_status in {LeadStatus.LOST.value, LeadStatus.EXPIRED.value}:
            lead.closed_at = now
        elif new_status == LeadStatus.CONVERTED.value:
            if converted_organization_id is None:
                raise ValidationException(
                    "converted_organization_id is required to convert a lead"
                )
            lead.converted_at = now
            lead.closed_at = now
            lead.converted_organization_id = converted_organization_id
            # Conversion is what creates the earning relationship — the
            # Year-1 introduce window starts here.
            await self.ensure_relationship(
                session,
                partner_id=lead.partner_id,
                organization_id=converted_organization_id,
                earning_method=EarningMethod.INTRODUCE.value,
                started_at=now,
                lead_id=lead.id,
                currency=lead.currency,
            )

        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type="partner.lead.status_changed",
            user_id=actor_id,
            resource_type="partner_lead",
            resource_id=str(lead.id),
            payload={"to": new_status, "reason": reason},
        )
        return lead

    def lead_to_response(self, lead: PartnerLead) -> dict[str, Any]:
        return {
            "id": lead.id,
            "status": lead.status,
            "company_name": lead.company_name,
            "contact_name": lead.contact_name,
            "masked_contact_email": mask_email(lead.contact_email),
            "country_code": lead.country_code,
            "industry": lead.industry,
            "company_size": lead.company_size,
            "estimated_value_minor": lead.estimated_value_minor,
            "currency": lead.currency,
            "exclusive_until": lead.exclusive_until,
            "accepted_at": lead.accepted_at,
            "contacted_at": lead.contacted_at,
            "qualified_at": lead.qualified_at,
            "converted_at": lead.converted_at,
            "rejection_reason": lead.rejection_reason,
            "created_at": lead.created_at,
        }

    # ────────────────────────── deployment claims ────────────────────

    async def create_claim(
        self,
        session: AsyncSession,
        partner: Partner,
        payload: DeploymentClaimCreate,
    ) -> PartnerDeploymentClaim:
        """Submit a deployment/creation claim.

        Evidence is mandatory: a deploy claim converts directly into a 30%
        earning relationship, so it must be reviewable rather than
        self-asserted.
        """
        self.ensure_can_earn(partner)
        if not payload.evidence:
            raise ValidationException(
                "At least one piece of evidence is required",
                details={"field": "evidence"},
            )
        if payload.earning_method not in {
            EarningMethod.DEPLOY,
            EarningMethod.CREATE,
        }:
            raise ValidationException(
                "Claims apply to the deploy and create earning methods only"
            )

        claim = PartnerDeploymentClaim(
            partner_id=partner.id,
            organization_id=payload.organization_id,
            customer_identifier=payload.customer_identifier,
            status=ClaimStatus.SUBMITTED.value,
            earning_method=payload.earning_method.value,
            title=payload.title.strip(),
            description=payload.description.strip(),
            deployed_at=payload.deployed_at,
        )
        session.add(claim)
        await session.flush()

        for item in payload.evidence:
            await ClaimRepository.add_evidence(
                session,
                PartnerClaimEvidence(
                    claim_id=claim.id,
                    evidence_type=item.evidence_type.value,
                    title=item.title,
                    description=item.description,
                    url=item.url,
                    storage_key=item.storage_key,
                    uploaded_by_id=partner.user_id,
                ),
            )

        await AuditLogService.log_event(
            session,
            event_type="partner.claim.submitted",
            user_id=partner.user_id,
            resource_type="partner_deployment_claim",
            resource_id=str(claim.id),
            payload={"earning_method": claim.earning_method},
        )
        return claim

    async def get_owned_claim(
        self, session: AsyncSession, partner: Partner, claim_id: uuid.UUID
    ) -> PartnerDeploymentClaim:
        claim = await ClaimRepository.get_owned(session, claim_id, partner.id)
        if claim is None:
            raise ResourceNotFoundException("Deployment claim not found")
        return claim

    async def review_claim(
        self,
        session: AsyncSession,
        claim: PartnerDeploymentClaim,
        payload: ClaimReviewRequest,
        *,
        reviewer_id: uuid.UUID,
    ) -> PartnerDeploymentClaim:
        target = (
            ClaimStatus.APPROVED.value if payload.approve else ClaimStatus.REJECTED.value
        )
        allowed = CLAIM_TRANSITIONS.get(claim.status, frozenset())
        if target not in allowed:
            raise ConflictException(
                f"Cannot move a claim from {claim.status} to {target}",
                details={"allowed": sorted(allowed)},
            )

        now = _now()
        claim.status = target
        claim.reviewed_at = now
        claim.reviewed_by_id = reviewer_id
        claim.review_notes = payload.review_notes
        claim.rejection_reason = payload.rejection_reason if not payload.approve else None

        if payload.approve:
            if claim.organization_id is None:
                raise ValidationException(
                    "An approved claim must be linked to a customer organisation",
                    details={"field": "organization_id"},
                )
            relationship = await self.ensure_relationship(
                session,
                partner_id=claim.partner_id,
                organization_id=claim.organization_id,
                earning_method=claim.earning_method,
                started_at=claim.deployed_at or now,
                claim_id=claim.id,
                rate_bps_override=payload.rate_bps_override,
            )
            claim.relationship_id = relationship.id

        await session.flush()
        await AuditLogService.log_event(
            session,
            event_type=f"partner.claim.{'approved' if payload.approve else 'rejected'}",
            user_id=reviewer_id,
            resource_type="partner_deployment_claim",
            resource_id=str(claim.id),
        )
        return claim

    # ──────────────────────── relationships ──────────────────────────

    async def ensure_relationship(
        self,
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        organization_id: uuid.UUID,
        earning_method: str,
        started_at: datetime,
        attribution_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        claim_id: uuid.UUID | None = None,
        referral_id: uuid.UUID | None = None,
        rate_bps_override: int | None = None,
        currency: str | None = None,
    ) -> PartnerCustomerRelationship:
        """Create (or return) the revenue-bearing partner↔customer link.

        The effective rate is **snapshotted** at creation so that later
        changes to configuration or negotiated terms cannot retroactively
        alter what a customer's payments are worth.
        """
        existing = await RelationshipRepository.get_for_org_and_method(
            session, organization_id, partner_id, earning_method
        )
        if existing is not None:
            return existing

        partner = await PartnerRepository.get_by_id(session, partner_id)
        if partner is None:
            raise ResourceNotFoundException("Partner not found")

        rate_bps = (
            min(int(rate_bps_override), economics.max_total_rate_bps())
            if rate_bps_override is not None
            else economics.resolve_rate_bps(
                earning_method, custom_rate_bps=partner.custom_rate_bps
            )
        )

        started_at = _aware(started_at) or _now()
        eligible_until = (
            economics.introduce_window_end(started_at)
            if earning_method == EarningMethod.INTRODUCE.value
            else None
        )

        relationship = PartnerCustomerRelationship(
            partner_id=partner_id,
            organization_id=organization_id,
            earning_method=earning_method,
            rate_bps=rate_bps,
            status=RelationshipStatus.ACTIVE.value,
            attribution_id=attribution_id,
            campaign_id=campaign_id,
            lead_id=lead_id,
            claim_id=claim_id,
            referral_id=referral_id,
            started_at=started_at,
            eligible_until=eligible_until,
            currency=currency or partner.payout_currency,
        )
        session.add(relationship)
        await session.flush()

        partner.active_customer_count = await RelationshipRepository.count_active(
            session, partner_id
        )

        await AuditLogService.log_event(
            session,
            event_type="partner.relationship.created",
            user_id=None,
            org_id=organization_id,
            resource_type="partner_customer_relationship",
            resource_id=str(relationship.id),
            payload={
                "partner_id": str(partner_id),
                "earning_method": earning_method,
                "rate_bps": rate_bps,
            },
        )
        return relationship

    async def end_relationship(
        self,
        session: AsyncSession,
        relationship: PartnerCustomerRelationship,
        *,
        status: str,
        reason: str,
    ) -> PartnerCustomerRelationship:
        relationship.status = status
        relationship.ended_at = _now()
        relationship.end_reason = reason
        await session.flush()
        partner = await PartnerRepository.get_by_id(session, relationship.partner_id)
        if partner is not None:
            partner.active_customer_count = await RelationshipRepository.count_active(
                session, partner.id
            )
        return relationship

    # ───────────────────────── program content ───────────────────────

    async def program(
        self, session: AsyncSession, *, locale: str = "en"
    ) -> PartnerProgramResponse:
        """Backend-managed program description + live economics.

        Rates and windows are read from configuration and served to clients
        so that no marketing surface has to hardcode the commission
        structure.
        """
        content = await ProgramContentRepository.list_published(
            session, locale=locale
        )
        tiers = [
            {
                "tier": tier,
                "rank": rank,
                "requirements": TIER_REQUIREMENTS.get(tier, {}),
                "capabilities": TIER_CAPABILITIES.get(tier, []),
            }
            for tier, rank in sorted(TIER_ORDER.items(), key=lambda item: item[1])
        ]
        methods = [
            {
                "method": method.value,
                "rate_bps": economics.default_rate_bps(method.value),
                "is_recurring": method.value
                in {
                    EarningMethod.REFER.value,
                    EarningMethod.DEPLOY.value,
                    EarningMethod.CREATE.value,
                },
                "window_months": (
                    settings.PARTNER_INTRODUCE_WINDOW_MONTHS
                    if method == EarningMethod.INTRODUCE
                    else None
                ),
            }
            for method in EarningMethod
        ]
        from app.modules.partners.schemas import PartnerProgramContentItem

        content_items = [
            PartnerProgramContentItem.model_validate(c) for c in content
        ]
        landing = build_program_landing()
        return PartnerProgramResponse(
            tiers=tiers,
            earning_methods=methods,
            attribution_window_days=settings.PARTNER_ATTRIBUTION_WINDOW_DAYS,
            commission_hold_days=settings.PARTNER_COMMISSION_HOLD_DAYS,
            min_payout_minor=settings.PARTNER_MIN_PAYOUT_MINOR,
            currency=settings.PARTNER_DEFAULT_CURRENCY,
            max_total_commission_bps=settings.PARTNER_MAX_TOTAL_COMMISSION_BPS,
            content=content_items,
            landing=landing,
        )


partner_service = PartnerService()

__all__ = ["PartnerService", "partner_service"]
