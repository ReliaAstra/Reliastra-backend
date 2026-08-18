"""Integration tests for the Partner Network API.

Coverage is organised around the things that would actually hurt if they
broke:

* the full lifecycle (apply → approve → code → link → campaign → click →
  attribution → signup → payment → commission → hold → payable → payout);
* cross-partner authorisation — every ownership-scoped endpoint denies
  access to another partner's data;
* commission correctness and immutability;
* payout idempotency and the minimum threshold;
* privacy: masked customer emails, masked payout accounts;
* public endpoints leaking nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.partners.constants import CommissionStatus, EarningMethod
from app.modules.partners.models import PartnerCommission

#: A realistic desktop browser User-Agent. Tests that care about click
#: *counts* must send one, because obvious automation (including the
#: default httpx UA) is intentionally excluded from partner analytics.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ══════════════════════════════ helpers ══════════════════════════════════


async def _register(
    client: AsyncClient, email: str, name: str = "Test Person", **extra: Any
) -> dict[str, Any]:
    payload = {
        "email": email,
        "password": "SecurePassword123!",
        "full_name": name,
        "org_name": f"{name} Org",
        **extra,
    }
    res = await client.post("/v1/auth/register", json=payload)
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/v1/users/me", headers=headers)
    orgs = await client.get("/v1/orgs", headers=headers)
    return {
        "headers": headers,
        "user_id": me.json()["id"],
        "email": email,
        "org_id": orgs.json()[0]["id"],
    }


async def _make_system_admin(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        text("UPDATE users SET is_system_admin = TRUE WHERE id = :uid"),
        {"uid": uuid.UUID(user_id)},
    )
    await session.commit()


def _application_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "partner_type": "consultant",
        "display_name": "Acme Consulting",
        "contact_email": "hello@acme.example.com",
        "country_code": "NG",
        "intended_methods": ["refer", "deploy"],
        "audience_description": "SRE teams in West Africa",
        "accept_agreement": True,
    }
    payload.update(overrides)
    return payload


async def _approve_partner(
    client: AsyncClient,
    session: AsyncSession,
    applicant: dict[str, Any],
    admin: dict[str, Any],
    **application_overrides: Any,
) -> dict[str, Any]:
    """Apply as ``applicant`` and approve as ``admin``; return the partner."""
    res = await client.post(
        "/v1/partners/apply",
        json=_application_payload(**application_overrides),
        headers=applicant["headers"],
    )
    assert res.status_code == 201, res.text
    application_id = res.json()["id"]

    review = await client.post(
        f"/v1/admin/partners/applications/{application_id}/review",
        json={"approve": True},
        headers=admin["headers"],
    )
    assert review.status_code == 200, review.text

    me = await client.get("/v1/partners/me", headers=applicant["headers"])
    assert me.status_code == 200, me.text
    return me.json()


@pytest_asyncio.fixture
async def admin_user(async_client: AsyncClient, db_session: AsyncSession):
    data = await _register(async_client, "admin@reliastra.example.com", "Admin User")
    await _make_system_admin(db_session, data["user_id"])
    return data


@pytest_asyncio.fixture
async def partner_a(async_client: AsyncClient, db_session: AsyncSession, admin_user):
    applicant = await _register(async_client, "partner-a@example.com", "Partner A")
    partner = await _approve_partner(
        async_client, db_session, applicant, admin_user, display_name="Partner A Co"
    )
    return {**applicant, "partner": partner}


@pytest_asyncio.fixture
async def partner_b(async_client: AsyncClient, db_session: AsyncSession, admin_user):
    applicant = await _register(async_client, "partner-b@example.com", "Partner B")
    partner = await _approve_partner(
        async_client, db_session, applicant, admin_user, display_name="Partner B Co"
    )
    return {**applicant, "partner": partner}


# ═══════════════════════════ Applications ════════════════════════════════


class TestPartnerApplication:
    async def test_apply_creates_a_submitted_application(
        self, async_client: AsyncClient, auth_data
    ):
        res = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(),
            headers=auth_data["headers"],
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["status"] == "submitted"
        assert body["partner_type"] == "consultant"
        assert body["submitted_at"] is not None

    async def test_apply_requires_accepting_the_agreement(
        self, async_client: AsyncClient, auth_data
    ):
        res = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(accept_agreement=False),
            headers=auth_data["headers"],
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_cannot_apply_twice_while_under_review(
        self, async_client: AsyncClient, auth_data
    ):
        first = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(),
            headers=auth_data["headers"],
        )
        assert first.status_code == 201
        second = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(),
            headers=auth_data["headers"],
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    async def test_application_requires_authentication(
        self, async_client: AsyncClient
    ):
        res = await async_client.post("/v1/partners/apply", json=_application_payload())
        assert res.status_code in (401, 403)

    async def test_approval_provisions_a_partner_with_a_code_and_link(
        self, async_client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        applicant = await _register(async_client, "new-partner@example.com", "New P")
        partner = await _approve_partner(
            async_client, db_session, applicant, admin_user
        )

        assert partner["status"] == "active"
        assert partner["tier"] == "explorer"
        assert len(partner["partner_code"]) == 8
        assert partner["referral_url"] == (
            f"https://reliastra.com/r/{partner['partner_code']}"
        )
        assert partner["slug"]
        # Approval is not a self-listing: the directory stays opt-in.
        assert partner["is_publicly_listed"] is False

    async def test_rejection_records_the_reason_and_creates_no_partner(
        self, async_client: AsyncClient, admin_user
    ):
        applicant = await _register(async_client, "rejected@example.com", "Rejected")
        res = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(),
            headers=applicant["headers"],
        )
        application_id = res.json()["id"]

        review = await async_client.post(
            f"/v1/admin/partners/applications/{application_id}/review",
            json={"approve": False, "rejection_reason": "Insufficient audience"},
            headers=admin_user["headers"],
        )
        assert review.status_code == 200
        assert review.json()["status"] == "rejected"
        assert review.json()["rejection_reason"] == "Insufficient audience"

        me = await async_client.get("/v1/partners/me", headers=applicant["headers"])
        assert me.status_code == 404

    async def test_non_admin_cannot_review_applications(
        self, async_client: AsyncClient, auth_data
    ):
        res = await async_client.post(
            "/v1/partners/apply",
            json=_application_payload(),
            headers=auth_data["headers"],
        )
        application_id = res.json()["id"]

        review = await async_client.post(
            f"/v1/admin/partners/applications/{application_id}/review",
            json={"approve": True},
            headers=auth_data["headers"],
        )
        assert review.status_code == 403


# ═════════════════════════════ Profile ═══════════════════════════════════


class TestPartnerProfile:
    async def test_partner_sees_their_own_profile(self, async_client, partner_a):
        res = await async_client.get("/v1/partners/me", headers=partner_a["headers"])
        assert res.status_code == 200
        assert res.json()["display_name"] == "Partner A Co"

    async def test_users_without_a_partner_account_get_404(
        self, async_client, auth_data
    ):
        res = await async_client.get("/v1/partners/me", headers=auth_data["headers"])
        assert res.status_code == 404

    async def test_profile_update_cannot_escalate_tier_or_status(
        self, async_client, partner_a
    ):
        res = await async_client.patch(
            "/v1/partners/me",
            json={
                "headline": "West Africa reliability specialists",
                "tier": "strategic",
                "status": "active",
                "risk_score": 0,
                "custom_rate_bps": {"refer": 9000},
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 200
        body = res.json()
        assert body["headline"] == "West Africa reliability specialists"
        # The forbidden fields are simply not part of the schema.
        assert body["tier"] == "explorer"

    async def test_capabilities_describe_the_tier_without_promising_rates(
        self, async_client, partner_a
    ):
        res = await async_client.get(
            "/v1/partners/me/capabilities", headers=partner_a["headers"]
        )
        assert res.status_code == 200
        body = res.json()
        assert body["tier"] == "explorer"
        assert isinstance(body["capabilities"], list)
        assert body["next_tier"] == "partner"
        # Tiers must never carry a rate multiplier.
        assert "rate" not in str(body["capabilities"]).lower()


# ══════════════════════ Campaigns & referral links ═══════════════════════


class TestCampaignsAndLinks:
    async def test_campaign_link_matches_the_canonical_shape(
        self, async_client, partner_a
    ):
        res = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Summer Launch", "campaign_code": "SUMMER"},
            headers=partner_a["headers"],
        )
        assert res.status_code == 201, res.text
        body = res.json()
        code = partner_a["partner"]["partner_code"]
        assert body["campaign_code"] == "SUMMER"
        assert body["referral_url"] == (
            f"https://reliastra.com/r/{code}?campaign=SUMMER"
        )

    async def test_duplicate_campaign_code_is_rejected(
        self, async_client, partner_a
    ):
        await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "First", "campaign_code": "DUPE"},
            headers=partner_a["headers"],
        )
        second = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Second", "campaign_code": "DUPE"},
            headers=partner_a["headers"],
        )
        assert second.status_code == 409

    async def test_two_partners_may_use_the_same_campaign_code(
        self, async_client, partner_a, partner_b
    ):
        """Campaign codes are namespaced per partner, not globally."""
        a = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Launch", "campaign_code": "LAUNCH"},
            headers=partner_a["headers"],
        )
        b = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Launch", "campaign_code": "LAUNCH"},
            headers=partner_b["headers"],
        )
        assert a.status_code == 201
        assert b.status_code == 201
        assert a.json()["referral_url"] != b.json()["referral_url"]

    async def test_link_creation_returns_a_ready_to_share_url(
        self, async_client, partner_a
    ):
        campaign = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Newsletter"},
            headers=partner_a["headers"],
        )
        res = await async_client.post(
            "/v1/partners/me/links",
            json={
                "label": "Footer link",
                "campaign_id": campaign.json()["id"],
                "destination_path": "/pricing",
                "utm": {"utm_source": "newsletter"},
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["url"].startswith(
            f"https://reliastra.com/r/{partner_a['partner']['partner_code']}"
        )
        assert "utm_source=newsletter" in body["url"]
        assert body["qr_payload"] == body["url"]

    async def test_link_destination_cannot_be_an_absolute_url(
        self, async_client, partner_a
    ):
        res = await async_client.post(
            "/v1/partners/me/links",
            json={"destination_path": "https://evil.example.com"},
            headers=partner_a["headers"],
        )
        assert res.status_code == 422


# ═══════════════════ Cross-partner authorization denial ══════════════════


class TestCrossPartnerAuthorization:
    """A partner must never reach another partner's resources.

    Each case asserts 404 rather than 403: revealing that a resource exists
    but belongs to someone else is itself a leak.
    """

    async def test_cannot_read_another_partners_campaign(
        self, async_client, partner_a, partner_b
    ):
        created = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "A's campaign"},
            headers=partner_a["headers"],
        )
        campaign_id = created.json()["id"]

        res = await async_client.get(
            f"/v1/partners/me/campaigns/{campaign_id}", headers=partner_b["headers"]
        )
        assert res.status_code == 404

    async def test_cannot_update_another_partners_campaign(
        self, async_client, partner_a, partner_b
    ):
        created = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "A's campaign"},
            headers=partner_a["headers"],
        )
        res = await async_client.patch(
            f"/v1/partners/me/campaigns/{created.json()['id']}",
            json={"name": "hijacked"},
            headers=partner_b["headers"],
        )
        assert res.status_code == 404

    async def test_cannot_delete_another_partners_campaign(
        self, async_client, partner_a, partner_b
    ):
        created = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "A's campaign"},
            headers=partner_a["headers"],
        )
        res = await async_client.delete(
            f"/v1/partners/me/campaigns/{created.json()['id']}",
            headers=partner_b["headers"],
        )
        assert res.status_code == 404

    async def test_cannot_update_another_partners_link(
        self, async_client, partner_a, partner_b
    ):
        created = await async_client.post(
            "/v1/partners/me/links",
            json={"label": "A's link"},
            headers=partner_a["headers"],
        )
        res = await async_client.patch(
            f"/v1/partners/me/links/{created.json()['id']}",
            json={"label": "hijacked"},
            headers=partner_b["headers"],
        )
        assert res.status_code == 404

    async def test_campaign_listing_is_scoped_to_the_caller(
        self, async_client, partner_a, partner_b
    ):
        await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "A only"},
            headers=partner_a["headers"],
        )
        res = await async_client.get(
            "/v1/partners/me/campaigns", headers=partner_b["headers"]
        )
        assert res.status_code == 200
        assert res.json()["total"] == 0

    async def test_cannot_read_another_partners_lead(
        self, async_client, partner_a, partner_b
    ):
        created = await async_client.post(
            "/v1/partners/me/leads",
            json={
                "company_name": "Prospect Ltd",
                "contact_name": "Jane Prospect",
                "contact_email": "jane@prospect.example.com",
                "consent_confirmed": True,
            },
            headers=partner_a["headers"],
        )
        assert created.status_code == 201, created.text
        res = await async_client.get(
            f"/v1/partners/me/leads/{created.json()['id']}",
            headers=partner_b["headers"],
        )
        assert res.status_code == 404

    async def test_cannot_read_another_partners_commission_events(
        self, async_client, partner_a, partner_b, db_session, commission_factory
    ):
        commission = await commission_factory(partner_a)
        res = await async_client.get(
            f"/v1/partners/me/commissions/{commission.id}/events",
            headers=partner_b["headers"],
        )
        assert res.status_code == 404

    async def test_partner_endpoints_reject_admin_only_operations(
        self, async_client, partner_a
    ):
        res = await async_client.get(
            "/v1/admin/partners", headers=partner_a["headers"]
        )
        assert res.status_code == 403


# ═══════════════════════ Public referral resolution ══════════════════════


class TestPublicReferral:
    async def test_resolution_returns_destination_and_visitor_id(
        self, async_client, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        res = await async_client.get(f"/v1/public/referral/{code}")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["partner_code"] == code
        assert body["is_valid"] is True
        assert body["visitor_id"]
        assert body["attribution_window_days"] == 90
        assert body["destination_path"] == "/"

    async def test_resolution_needs_no_authentication(
        self, async_client, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        res = await async_client.get(f"/v1/public/referral/{code}")
        assert res.status_code == 200

    async def test_resolution_is_case_insensitive(self, async_client, partner_a):
        code = partner_a["partner"]["partner_code"]
        res = await async_client.get(f"/v1/public/referral/{code.lower()}")
        assert res.status_code == 200
        assert res.json()["partner_code"] == code

    async def test_unknown_code_returns_404_in_the_standard_envelope(
        self, async_client
    ):
        res = await async_client.get("/v1/public/referral/NOSUCHCODE")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    async def test_resolution_reveals_no_partner_pii(
        self, async_client, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        body = (await async_client.get(f"/v1/public/referral/{code}")).json()
        blob = str(body).lower()
        assert "partner-a@example.com" not in blob
        assert "hello@acme.example.com" not in blob
        assert "lifetime" not in blob
        assert "commission" not in blob

    async def test_campaign_is_carried_through_resolution(
        self, async_client, partner_a
    ):
        await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Promo", "campaign_code": "PROMO"},
            headers=partner_a["headers"],
        )
        code = partner_a["partner"]["partner_code"]
        res = await async_client.get(
            f"/v1/public/referral/{code}", params={"campaign": "PROMO"}
        )
        assert res.status_code == 200
        assert res.json()["campaign_code"] == "PROMO"

    async def test_validate_reports_invalid_codes_without_erroring(
        self, async_client
    ):
        res = await async_client.get("/v1/public/referral/NOPE/validate")
        assert res.status_code == 200
        assert res.json()["is_valid"] is False
        assert res.json()["reason"] == "unknown_code"

    async def test_automated_traffic_is_excluded_from_reported_clicks(
        self, async_client, db_session, partner_a
    ):
        """Crawlers still resolve, but must not inflate a partner's numbers."""
        code = partner_a["partner"]["partner_code"]
        await async_client.get(
            f"/v1/public/referral/{code}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
        )
        await async_client.get(
            f"/v1/public/referral/{code}", headers={"User-Agent": BROWSER_UA}
        )

        from app.modules.partners.repository import ClickRepository

        partner_id = uuid.UUID(partner_a["partner"]["id"])
        # Two raw events are stored; only the human one is counted.
        assert await ClickRepository.count_for_partner(db_session, partner_id) == 1
        assert (
            await ClickRepository.count_for_partner(
                db_session, partner_id, include_bots=True
            )
            == 2
        )

    async def test_repeat_clicks_are_deduplicated_for_counting(
        self, async_client, db_session, partner_a
    ):
        """A visitor refreshing the link does not multiply their clicks."""
        code = partner_a["partner"]["partner_code"]
        first = (
            await async_client.get(
                f"/v1/public/referral/{code}", headers={"User-Agent": BROWSER_UA}
            )
        ).json()
        for _ in range(3):
            await async_client.get(
                f"/v1/public/referral/{code}",
                params={"visitor_id": first["visitor_id"]},
                headers={"User-Agent": BROWSER_UA},
            )

        from app.modules.partners.repository import ClickRepository

        assert (
            await ClickRepository.count_for_partner(
                db_session, uuid.UUID(partner_a["partner"]["id"])
            )
            == 1
        )

    async def test_utm_parameters_never_change_partner_ownership(
        self, async_client, partner_a, partner_b
    ):
        """A crafted utm_source must not steal the click for someone else."""
        code_a = partner_a["partner"]["partner_code"]
        res = await async_client.get(
            f"/v1/public/referral/{code_a}",
            params={
                "utm_source": partner_b["partner"]["partner_code"],
                "utm_campaign": "steal",
            },
        )
        assert res.status_code == 200
        assert res.json()["partner_code"] == code_a


class TestPublicDirectory:
    async def test_unlisted_partners_are_invisible(self, async_client, partner_a):
        res = await async_client.get(
            f"/v1/public/partners/{partner_a['partner']['slug']}"
        )
        assert res.status_code == 404

    async def test_opted_in_partner_appears_with_marketing_data_only(
        self, async_client, partner_a
    ):
        await async_client.patch(
            "/v1/partners/me",
            json={"is_publicly_listed": True, "headline": "Reliability people"},
            headers=partner_a["headers"],
        )
        res = await async_client.get(
            f"/v1/public/partners/{partner_a['partner']['slug']}"
        )
        assert res.status_code == 200
        body = res.json()
        assert body["display_name"] == "Partner A Co"
        assert body["headline"] == "Reliability people"
        # No contact, financial or risk data may appear.
        for leaked in ("contact_email", "lifetime_revenue_minor", "risk_score"):
            assert leaked not in body

    async def test_program_endpoint_serves_economics_from_configuration(
        self, async_client
    ):
        res = await async_client.get("/v1/public/partner-program")
        assert res.status_code == 200
        body = res.json()
        rates = {m["method"]: m["rate_bps"] for m in body["earning_methods"]}
        assert rates == {
            "refer": 2000,
            "deploy": 3000,
            "create": 2500,
            "introduce": 1500,
            "resell": 0,
        }
        assert body["attribution_window_days"] == 90
        assert body["commission_hold_days"] == 30
        assert body["min_payout_minor"] == 5000
        assert body["max_total_commission_bps"] == 5000


# ═══════════════════════ Attribution through signup ══════════════════════


class TestAttribution:
    async def test_click_then_signup_attributes_the_new_user(
        self, async_client, db_session, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        resolved = (await async_client.get(f"/v1/public/referral/{code}")).json()

        referred = await _register(
            async_client,
            "referred@example.com",
            "Referred User",
            partner_visitor_id=resolved["visitor_id"],
        )

        from app.modules.partners.repository import AttributionRepository

        attribution = await AttributionRepository.get_active_for_user(
            db_session, uuid.UUID(referred["user_id"])
        )
        assert attribution is not None
        assert str(attribution.partner_id) == partner_a["partner"]["id"]

    async def test_signup_with_a_typed_partner_code_also_attributes(
        self, async_client, db_session, partner_a
    ):
        referred = await _register(
            async_client,
            "typed-code@example.com",
            "Typed Code",
            partner_code=partner_a["partner"]["partner_code"],
        )
        from app.modules.partners.repository import AttributionRepository

        attribution = await AttributionRepository.get_active_for_user(
            db_session, uuid.UUID(referred["user_id"])
        )
        assert attribution is not None

    async def test_partner_cannot_attribute_their_own_signup(
        self, async_client, db_session, partner_a
    ):
        """Self-referral is voided rather than silently earning."""
        code = partner_a["partner"]["partner_code"]
        resolved = (await async_client.get(f"/v1/public/referral/{code}")).json()

        from app.modules.partners.tracking import tracking_service

        result = await tracking_service.bind_signup(
            db_session,
            user_id=uuid.UUID(partner_a["user_id"]),
            organization_id=uuid.UUID(partner_a["org_id"]),
            visitor_id=resolved["visitor_id"],
        )
        assert result is None

    async def test_last_touch_wins_when_two_partners_are_clicked(
        self, async_client, db_session, partner_a, partner_b
    ):
        first = (
            await async_client.get(
                f"/v1/public/referral/{partner_a['partner']['partner_code']}"
            )
        ).json()
        # Same visitor now clicks partner B's link.
        second = await async_client.get(
            f"/v1/public/referral/{partner_b['partner']['partner_code']}",
            params={"visitor_id": first["visitor_id"]},
        )
        assert second.status_code == 200

        referred = await _register(
            async_client,
            "last-touch@example.com",
            "Last Touch",
            partner_visitor_id=first["visitor_id"],
        )
        from app.modules.partners.repository import AttributionRepository

        attribution = await AttributionRepository.get_active_for_user(
            db_session, uuid.UUID(referred["user_id"])
        )
        assert str(attribution.partner_id) == partner_b["partner"]["id"]

    async def test_registration_survives_a_bogus_visitor_id(
        self, async_client
    ):
        """Attribution must never be able to fail a signup."""
        data = await _register(
            async_client,
            "bogus-visitor@example.com",
            "Bogus Visitor",
            partner_visitor_id="not-a-real-visitor-id",
        )
        assert data["user_id"]

    async def test_existing_plg_referral_flow_still_works(
        self, async_client, auth_data, db_session
    ):
        """The partner system must not break the peer referral programme."""
        info = await async_client.get(
            "/v1/referrals/my-referral", headers=auth_data["headers"]
        )
        assert info.status_code == 200
        ref_code = info.json()["referral_code"]

        referred = await _register(
            async_client, "plg-referred@example.com", "PLG Referred", ref_code=ref_code
        )
        assert referred["user_id"]

        from app.modules.referrals.models import Referral

        rows = (
            await db_session.execute(
                select(Referral).where(
                    Referral.referred_id == uuid.UUID(referred["user_id"])
                )
            )
        ).scalars().all()
        assert len(rows) == 1


# ══════════════════════════ Commission ledger ════════════════════════════


@pytest_asyncio.fixture
def commission_factory(db_session: AsyncSession):
    """Create a real earning relationship and accrue a commission on it."""

    async def _factory(
        partner_ctx: dict[str, Any],
        *,
        collected_minor: int = 4900,
        method: str = EarningMethod.REFER.value,
        reference: str | None = None,
        customer_org_id: uuid.UUID | None = None,
    ) -> PartnerCommission:
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.service import partner_service

        partner_id = uuid.UUID(partner_ctx["partner"]["id"])
        org_id = customer_org_id or uuid.UUID(partner_ctx["org_id"])
        now = datetime.now(timezone.utc)

        await partner_service.ensure_relationship(
            db_session,
            partner_id=partner_id,
            organization_id=org_id,
            earning_method=method,
            started_at=now,
        )
        created = await commission_service.record_payment(
            db_session,
            organization_id=org_id,
            collected_minor=collected_minor,
            currency="USD",
            payment_reference=reference or f"pay_{uuid.uuid4().hex[:12]}",
            paid_at=now,
        )
        await db_session.commit()
        return created[0]

    return _factory


class TestCommissionLedger:
    async def test_payment_accrues_a_pending_commission_at_the_right_rate(
        self, async_client, db_session, partner_a, commission_factory
    ):
        commission = await commission_factory(partner_a, collected_minor=4900)
        assert commission.amount_minor == 980           # $49.00 @ 20%
        assert commission.rate_bps == 2000
        assert commission.status == CommissionStatus.PENDING.value
        assert commission.currency == "USD"
        assert commission.payable_at is not None        # 30-day hold set
        assert commission.calculation_basis["formula"]

    async def test_commission_creation_is_idempotent_per_payment(
        self, db_session, partner_a, commission_factory
    ):
        """A replayed webhook must not pay the partner twice."""
        from app.modules.partners.commissions import commission_service

        reference = "pay_replayed_reference"
        first = await commission_factory(partner_a, reference=reference)

        again = await commission_service.record_payment(
            db_session,
            organization_id=uuid.UUID(partner_a["org_id"]),
            collected_minor=4900,
            currency="USD",
            payment_reference=reference,
            paid_at=datetime.now(timezone.utc),
        )
        await db_session.commit()

        assert len(again) == 1
        assert again[0].id == first.id

        rows = (
            await db_session.execute(
                select(PartnerCommission).where(
                    PartnerCommission.source_reference == reference
                )
            )
        ).scalars().all()
        assert len(rows) == 1

    async def test_partner_sees_their_ledger_and_balance(
        self, async_client, partner_a, commission_factory
    ):
        await commission_factory(partner_a)

        listing = await async_client.get(
            "/v1/partners/me/commissions", headers=partner_a["headers"]
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 1

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert balance.status_code == 200
        body = balance.json()
        assert body["pending_minor"] == 980
        assert body["payable_minor"] == 0
        assert body["can_request_payout"] is False
        assert body["min_payout_minor"] == 5000

    async def test_hold_release_promotes_only_matured_commissions(
        self, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a)

        # Nothing is due yet.
        assert await commission_service.release_due_holds(db_session) == 0
        await db_session.refresh(commission)
        assert commission.status == CommissionStatus.PENDING.value

        # Wind the clock past the holding period.
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()

        assert await commission_service.release_due_holds(db_session) == 1
        await db_session.refresh(commission)
        assert commission.status == CommissionStatus.PAYABLE.value
        assert commission.became_payable_at is not None

    async def test_every_transition_is_journalled(
        self, async_client, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        res = await async_client.get(
            f"/v1/partners/me/commissions/{commission.id}/events",
            headers=partner_a["headers"],
        )
        assert res.status_code == 200
        events = res.json()
        assert [e["to_status"] for e in events] == ["pending", "payable"]
        assert events[-1]["reason"] == "holding_period_elapsed"

    async def test_refund_writes_a_reversal_and_never_edits_the_original(
        self, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        original = await commission_factory(partner_a, collected_minor=4900)
        original_amount = original.amount_minor

        reversal = await commission_service.reverse_commission(
            db_session, original, reason="refund"
        )
        await db_session.commit()

        assert reversal.amount_minor == -original_amount
        assert reversal.reverses_id == original.id
        assert reversal.entry_type == "reversal"

        await db_session.refresh(original)
        # The original keeps its amount; only its status moved.
        assert original.amount_minor == original_amount
        assert original.status == CommissionStatus.REVERSED.value

    async def test_partial_refund_reverses_proportionally(
        self, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        original = await commission_factory(partner_a, collected_minor=4900)
        reversal = await commission_service.reverse_commission(
            db_session, original, reason="refund", refunded_minor=2450
        )
        await db_session.commit()

        assert reversal.amount_minor == -490
        await db_session.refresh(original)
        # A partial refund leaves the original standing: some was earned.
        assert original.status != CommissionStatus.REVERSED.value

    async def test_reversal_is_idempotent(
        self, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        original = await commission_factory(partner_a)
        first = await commission_service.reverse_commission(
            db_session, original, reason="refund"
        )
        second = await commission_service.reverse_commission(
            db_session, original, reason="refund"
        )
        await db_session.commit()
        assert first.id == second.id

    async def test_balance_is_the_sum_of_the_ledger_after_a_reversal(
        self, async_client, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        first = await commission_factory(partner_a, collected_minor=4900)
        await commission_factory(
            partner_a, collected_minor=9900, reference="pay_second"
        )
        await commission_service.reverse_commission(
            db_session, first, reason="refund"
        )
        await db_session.commit()

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        body = balance.json()
        # 1980 still pending; the 980 accrual and its -980 reversal net out.
        assert body["pending_minor"] == 1980
        assert body["reversed_minor"] == 0

    async def test_two_partners_on_one_customer_respect_the_50_percent_cap(
        self, db_session, partner_a, partner_b
    ):
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.service import partner_service

        customer_org = uuid.UUID(partner_a["org_id"])
        now = datetime.now(timezone.utc)

        await partner_service.ensure_relationship(
            db_session,
            partner_id=uuid.UUID(partner_a["partner"]["id"]),
            organization_id=customer_org,
            earning_method=EarningMethod.DEPLOY.value,   # 30%
            started_at=now,
        )
        await partner_service.ensure_relationship(
            db_session,
            partner_id=uuid.UUID(partner_b["partner"]["id"]),
            organization_id=customer_org,
            earning_method=EarningMethod.CREATE.value,   # 25% -> capped
            started_at=now + timedelta(seconds=1),
        )

        created = await commission_service.record_payment(
            db_session,
            organization_id=customer_org,
            collected_minor=10_000,
            currency="USD",
            payment_reference="pay_shared_customer",
            paid_at=now,
        )
        await db_session.commit()

        assert len(created) == 2
        assert sum(c.rate_bps for c in created) == 5000
        assert sum(c.amount_minor for c in created) == 5000

    async def test_resell_relationship_accrues_nothing(
        self, db_session, partner_a
    ):
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.service import partner_service

        await partner_service.ensure_relationship(
            db_session,
            partner_id=uuid.UUID(partner_a["partner"]["id"]),
            organization_id=uuid.UUID(partner_a["org_id"]),
            earning_method=EarningMethod.RESELL.value,
            started_at=datetime.now(timezone.utc),
        )
        created = await commission_service.record_payment(
            db_session,
            organization_id=uuid.UUID(partner_a["org_id"]),
            collected_minor=100_000,
            currency="USD",
            payment_reference="pay_resell",
        )
        await db_session.commit()
        assert created == []

    async def test_clicks_alone_never_produce_commission(
        self, async_client, db_session, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        for _ in range(5):
            await async_client.get(f"/v1/public/referral/{code}")

        rows = (
            await db_session.execute(
                select(PartnerCommission).where(
                    PartnerCommission.partner_id
                    == uuid.UUID(partner_a["partner"]["id"])
                )
            )
        ).scalars().all()
        assert rows == []

    async def test_signup_alone_never_produces_commission(
        self, async_client, db_session, partner_a
    ):
        code = partner_a["partner"]["partner_code"]
        resolved = (await async_client.get(f"/v1/public/referral/{code}")).json()
        await _register(
            async_client,
            "signup-only@example.com",
            "Signup Only",
            partner_visitor_id=resolved["visitor_id"],
        )
        rows = (
            await db_session.execute(
                select(PartnerCommission).where(
                    PartnerCommission.partner_id
                    == uuid.UUID(partner_a["partner"]["id"])
                )
            )
        ).scalars().all()
        assert rows == []


# ═════════════════════════════ Payouts ═══════════════════════════════════


class TestPayouts:
    async def test_payout_account_is_stored_encrypted_and_returned_masked(
        self, async_client, db_session, partner_a
    ):
        res = await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "method": "paystack_transfer",
                "currency": "USD",
                "bank_name": "GTBank",
                "account_name": "Acme Consulting Ltd",
                "account_number": "0123456789",
                "bank_code": "058",
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["account_last4"] == "6789"
        assert body["display_label"] == "GTBank ••••6789"
        # The full number must not appear anywhere in the response.
        assert "0123456789" not in str(body)
        assert "encrypted_details" not in body

        # ...nor in plaintext in the database.
        stored = (
            await db_session.execute(
                text(
                    "SELECT encrypted_details FROM partner_payout_accounts "
                    "WHERE id = :id"
                ),
                {"id": uuid.UUID(body["id"])},
            )
        ).scalar_one()
        assert stored
        assert "0123456789" not in stored

    async def test_payout_below_the_threshold_is_refused(
        self, async_client, partner_a, commission_factory, db_session
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=4900)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        res = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert res.status_code == 422
        assert res.json()["error"]["details"]["min_payout_minor"] == 5000

    async def test_payout_requires_a_configured_account(
        self, async_client, partner_a, commission_factory, db_session
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        res = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert res.status_code == 422

    async def test_payout_pays_the_payable_balance_and_marks_it_paid(
        self, async_client, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        res = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["amount_minor"] == 20_000     # $1000.00 @ 20%
        assert body["status"] == "requested"
        assert body["commission_count"] == 1
        assert body["reference"].startswith("PPO-")

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert balance.json()["payable_minor"] == 0
        assert balance.json()["paid_minor"] == 20_000

    async def test_payout_is_idempotent_across_retries(
        self, async_client, db_session, partner_a, commission_factory
    ):
        """The same Idempotency-Key must never create a second payout."""
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        headers = {**partner_a["headers"], "Idempotency-Key": "payout-retry-001"}
        first = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=headers
        )
        second = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=headers
        )
        assert first.status_code == 201
        assert second.status_code in (200, 201)
        assert first.json()["id"] == second.json()["id"]

        listing = await async_client.get(
            "/v1/partners/me/payouts", headers=partner_a["headers"]
        )
        assert listing.json()["total"] == 1

    async def test_only_one_payout_may_be_in_flight(
        self, async_client, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        for i, amount in enumerate((100_000, 100_000)):
            commission = await commission_factory(
                partner_a, collected_minor=amount, reference=f"pay_multi_{i}"
            )
            commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        first = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**partner_a["headers"], "Idempotency-Key": "k1"},
        )
        assert first.status_code == 201
        second = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**partner_a["headers"], "Idempotency-Key": "k2"},
        )
        assert second.status_code == 409

    async def test_manual_transfer_can_be_marked_paid_directly(
        self, async_client, db_session, admin_user, partner_a, commission_factory
    ):
        """Bank/manual transfers settle out of band.

        An operator wires the money and then records it; forcing a
        `processing` hop would mean nothing for those methods.
        """
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        payout = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**partner_a["headers"], "Idempotency-Key": "manual-settle"},
        )
        payout_id = payout.json()["id"]

        approved = await async_client.post(
            f"/v1/admin/partners/payouts/{payout_id}/action",
            json={"action": "approve", "reason": "Verified"},
            headers=admin_user["headers"],
        )
        assert approved.json()["status"] == "approved"

        paid = await async_client.post(
            f"/v1/admin/partners/payouts/{payout_id}/action",
            json={"action": "mark_paid", "provider_reference": "TRF_001"},
            headers=admin_user["headers"],
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "paid"
        assert paid.json()["paid_at"] is not None
        assert paid.json()["provider_reference"] == "TRF_001"

    async def test_illegal_payout_transitions_are_refused(
        self, async_client, db_session, admin_user, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        payout = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**partner_a["headers"], "Idempotency-Key": "illegal-transition"},
        )
        payout_id = payout.json()["id"]

        # requested -> paid skips approval entirely.
        res = await async_client.post(
            f"/v1/admin/partners/payouts/{payout_id}/action",
            json={"action": "mark_paid"},
            headers=admin_user["headers"],
        )
        assert res.status_code == 409
        assert "approved" in res.json()["error"]["details"]["allowed"]

    async def test_a_failed_payout_returns_the_money_to_payable(
        self, async_client, db_session, admin_user, partner_a, commission_factory
    ):
        """A failed transfer must never swallow a partner's commissions."""
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(partner_a, collected_minor=100_000)
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_a["headers"],
        )
        payout = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**partner_a["headers"], "Idempotency-Key": "will-fail"},
        )
        payout_id = payout.json()["id"]

        after_request = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert after_request.json()["payable_minor"] == 0

        failed = await async_client.post(
            f"/v1/admin/partners/payouts/{payout_id}/action",
            json={"action": "fail", "reason": "Bank rejected the transfer"},
            headers=admin_user["headers"],
        )
        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"

        restored = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert restored.json()["payable_minor"] == 20_000

    async def test_cannot_list_another_partners_payouts(
        self, async_client, partner_a, partner_b
    ):
        res = await async_client.get(
            "/v1/partners/me/payouts", headers=partner_b["headers"]
        )
        assert res.status_code == 200
        assert res.json()["total"] == 0


# ═════════════════════════ Customers & privacy ═══════════════════════════


class TestPayoutReversalSafety:
    """Regressions for the payout/refund race (Strix HIGH finding).

    ``request_payout`` marks commissions ``paid`` at request time, before the
    transfer settles. If the underlying customer payment is refunded during
    that window, unwinding the payout must not hand the money back.
    """

    async def _payable_commission(
        self, async_client, db_session, partner_ctx, commission_factory, *, reference
    ):
        from app.modules.partners.commissions import commission_service

        commission = await commission_factory(
            partner_ctx, collected_minor=100_000, reference=reference
        )
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Acme",
                "account_number": "0123456789",
                "bank_name": "GTBank",
            },
            headers=partner_ctx["headers"],
        )
        return commission

    async def test_fully_refunded_commission_is_not_recredited_when_payout_fails(
        self, async_client, db_session, partner_a, commission_factory, admin_user
    ):
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.constants import ReversalReason
        from app.modules.partners.payouts import payout_service
        from app.modules.partners.repository import PayoutRepository

        await self._payable_commission(
            async_client,
            db_session,
            partner_a,
            commission_factory,
            reference="pay_refund_race",
        )

        created = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert created.status_code == 201, created.text
        assert created.json()["amount_minor"] == 20_000

        # The customer charges back while the transfer is still in flight.
        await commission_service.reverse_payment(
            db_session,
            payment_reference="pay_refund_race",
            reason=ReversalReason.CHARGEBACK,
        )
        await db_session.commit()

        # ...and then the transfer fails, unwinding the payout.
        payout = await PayoutRepository.get_by_id(
            db_session, uuid.UUID(created.json()["id"])
        )
        await payout_service.transition(
            db_session,
            payout,
            to_status="failed",
            actor_user_id=None,
            reason="bank rejected",
        )
        await db_session.commit()

        # The money is gone: it must NOT come back as payable.
        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert balance.json()["payable_minor"] == 0

        # And a second payout for the same money must be impossible.
        retry = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert retry.status_code == 422

    async def test_partial_refund_restores_only_the_unreversed_remainder(
        self, async_client, db_session, partner_a, commission_factory
    ):
        from app.modules.partners.commissions import commission_service
        from app.modules.partners.constants import ReversalReason
        from app.modules.partners.payouts import payout_service
        from app.modules.partners.repository import PayoutRepository

        await self._payable_commission(
            async_client,
            db_session,
            partner_a,
            commission_factory,
            reference="pay_partial_race",
        )

        created = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert created.json()["amount_minor"] == 20_000

        # Half the payment is refunded: 20% of 50_000 = 10_000 clawed back.
        await commission_service.reverse_payment(
            db_session,
            payment_reference="pay_partial_race",
            reason=ReversalReason.REFUND,
            refunded_minor=50_000,
        )
        await db_session.commit()

        payout = await PayoutRepository.get_by_id(
            db_session, uuid.UUID(created.json()["id"])
        )
        await payout_service.transition(
            db_session, payout, to_status="cancelled", actor_user_id=None
        )
        await db_session.commit()

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        # Only the half the partner is still owed returns to payable.
        assert balance.json()["payable_minor"] == 10_000

    async def test_unrefunded_payout_failure_still_restores_in_full(
        self, async_client, db_session, partner_a, commission_factory
    ):
        """The narrowing must not break the ordinary failure path."""
        from app.modules.partners.payouts import payout_service
        from app.modules.partners.repository import PayoutRepository

        await self._payable_commission(
            async_client,
            db_session,
            partner_a,
            commission_factory,
            reference="pay_clean_fail",
        )
        created = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        payout = await PayoutRepository.get_by_id(
            db_session, uuid.UUID(created.json()["id"])
        )
        await payout_service.transition(
            db_session,
            payout,
            to_status="failed",
            actor_user_id=None,
            reason="bank rejected",
        )
        await db_session.commit()

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=partner_a["headers"]
        )
        assert balance.json()["payable_minor"] == 20_000


class TestApiKeyCannotActAsPartner:
    """Regression for the org-API-key escalation (Strix MEDIUM finding).

    ``get_current_user`` maps an org API key onto that org's *owner*. Partner
    routes are user-bound and expose earnings and payout actions, so an
    org-scoped integration key must be refused.
    """

    async def _api_key(self, async_client, ctx) -> str:
        res = await async_client.post(
            f"/v1/orgs/{ctx['org_id']}/api-keys",
            json={
                "name": "ci-integration",
                "scopes": ["read:organizations", "write:organizations"],
            },
            headers=ctx["headers"],
        )
        assert res.status_code in (200, 201), res.text
        return res.json()["full_key"]

    async def test_api_key_cannot_read_partner_profile(
        self, async_client, partner_a
    ):
        key = await self._api_key(async_client, partner_a)
        res = await async_client.get("/v1/partners/me", headers={"X-API-Key": key})
        assert res.status_code == 403, res.text

    async def test_api_key_cannot_request_a_payout(self, async_client, partner_a):
        key = await self._api_key(async_client, partner_a)
        res = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers={"X-API-Key": key}
        )
        assert res.status_code == 403, res.text

    async def test_api_key_cannot_read_commissions(self, async_client, partner_a):
        key = await self._api_key(async_client, partner_a)
        res = await async_client.get(
            "/v1/partners/me/commissions", headers={"X-API-Key": key}
        )
        assert res.status_code == 403, res.text

    async def test_normal_jwt_access_still_works(self, async_client, partner_a):
        """The guard must not lock out legitimate partners."""
        res = await async_client.get("/v1/partners/me", headers=partner_a["headers"])
        assert res.status_code == 200


class TestCustomerPrivacy:
    async def test_referred_customer_emails_are_masked(
        self, async_client, db_session, partner_a
    ):
        from app.modules.partners.service import partner_service

        customer = await _register(
            async_client, "customer@bigco.example.com", "Big Co"
        )
        await partner_service.ensure_relationship(
            db_session,
            partner_id=uuid.UUID(partner_a["partner"]["id"]),
            organization_id=uuid.UUID(customer["org_id"]),
            earning_method=EarningMethod.REFER.value,
            started_at=datetime.now(timezone.utc),
        )
        await db_session.commit()

        res = await async_client.get(
            "/v1/partners/me/customers", headers=partner_a["headers"]
        )
        assert res.status_code == 200
        blob = str(res.json())
        assert "customer@bigco.example.com" not in blob

    async def test_customers_listing_is_scoped_to_the_caller(
        self, async_client, db_session, partner_a, partner_b
    ):
        from app.modules.partners.service import partner_service

        await partner_service.ensure_relationship(
            db_session,
            partner_id=uuid.UUID(partner_a["partner"]["id"]),
            organization_id=uuid.UUID(partner_a["org_id"]),
            earning_method=EarningMethod.REFER.value,
            started_at=datetime.now(timezone.utc),
        )
        await db_session.commit()

        res = await async_client.get(
            "/v1/partners/me/customers", headers=partner_b["headers"]
        )
        assert res.json()["total"] == 0


# ═══════════════════════════ Leads & claims ══════════════════════════════


class TestLeadsAndClaims:
    async def test_lead_requires_consent(self, async_client, partner_a):
        res = await async_client.post(
            "/v1/partners/me/leads",
            json={
                "company_name": "Prospect",
                "contact_name": "Jane",
                "contact_email": "jane@prospect.example.com",
                "consent_confirmed": False,
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 422

    async def test_lead_response_masks_the_contact_email(
        self, async_client, partner_a
    ):
        res = await async_client.post(
            "/v1/partners/me/leads",
            json={
                "company_name": "Prospect",
                "contact_name": "Jane",
                "contact_email": "jane.prospect@bigco.example.com",
                "consent_confirmed": True,
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 201
        body = res.json()
        assert body["masked_contact_email"] == "j•••t@bigco.example.com"
        assert "jane.prospect@bigco.example.com" not in str(body)

    async def test_duplicate_lead_across_partners_is_blocked_without_disclosure(
        self, async_client, partner_a, partner_b
    ):
        payload = {
            "company_name": "Contested Ltd",
            "contact_name": "Sam Contest",
            "contact_email": "sam@contested.example.com",
            "consent_confirmed": True,
        }
        first = await async_client.post(
            "/v1/partners/me/leads", json=payload, headers=partner_a["headers"]
        )
        assert first.status_code == 201

        second = await async_client.post(
            "/v1/partners/me/leads", json=payload, headers=partner_b["headers"]
        )
        assert second.status_code == 409
        # It says "taken", not "taken by Partner A".
        assert "Partner A" not in second.text
        # And it must not leak *whose* lead it is, not even as a boolean:
        # that would let a partner probe which prospects rivals hold.
        assert "is_own_lead" not in second.json()["error"].get("details", {})

        # The same partner resubmitting their own lead gets a byte-identical
        # response, so the conflict body carries no ownership signal at all.
        repeat = await async_client.post(
            "/v1/partners/me/leads", json=payload, headers=partner_a["headers"]
        )
        assert repeat.status_code == 409
        assert repeat.json()["error"]["details"] == second.json()["error"]["details"]
        assert repeat.json()["error"]["message"] == second.json()["error"]["message"]

    async def test_claim_requires_evidence(self, async_client, partner_a):
        res = await async_client.post(
            "/v1/partners/me/claims",
            json={
                "title": "Deployed monitoring for BigCo",
                "description": "A" * 30,
                "earning_method": "deploy",
                "evidence": [],
            },
            headers=partner_a["headers"],
        )
        assert res.status_code == 422

    async def test_approved_claim_creates_a_deploy_relationship(
        self, async_client, db_session, partner_a, admin_user
    ):
        customer = await _register(
            async_client, "claimed-customer@example.com", "Claimed Co"
        )
        created = await async_client.post(
            "/v1/partners/me/claims",
            json={
                "title": "Deployed monitoring for Claimed Co",
                "description": "Full rollout across 12 services and 3 regions.",
                "organization_id": customer["org_id"],
                "earning_method": "deploy",
                "evidence": [
                    {
                        "evidence_type": "url",
                        "title": "Runbook",
                        "url": "https://example.com/runbook",
                    }
                ],
            },
            headers=partner_a["headers"],
        )
        assert created.status_code == 201, created.text
        claim_id = created.json()["id"]
        assert len(created.json()["evidence"]) == 1

        review = await async_client.post(
            f"/v1/admin/partners/claims/{claim_id}/review",
            json={"approve": True, "review_notes": "Evidence checked"},
            headers=admin_user["headers"],
        )
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "approved"
        assert review.json()["relationship_id"] is not None

        from app.modules.partners.repository import RelationshipRepository

        relationship = await RelationshipRepository.get_for_org_and_method(
            db_session,
            uuid.UUID(customer["org_id"]),
            uuid.UUID(partner_a["partner"]["id"]),
            EarningMethod.DEPLOY.value,
        )
        assert relationship is not None
        assert relationship.rate_bps == 3000  # deploy rate, snapshotted


# ══════════════════════════ Admin operations ═════════════════════════════


class TestAdminOperations:
    async def test_admin_can_list_partners(self, async_client, admin_user, partner_a):
        res = await async_client.get(
            "/v1/admin/partners", headers=admin_user["headers"]
        )
        assert res.status_code == 200
        assert res.json()["total"] >= 1
        assert "risk_score" in res.json()["items"][0]

    async def test_suspension_holds_commissions(
        self, async_client, db_session, admin_user, partner_a, commission_factory
    ):
        await commission_factory(partner_a)

        res = await async_client.patch(
            f"/v1/admin/partners/{partner_a['partner']['id']}/status",
            json={"status": "suspended", "reason": "Under investigation"},
            headers=admin_user["headers"],
        )
        assert res.status_code == 200
        assert res.json()["commissions_held"] is True

        payout = await async_client.post(
            "/v1/partners/me/payouts", json={}, headers=partner_a["headers"]
        )
        assert payout.status_code == 409

    async def test_admin_reversal_writes_a_new_negative_entry(
        self, async_client, db_session, admin_user, partner_a, commission_factory
    ):
        commission = await commission_factory(partner_a)
        res = await async_client.post(
            f"/v1/admin/partners/commissions/{commission.id}/reverse",
            json={"reason": "chargeback", "notes": "Bank dispute"},
            headers=admin_user["headers"],
        )
        assert res.status_code == 200, res.text
        assert res.json()["amount_minor"] == -980
        assert res.json()["reverses_id"] == str(commission.id)

    async def test_admin_adjustment_is_immediately_payable_and_reasoned(
        self, async_client, admin_user, partner_a
    ):
        res = await async_client.post(
            "/v1/admin/partners/commissions/adjust",
            json={
                "partner_id": partner_a["partner"]["id"],
                "amount_minor": 2500,
                "currency": "USD",
                "reason": "Goodwill credit for a delayed payout",
            },
            headers=admin_user["headers"],
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["amount_minor"] == 2500
        assert body["status"] == "payable"
        assert body["entry_type"] == "adjustment"

    async def test_custom_rates_are_clamped_to_the_ceiling(
        self, async_client, admin_user, partner_a
    ):
        res = await async_client.patch(
            f"/v1/admin/partners/{partner_a['partner']['id']}/rates",
            json={
                "custom_rate_bps": {"refer": 9000},
                "reason": "Strategic agreement",
            },
            headers=admin_user["headers"],
        )
        assert res.status_code == 200
        assert res.json()["custom_rate_bps"]["refer"] == 5000

    async def test_manual_tier_change_is_recorded_in_history(
        self, async_client, admin_user, partner_a
    ):
        res = await async_client.patch(
            f"/v1/admin/partners/{partner_a['partner']['id']}/tier",
            json={"tier": "certified", "reason": "Completed certification"},
            headers=admin_user["headers"],
        )
        assert res.status_code == 200
        assert res.json()["to_tier"] == "certified"
        assert res.json()["is_automatic"] is False

        history = await async_client.get(
            "/v1/partners/me/tier-history", headers=partner_a["headers"]
        )
        assert history.status_code == 200
        assert history.json()[0]["to_tier"] == "certified"

    async def test_fraud_flags_endpoint_is_admin_only(
        self, async_client, partner_a, admin_user
    ):
        denied = await async_client.get(
            "/v1/admin/partners/fraud/flags", headers=partner_a["headers"]
        )
        assert denied.status_code == 403

        allowed = await async_client.get(
            "/v1/admin/partners/fraud/flags", headers=admin_user["headers"]
        )
        assert allowed.status_code == 200

    async def test_geo_endpoints_are_admin_only(self, async_client, partner_a, admin_user):
        assert (
            await async_client.get(
                "/v1/admin/geo/countries", headers=partner_a["headers"]
            )
        ).status_code == 403
        res = await async_client.get(
            "/v1/admin/geo/coverage", headers=admin_user["headers"]
        )
        assert res.status_code == 200
        assert "database_available" in res.json()


# ═════════════════════════ End-to-end lifecycle ══════════════════════════


class TestFullLifecycle:
    async def test_apply_to_payout_end_to_end(
        self, async_client, db_session, admin_user
    ):
        """apply → approve → link → campaign → click → signup → payment →
        commission → hold → payable → payout → ledger."""
        from app.modules.partners.commissions import commission_service

        # 1. Apply and get approved.
        applicant = await _register(async_client, "lifecycle@example.com", "Lifecycle")
        partner = await _approve_partner(
            async_client, db_session, applicant, admin_user
        )
        code = partner["partner_code"]

        # 2. Create a campaign and confirm the canonical URL.
        campaign = await async_client.post(
            "/v1/partners/me/campaigns",
            json={"name": "Q1 Push", "campaign_code": "Q1PUSH"},
            headers=applicant["headers"],
        )
        assert campaign.json()["referral_url"] == (
            f"https://reliastra.com/r/{code}?campaign=Q1PUSH"
        )

        # 3. A visitor clicks the campaign link. A realistic browser
        #    User-Agent matters: automated traffic is deliberately excluded
        #    from a partner's reported click counts.
        resolved = (
            await async_client.get(
                f"/v1/public/referral/{code}",
                params={"campaign": "Q1PUSH"},
                headers={"User-Agent": BROWSER_UA},
            )
        ).json()
        assert resolved["campaign_code"] == "Q1PUSH"

        # 4. The visitor signs up, replaying the visitor id.
        customer = await _register(
            async_client,
            "lifecycle-customer@example.com",
            "Lifecycle Customer",
            partner_visitor_id=resolved["visitor_id"],
        )

        # 5. The customer pays; attribution becomes a relationship and the
        #    payment accrues commission.
        from app.modules.partners.tracking import tracking_service

        await tracking_service.convert_attribution(
            db_session,
            organization_id=uuid.UUID(customer["org_id"]),
            user_id=uuid.UUID(customer["user_id"]),
        )
        created = await commission_service.record_payment(
            db_session,
            organization_id=uuid.UUID(customer["org_id"]),
            collected_minor=100_000,
            currency="USD",
            payment_reference="pay_lifecycle_001",
        )
        await db_session.commit()
        assert len(created) == 1
        commission = created[0]
        assert commission.amount_minor == 20_000
        assert commission.status == CommissionStatus.PENDING.value

        # 6. The hold elapses and the commission becomes payable.
        commission.payable_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()
        await commission_service.release_due_holds(db_session)
        await db_session.commit()

        balance = await async_client.get(
            "/v1/partners/me/commissions/balance", headers=applicant["headers"]
        )
        assert balance.json()["payable_minor"] == 20_000
        assert balance.json()["can_request_payout"] is True

        # 7. The partner adds an account and gets paid.
        await async_client.post(
            "/v1/partners/me/payout-accounts",
            json={
                "account_name": "Lifecycle Ltd",
                "account_number": "0987654321",
                "bank_name": "Zenith",
            },
            headers=applicant["headers"],
        )
        payout = await async_client.post(
            "/v1/partners/me/payouts",
            json={},
            headers={**applicant["headers"], "Idempotency-Key": "lifecycle-payout"},
        )
        assert payout.status_code == 201, payout.text
        assert payout.json()["amount_minor"] == 20_000

        # 8. The dashboard and ledger agree, and the admin can see it all.
        dashboard = await async_client.get(
            "/v1/partners/me/dashboard", headers=applicant["headers"]
        )
        assert dashboard.json()["paid_commission_minor"] == 20_000
        assert dashboard.json()["clicks_30d"] >= 1

        admin_view = await async_client.get(
            "/v1/admin/partners/commissions/all",
            params={"partner_id": partner["id"]},
            headers=admin_user["headers"],
        )
        assert admin_view.json()["total"] == 1
        assert admin_view.json()["items"][0]["calculation_basis"] is not None
