"""Referral URL construction.

Every partner-facing URL in the platform is produced here and nowhere else.
Two rules motivate the existence of this module:

1. **No hardcoded origin.** The base URL comes from
   ``settings.RELIASTRA_PUBLIC_URL`` (+ ``PARTNER_REFERRAL_PATH_PREFIX``), so
   staging, preview and production emit correct links without code changes.
2. **One canonical shape.** The canonical link is
   ``{RELIASTRA_PUBLIC_URL}/r/{partner_code}`` and the campaign variant adds
   ``?campaign={campaign_code}``. Because every caller goes through this
   service, the link a partner copies, the link in an email and the link a
   test asserts on are byte-identical.

Note that this is intentionally separate from the existing PLG referral link
(``{FRONTEND_BASE_URL}/ref/{code}``) built by
:mod:`app.modules.referrals.service` — that flow is untouched.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from app.config import settings
from app.modules.partners.constants import UTM_FIELDS


class ReferralLinkService:
    """Builds canonical partner referral URLs.

    Stateless and I/O-free — safe to call from services, routers and tasks.
    """

    @staticmethod
    def base_url() -> str:
        """``https://reliastra.com/r`` (configuration-driven, no trailing slash)."""
        return settings.partner_referral_base_url

    @staticmethod
    def build(
        partner_code: str,
        *,
        campaign_code: str | None = None,
        destination_path: str | None = None,
        utm: dict[str, str] | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Return the shareable URL for a partner (optionally a campaign).

        ``destination_path`` is passed through as a ``to`` parameter rather
        than being spliced into the path: the canonical ``/r/{code}`` shape
        stays stable, and the resolver decides where to send the visitor.
        """
        code = quote(partner_code.strip(), safe="")
        url = f"{ReferralLinkService.base_url()}/{code}"

        params: list[tuple[str, str]] = []
        if campaign_code:
            params.append(("campaign", campaign_code.strip()))
        if destination_path:
            params.append(("to", destination_path))
        for field in UTM_FIELDS:
            value = (utm or {}).get(field)
            if value:
                params.append((field, str(value)))
        for key, value in (extra_params or {}).items():
            if value:
                params.append((key, str(value)))

        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    @staticmethod
    def build_for_link(partner_code: str, link, campaign=None) -> str:
        """Build the URL for a stored :class:`PartnerReferralLink` row.

        Campaign UTM defaults are applied first and the link's own UTM values
        win, so a link can specialise its campaign without redefining it.
        """
        merged_utm: dict[str, str] = {}
        if campaign is not None and getattr(campaign, "default_utm", None):
            merged_utm.update(campaign.default_utm)
        if getattr(link, "utm", None):
            merged_utm.update(link.utm)

        destination = getattr(link, "destination_path", None) or (
            getattr(campaign, "destination_path", None) if campaign else None
        )
        campaign_code = getattr(campaign, "campaign_code", None) if campaign else None

        return ReferralLinkService.build(
            partner_code,
            campaign_code=campaign_code,
            destination_path=destination,
            utm=merged_utm or None,
        )

    @staticmethod
    def build_for_campaign(partner_code: str, campaign) -> str:
        return ReferralLinkService.build(
            partner_code,
            campaign_code=getattr(campaign, "campaign_code", None),
            destination_path=getattr(campaign, "destination_path", None),
            utm=getattr(campaign, "default_utm", None),
        )

    @staticmethod
    def public_profile_url(slug: str) -> str:
        origin = settings.RELIASTRA_PUBLIC_URL.rstrip("/")
        return f"{origin}/partners/{quote(slug, safe='')}"

    @staticmethod
    def default_destination_path() -> str:
        """Where a referral lands when nothing more specific is configured."""
        return "/"


referral_link_service = ReferralLinkService()

__all__ = ["ReferralLinkService", "referral_link_service"]
