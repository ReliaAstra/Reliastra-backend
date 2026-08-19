"""Public Partner Network landing copy, driven by live economics.

The frontend must not hardcode commission rates. Every number on the
public /partners page comes from this module (and therefore from
configuration) so a rate change is a deploy of settings, not a rewrite of
marketing surfaces.

Copy is real product language. It does not invent payout calendars,
downloadable assets, white-label features or live partner statistics.
"""

from __future__ import annotations

from app.config import settings
from app.modules.partners import economics
from app.modules.partners.constants import (
    EarningMethod,
    RECURRING_METHODS,
    TIER_CAPABILITIES,
    TIER_ORDER,
    TIER_REQUIREMENTS,
)
from app.modules.partners.links import ReferralLinkService


def _bps_percent(bps: int) -> str:
    whole, frac = divmod(int(bps), 100)
    if frac == 0:
        return f"{whole}%"
    return f"{bps / 100:.2f}%".rstrip("0").rstrip(".") + "%"


def _method_copy() -> list[dict]:
    descriptions = {
        EarningMethod.REFER.value: (
            "A company signs up through your referral link and becomes a "
            "paying customer. Commission accrues on eligible collected "
            "subscription revenue while the relationship stays active."
        ),
        EarningMethod.DEPLOY.value: (
            "You implemented RELIASTRA for the customer. Requires a reviewed "
            "deployment claim. Recurring while the relationship is active."
        ),
        EarningMethod.CREATE.value: (
            "You built a product, integration or content surface on the "
            "platform. Requires a reviewed claim. Recurring while active."
        ),
        EarningMethod.INTRODUCE.value: (
            "A consented warm introduction that converts. Commission is "
            "limited to the configured Year-1 window and is not lifetime."
        ),
        EarningMethod.RESELL.value: (
            "Resellers are compensated through wholesale margin, not a "
            "platform commission ledger entry."
        ),
    }
    methods = []
    for method in EarningMethod:
        rate = economics.default_rate_bps(method.value)
        methods.append(
            {
                "method": method.value,
                "rate_bps": rate,
                "rate_display": _bps_percent(rate),
                "is_recurring": method.value in RECURRING_METHODS,
                "window_months": (
                    settings.PARTNER_INTRODUCE_WINDOW_MONTHS
                    if method == EarningMethod.INTRODUCE
                    else None
                ),
                "description": descriptions[method.value],
            }
        )
    return methods


def _tiers() -> list[dict]:
    return [
        {
            "tier": tier,
            "rank": rank,
            "requirements": TIER_REQUIREMENTS.get(tier, {}),
            "capabilities": list(TIER_CAPABILITIES.get(tier, [])),
            "note": (
                "Tiers unlock capabilities. They are not a commission multiplier."
            ),
        }
        for tier, rank in sorted(TIER_ORDER.items(), key=lambda item: item[1])
    ]


def _illustration() -> dict:
    """Clearly labelled example. Never a guaranteed payout."""
    subscription_minor = 9900
    rate = economics.default_rate_bps(EarningMethod.REFER.value)
    commission_minor = economics.apply_bps(subscription_minor, rate)
    return {
        "label": "ILLUSTRATIVE EXAMPLE",
        "disclaimer": (
            "This is an illustration using the current refer rate applied to "
            "an example collected subscription amount. It is not a guaranteed "
            "payout. Commission is calculated by the backend from verified "
            "collected revenue and program terms."
        ),
        "subscription_minor": subscription_minor,
        "subscription_display": f"${economics.format_minor(subscription_minor)}/mo",
        "method": EarningMethod.REFER.value,
        "rate_bps": rate,
        "rate_display": _bps_percent(rate),
        "commission_minor": commission_minor,
        "commission_display": f"${economics.format_minor(commission_minor)}/mo",
        "currency": settings.PARTNER_DEFAULT_CURRENCY,
        "continues_while_active": True,
    }


def _faq() -> list[dict]:
    refer = _bps_percent(economics.default_rate_bps(EarningMethod.REFER.value))
    deploy = _bps_percent(economics.default_rate_bps(EarningMethod.DEPLOY.value))
    create = _bps_percent(economics.default_rate_bps(EarningMethod.CREATE.value))
    introduce = _bps_percent(
        economics.default_rate_bps(EarningMethod.INTRODUCE.value)
    )
    hold = settings.PARTNER_COMMISSION_HOLD_DAYS
    window = settings.PARTNER_ATTRIBUTION_WINDOW_DAYS
    min_payout = economics.format_minor(settings.PARTNER_MIN_PAYOUT_MINOR)
    currency = settings.PARTNER_DEFAULT_CURRENCY
    return [
        {
            "id": "what-is-the-network",
            "question": "What is the RELIASTRA Partner Network?",
            "answer": (
                "A distribution layer around RELIASTRA's accountability "
                "infrastructure. Partners introduce independent observation, "
                "correlation and evidence to companies that depend on external "
                "APIs, cloud platforms, payments, identity and other vendors. "
                "When a referred company becomes a paying customer, eligible "
                "collected revenue can generate commission according to program terms."
            ),
        },
        {
            "id": "who-can-join",
            "question": "Who can become a partner?",
            "answer": (
                "Consultants, agencies, MSPs, developers, technical creators, "
                "communities, founders, sales professionals and others who "
                "already work with companies that depend on third-party "
                "infrastructure. Joining requires an authenticated application "
                "and acceptance of the partner agreement. Approval is a review "
                "step unless auto-approval is enabled for the environment."
            ),
        },
        {
            "id": "cost",
            "question": "Does it cost anything to join?",
            "answer": "There is no fee to apply or to hold a partner account.",
        },
        {
            "id": "attribution",
            "question": "How does referral attribution work?",
            "answer": (
                f"A visitor opens your unique link ({ReferralLinkService.build('YOURCODE')}). "
                "The backend records a click and returns an anonymous visitor id. "
                "The client stores that id and sends it at signup as "
                "partner_visitor_id. Last eligible touch wins inside a "
                f"{window}-day window. Clicks and signups are not payable. "
                "Commission is created only when a verified payment is collected."
            ),
        },
        {
            "id": "earn",
            "question": "How much do partners earn?",
            "answer": (
                f"Default configured rates: refer {refer} recurring, deploy "
                f"{deploy} recurring (reviewed claim), create {create} "
                f"recurring (reviewed claim), introduce {introduce} for the "
                f"Year-1 window only, resell 0% (wholesale margin instead). "
                "Rates are served from configuration. Combined commission on a "
                f"single payment cannot exceed {_bps_percent(settings.PARTNER_MAX_TOTAL_COMMISSION_BPS)}."
            ),
        },
        {
            "id": "recurring",
            "question": "Is commission recurring?",
            "answer": (
                "Refer, deploy and create accrue on eligible collected "
                "payments while the customer relationship stays active. "
                "Introduce is limited to the Year-1 window. Resell does not "
                "write a platform commission."
            ),
        },
        {
            "id": "upgrades",
            "question": "What happens when a referred customer upgrades?",
            "answer": (
                "Commission is calculated from actual collected revenue, not "
                "list price. If an upgrade increases collected subscription "
                "revenue, later eligible payments use that collected amount "
                "at the snapshotted relationship rate."
            ),
        },
        {
            "id": "agencies",
            "question": "Can agencies use RELIASTRA for multiple clients?",
            "answer": (
                "Yes. Agencies can introduce RELIASTRA across client "
                "environments. Multi-client operational management uses the "
                "existing agency/client product surface. Partner commission "
                "is separate and follows attributed paying customers."
            ),
        },
        {
            "id": "white-label",
            "question": "Can I use RELIASTRA as a white-label offering?",
            "answer": (
                "The current partner program does not expose a white-label "
                "rebranding API. Agency-tier capabilities include managed "
                "clients and co-marketing when earned. Do not market "
                "white-label as a live partner feature."
            ),
        },
        {
            "id": "referral-link",
            "question": "How do I access my referral link?",
            "answer": (
                "After approval, GET /v1/partners/me and "
                "GET /v1/partners/me/dashboard return referral_url. Additional "
                "campaign links are created at POST /v1/partners/me/links. "
                "Use the URL the backend returns; do not assemble one."
            ),
        },
        {
            "id": "see-commissions",
            "question": "Where can I see my commissions?",
            "answer": (
                "Authenticated partners read GET /v1/partners/me/commissions "
                "and GET /v1/partners/me/commissions/balance. Amounts are "
                "integer minor units from the immutable ledger."
            ),
        },
        {
            "id": "paid",
            "question": "When are commissions paid?",
            "answer": (
                f"New commissions start pending for {hold} days, then become "
                f"payable. Partners may request a payout of the payable "
                f"balance once it meets the minimum of {currency} {min_payout}. "
                "The backend derives the amount from the ledger. There is no "
                "fixed calendar date published beyond the hold and the "
                "minimum threshold."
            ),
        },
    ]


def _audiences() -> list[dict]:
    return [
        {
            "id": "devops-sre",
            "title": "DevOps / SRE",
            "body": "Introduce independent evidence when a vendor, not the client's system, caused the incident.",
        },
        {
            "id": "cloud",
            "title": "Cloud consultants",
            "body": "Give cloud clients a product that observes the external platforms they already depend on.",
        },
        {
            "id": "msp",
            "title": "MSPs",
            "body": "Monitor external dependencies across the infrastructure you already manage for clients.",
        },
        {
            "id": "agency",
            "title": "Software agencies",
            "body": "Give clients independent evidence when a third-party service causes an incident.",
        },
        {
            "id": "security",
            "title": "Cybersecurity consultants",
            "body": "Add dependency evidence to operational resilience conversations you already have.",
        },
        {
            "id": "creators",
            "title": "Technical creators",
            "body": "Turn infrastructure education and recommendations into recurring commission on eligible referrals.",
        },
        {
            "id": "developers",
            "title": "Developers",
            "body": "Share RELIASTRA with teams that already ask you which vendor actually failed.",
        },
        {
            "id": "communities",
            "title": "Communities",
            "body": "Introduce accountability infrastructure to operators who already discuss outages together.",
        },
        {
            "id": "founders",
            "title": "Founders",
            "body": "Point peer companies at evidence when their checkout, auth or AI vendor degrades.",
        },
        {
            "id": "sales",
            "title": "Sales professionals",
            "body": "Introduce a concrete operational product, not an abstract monitoring pitch.",
        },
    ]


def _reasons() -> list[dict]:
    return [
        {
            "id": "real-product",
            "title": "REAL PRODUCT",
            "body": "You introduce actual accountability infrastructure: observation, correlation and evidence.",
        },
        {
            "id": "recurring",
            "title": "RECURRING ECONOMICS",
            "body": "Eligible collected customer revenue can generate ongoing commission under program terms.",
        },
        {
            "id": "introduction",
            "title": "EASY INTRODUCTION",
            "body": "Partners do not need to become infrastructure salespeople. They introduce a product into a conversation they already have.",
        },
        {
            "id": "credibility",
            "title": "PUBLIC CREDIBILITY",
            "body": "RELIASTRA publishes vendor intelligence and evidence-driven infrastructure positioning.",
        },
        {
            "id": "agency",
            "title": "AGENCY POTENTIAL",
            "body": "Agencies can introduce RELIASTRA across clients. White-label rebranding is not a live partner API.",
        },
    ]


def _resources() -> list[dict]:
    """Catalog only. Downloadable files that do not exist are not invented."""
    return [
        {
            "id": "overview",
            "title": "RELIASTRA overview",
            "kind": "copy",
            "available": True,
            "body": (
                "RELIASTRA is external dependency intelligence and "
                "accountability infrastructure. Track vendor behaviour, "
                "correlate it with customer impact, and prove what happened "
                "when a dependency fails."
            ),
            "href": None,
        },
        {
            "id": "one-pager",
            "title": "Product one-pager",
            "kind": "asset",
            "available": False,
            "body": "A downloadable one-pager is not published yet.",
            "href": None,
        },
        {
            "id": "explainer",
            "title": "External Dependency Intelligence explainer",
            "kind": "copy",
            "available": True,
            "body": (
                "When Stripe, Cloudflare, Auth0, OpenAI or AWS degrades, "
                "someone has to determine whether the fault is internal or "
                "external. RELIASTRA independently observes those vendors "
                "and produces evidence."
            ),
            "href": None,
        },
        {
            "id": "agency-pitch",
            "title": "Agency introduction message",
            "kind": "copy",
            "available": True,
            "body": (
                "We use RELIASTRA to independently observe the vendors our "
                "clients depend on. When checkout, auth or an AI API fails "
                "and the vendor status page still says operational, we have "
                "correlated evidence to take into the escalation."
            ),
            "href": None,
        },
        {
            "id": "faq",
            "title": "FAQ",
            "kind": "copy",
            "available": True,
            "body": "Served from this program endpoint so commercial terms stay authoritative.",
            "href": None,
        },
    ]


def build_program_landing() -> dict:
    refer_bps = economics.default_rate_bps(EarningMethod.REFER.value)
    public_url = settings.RELIASTRA_PUBLIC_URL.rstrip("/")
    return {
        "product": {
            "name": "RELIASTRA",
            "positioning": "External Dependency Intelligence / Accountability Infrastructure",
            "flow": ["TRACK", "CORRELATE", "PROVE"],
            "monitors": [
                "external APIs",
                "cloud platforms",
                "payment providers",
                "identity systems",
                "AI APIs",
                "databases",
                "communications platforms",
            ],
            "customer_problem": (
                "When a critical vendor fails, someone has to determine "
                "whether the problem came from the customer's system or the "
                "vendor — and prove it."
            ),
        },
        "positioning": {
            "eyebrow": "RELIASTRA PARTNER NETWORK",
            "headline": "Earn from the infrastructure problems you already help solve.",
            "supporting": (
                "Introduce RELIASTRA to companies that depend on external APIs, "
                "cloud platforms, payment providers, identity systems and other "
                "critical vendors. Help them prove what happened when those "
                "dependencies fail — and earn recurring revenue when they "
                "become customers."
            ),
            "primary_cta": "BECOME A PARTNER",
            "secondary_cta": "SEE HOW IT WORKS",
            "trust_row": [
                f"{_bps_percent(refer_bps)} LIFETIME COMMISSION (refer method)",
                "NO COST TO JOIN",
                "TRACKED REFERRALS",
                "RECURRING REVENUE",
            ],
            "canonical_path": "/partners",
            "apply_path": "/partners/apply",
            "dashboard_path": "/partners/dashboard",
        },
        "how_it_works": [
            {
                "step": 1,
                "key": "join",
                "title": "JOIN",
                "body": "Create your account and submit a partner application.",
            },
            {
                "step": 2,
                "key": "share",
                "title": "SHARE",
                "body": "Use the unique referral URL the backend issues after approval.",
            },
            {
                "step": 3,
                "key": "convert",
                "title": "CONVERT",
                "body": "When a referred company becomes a paying customer, attribution is bound to your partner account.",
            },
            {
                "step": 4,
                "key": "earn",
                "title": "EARN",
                "body": "Receive the applicable commission on eligible collected revenue according to program terms.",
            },
        ],
        "onboarding": [
            {"key": "introduction", "title": "Introduction"},
            {"key": "authenticate", "title": "Account creation / authentication"},
            {"key": "apply", "title": "Partner application"},
            {"key": "review", "title": "Review / approval"},
            {"key": "link", "title": "Referral link issued"},
            {"key": "dashboard", "title": "Partner dashboard"},
        ],
        "audiences": _audiences(),
        "reasons": _reasons(),
        "scenario": {
            "title": "A realistic introduction",
            "body": (
                "A software agency manages infrastructure for 14 SaaS clients. "
                "One client's checkout begins failing. Internal systems look "
                "healthy. Stripe's public status page reports operational. "
                "RELIASTRA independently observes elevated Stripe latency "
                "across multiple regions. The agency uses the evidence during "
                "the vendor escalation. The customer subscribes. The partner "
                "receives recurring commission on eligible collected revenue."
            ),
        },
        "diagnostic": {
            "question": (
                "Do you regularly work with companies that depend on "
                "third-party APIs, cloud infrastructure, payments, "
                "authentication, AI APIs, databases or communications platforms?"
            ),
            "yes": "You have a reason to introduce RELIASTRA.",
            "no": "You may not need the program yet.",
        },
        "seo": {
            "title": "RELIASTRA Partner Network — Earn Recurring Revenue",
            "description": (
                "Join the RELIASTRA Partner Network. Introduce accountability "
                "infrastructure to companies that depend on external APIs, "
                "cloud services and critical vendors, and earn recurring "
                "revenue from eligible referrals."
            ),
            "canonical_url": f"{public_url}/partners",
            "og_title": "RELIASTRA Partner Network",
            "og_description": (
                "You already know the companies. RELIASTRA gives you something "
                "valuable to introduce."
            ),
        },
        "faq": _faq(),
        "resources": _resources(),
        "commission_illustration": _illustration(),
        "empty_states": {
            "referrals": (
                "Your network is ready. Share your referral link to start "
                "generating referrals."
            ),
            "commissions": (
                "Commission activity will appear here when eligible referred "
                "customers generate commission."
            ),
        },
        "frontend_endpoints": {
            "program": "GET /v1/partner-program",
            "content": "GET /v1/partner-program/content",
            "apply": "POST /v1/partners/apply",
            "applications": "GET /v1/partners/applications",
            "me": "GET /v1/partners/me",
            "dashboard": "GET /v1/partners/me/dashboard",
            "analytics": "GET /v1/partners/me/analytics",
            "links": "GET /v1/partners/me/links",
            "resources": "GET /v1/partners/me/resources",
            "commissions": "GET /v1/partners/me/commissions",
            "balance": "GET /v1/partners/me/commissions/balance",
            "customers": "GET /v1/partners/me/customers",
            "payouts": "GET /v1/partners/me/payouts",
            "resolve": "GET /v1/referral/{partner_code}",
        },
    }


__all__ = ["build_program_landing", "_bps_percent"]
