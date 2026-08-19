"""Integration tests for the lean Partner Referral program (v1).

Covers the full lifecycle from the acceptance criteria: activation, referral
binding, subscription commission, recurring billing, cancellation, refund,
idempotency, self-referral rejection, authorization, and payout.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.modules.partners.commissions import commission_service
from app.modules.partners.models import (
    PartnerCommission,
    PartnerPayout,
    PartnerProfile,
    PartnerReferral,
)
from app.modules.partners.service import partner_service
from app.modules.users.models import User


async def _register(async_client, email, full_name, ref_code=None):
    payload = {
        "email": email,
        "password": "SecurePassword123!",
        "full_name": full_name,
        "org_name": f"{full_name} Org",
    }
    if ref_code:
        payload["ref_code"] = ref_code
    res = await async_client.post("/v1/auth/register", json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    return {
        "token": body["tokens"]["access_token"],
        "headers": {"Authorization": f"Bearer {body['tokens']['access_token']}"},
        "user_id": body["user"]["id"],
        "org_id": body["organization"]["id"],
    }


async def _activate_partner(async_client, headers):
    res = await async_client.post(
        "/v1/partners/apply", json={"agree_terms": True}, headers=headers
    )
    assert res.status_code == 201, res.text
    return res.json()


# ── Activation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partner_activation(async_client):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])

    assert profile["status"] == "active"
    assert profile["commission_rate"] == 30
    assert profile["referral_code"]
    assert profile["referral_link"] == f"{settings.partner_referral_base_url}/{profile['referral_code']}"

    # Idempotent: applying again returns the same profile, not a duplicate.
    again = await _activate_partner(async_client, partner["headers"])
    assert again["partner_id"] == profile["partner_id"]
    assert again["referral_code"] == profile["referral_code"]


@pytest.mark.asyncio
async def test_partner_apply_requires_terms(async_client):
    partner = await _register(async_client, "bob@example.com", "Bob Builder")
    res = await async_client.post(
        "/v1/partners/apply", json={"agree_terms": False}, headers=partner["headers"]
    )
    assert res.status_code == 422, res.text


# ── Referral binding ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_referral_binding_on_registration(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])

    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    referral = (
        await db_session.execute(
            select(PartnerReferral).where(
                PartnerReferral.referred_user_id == customer["user_id"]
            )
        )
    ).scalar_one()
    assert str(referral.partner_id) == profile["partner_id"]
    assert referral.status == "signed_up"


@pytest.mark.asyncio
async def test_self_referral_rejected(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])

    # Directly attempt to bind the partner's own user as the referred user.
    result = await partner_service.bind_referral(
        db_session,
        referral_code=profile["referral_code"],
        new_user_id=uuid.UUID(partner["user_id"]),
        new_org_id=uuid.UUID(partner["org_id"]),
    )
    assert result is None


# ── Commission lifecycle ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscription_creates_commission(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-1",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    commissions = (
        await db_session.execute(
            select(PartnerCommission).where(
                PartnerCommission.partner_id == profile["partner_id"]
            )
        )
    ).scalars().all()
    assert len(commissions) == 1
    assert commissions[0].subscription_amount_minor == 4900
    assert commissions[0].commission_amount_minor == 1470  # 30% of $49
    assert commissions[0].rate == 30
    assert commissions[0].status == "pending"

    # Referral is promoted to a paying customer.
    referral = (
        await db_session.execute(
            select(PartnerReferral).where(
                PartnerReferral.referred_user_id == customer["user_id"]
            )
        )
    ).scalar_one()
    assert referral.status == "paid"
    assert referral.subscribed_at is not None


@pytest.mark.asyncio
async def test_recurring_billing_creates_recurring_commissions(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    for i in range(3):
        await commission_service.record_payment(
            db_session,
            organization_id=customer["org_id"],
            collected_minor=4900,
            currency="USD",
            payment_reference=f"ref-{i}",
            paid_at=datetime.now(timezone.utc),
        )
    await db_session.commit()

    commissions = (
        await db_session.execute(
            select(PartnerCommission).where(
                PartnerCommission.partner_id == profile["partner_id"]
            )
        )
    ).scalars().all()
    assert len(commissions) == 3


@pytest.mark.asyncio
async def test_duplicate_payment_event_creates_one_commission(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-dup",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()
    # Duplicate delivery of the same billing event.
    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-dup",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    commissions = (
        await db_session.execute(
            select(PartnerCommission).where(
                PartnerCommission.partner_id == profile["partner_id"]
            )
        )
    ).scalars().all()
    assert len(commissions) == 1


@pytest.mark.asyncio
async def test_cancellation_stops_future_commissions(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-1",
        paid_at=datetime.now(timezone.utc),
    )
    await commission_service.handle_churn(db_session, customer["org_id"])
    await db_session.commit()

    # A payment arriving after churn must not create a new commission.
    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-2",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    commissions = (
        await db_session.execute(
            select(PartnerCommission).where(
                PartnerCommission.partner_id == profile["partner_id"]
            )
        )
    ).scalars().all()
    assert len(commissions) == 1


@pytest.mark.asyncio
async def test_refund_reverses_commission(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-1",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    count = await commission_service.reverse_by_reference(
        db_session, "ref-1", "refund"
    )
    await db_session.commit()
    assert count == 1

    commission = (
        await db_session.execute(
            select(PartnerCommission).where(
                PartnerCommission.billing_event_id == "ref-1"
            )
        )
    ).scalar_one()
    assert commission.status == "reversed"
    assert commission.reversal_reason == "refund"
    # Original amounts are preserved.
    assert commission.commission_amount_minor == 1470


# ── Authorization ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partner_sees_only_own_data(async_client, db_session):
    partner_a = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile_a = await _activate_partner(async_client, partner_a["headers"])
    await _register(
        async_client, "customer@example.com", "Customer One",
        ref_code=profile_a["referral_code"],
    )

    partner_b = await _register(async_client, "bob@example.com", "Bob Builder")
    await _activate_partner(async_client, partner_b["headers"])

    # B's dashboard must not show A's signups.
    res = await async_client.get("/v1/partners/dashboard", headers=partner_b["headers"])
    assert res.status_code == 200, res.text
    assert res.json()["signups"] == 0


@pytest.mark.asyncio
async def test_admin_endpoints_require_system_admin(async_client):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    await _activate_partner(async_client, partner["headers"])

    res = await async_client.get("/v1/admin/partners", headers=partner["headers"])
    assert res.status_code == 403, res.text


# ── Payout ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_flow(async_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_MINIMUM_PAYOUT_MINOR", 0)
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-1",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    # Make the commission payable (bypass the hold period).
    commission = (
        await db_session.execute(select(PartnerCommission))
    ).scalar_one()
    commission.status = "payable"
    await db_session.commit()

    from app.modules.partners.payouts import payout_service

    payout = await payout_service.create_payout(db_session, profile["partner_id"])
    await db_session.commit()
    assert payout.amount_minor == 1470

    processed = await payout_service.process_payout(
        db_session, payout.id, "mark_paid", "TXN-123"
    )
    await db_session.commit()
    assert processed.status == "paid"
    assert processed.transaction_reference == "TXN-123"

    commission = (
        await db_session.execute(select(PartnerCommission))
    ).scalar_one()
    assert commission.status == "paid"
    assert commission.paid_at is not None
    assert str(commission.payout_id) == str(payout.id)


# ── Public referral resolver ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_referral_resolver(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])

    res = await async_client.get(
        f"/v1/public/referral/{profile['referral_code']}"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid"] is True
    assert body["referral_code"] == profile["referral_code"]

    # Unknown code → not valid, safe default destination.
    res2 = await async_client.get("/v1/public/referral/NOPE-0000")
    assert res2.status_code == 200
    assert res2.json()["valid"] is False
    assert res2.json()["destination"] == "/"


# ── Admin control plane ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_control_plane(async_client, db_session):
    admin = await _register(async_client, "admin@example.com", "Admin User")
    # Promote to system admin directly.
    admin_row = (
        await db_session.execute(select(User).where(User.id == admin["user_id"]))
    ).scalar_one()
    admin_row.is_system_admin = True
    await db_session.commit()

    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])
    customer = await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )
    await commission_service.record_payment(
        db_session,
        organization_id=customer["org_id"],
        collected_minor=4900,
        currency="USD",
        payment_reference="ref-1",
        paid_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    admin_headers = {"Authorization": f"Bearer {admin['token']}"}

    # List partners.
    res = await async_client.get("/v1/admin/partners", headers=admin_headers)
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1

    # Stats.
    res = await async_client.get("/v1/admin/partners/stats", headers=admin_headers)
    assert res.status_code == 200, res.text
    assert res.json()["total_partners"] == 1
    assert res.json()["total_active_paid_customers"] == 1

    # Detail.
    res = await async_client.get(
        f"/v1/admin/partners/{profile['partner_id']}", headers=admin_headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["referral_code"] == profile["referral_code"]
    assert len(body["referred_customers"]) == 1

    # Admin commissions list.
    res = await async_client.get(
        "/v1/admin/partners/commissions", headers=admin_headers
    )
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1
    commission_id = res.json()["items"][0]["commission_id"]

    # Reverse the commission.
    res = await async_client.post(
        f"/v1/admin/partners/commissions/{commission_id}/reverse",
        json={"reason": "Customer payment was refunded."},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text

    # Suspend the partner.
    res = await async_client.patch(
        f"/v1/admin/partners/{profile['partner_id']}",
        json={"status": "suspended", "reason": "review"},
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "suspended"


# ── Suspended partner cannot create new referrals ────────────────────────


@pytest.mark.asyncio
async def test_suspended_partner_cannot_refer(async_client, db_session):
    partner = await _register(async_client, "alex@example.com", "Alexander Kof")
    profile = await _activate_partner(async_client, partner["headers"])

    profile_row = (
        await db_session.execute(
            select(PartnerProfile).where(
                PartnerProfile.id == profile["partner_id"]
            )
        )
    ).scalar_one()
    profile_row.status = "suspended"
    await db_session.commit()

    await _register(
        async_client,
        "customer@example.com",
        "Customer One",
        ref_code=profile["referral_code"],
    )

    referral = (
        await db_session.execute(select(PartnerReferral))
    ).scalars().all()
    assert referral == []
