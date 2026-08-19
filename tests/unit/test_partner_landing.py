"""Public partner landing contract stays aligned with live economics."""

from app.config import settings
from app.modules.partners.economics import apply_bps, default_rate_bps
from app.modules.partners.landing import build_program_landing


def test_landing_refer_rate_matches_configuration():
    landing = build_program_landing()
    illustration = landing["commission_illustration"]
    assert illustration["rate_bps"] == settings.PARTNER_RATE_REFER_BPS
    assert illustration["label"] == "ILLUSTRATIVE EXAMPLE"
    expected = apply_bps(illustration["subscription_minor"], illustration["rate_bps"])
    assert illustration["commission_minor"] == expected
    assert default_rate_bps("refer") == illustration["rate_bps"]


def test_landing_does_not_invent_white_label_or_payout_calendar():
    landing = build_program_landing()
    faq = {item["id"]: item["answer"].lower() for item in landing["faq"]}
    assert "white-label" in faq["white-label"]
    assert "not a live" in faq["white-label"] or "does not expose" in faq["white-label"]
    assert "calendar" not in faq["paid"] or "no fixed calendar" in faq["paid"]
    unavailable = [r for r in landing["resources"] if not r["available"]]
    assert all(r["href"] is None for r in unavailable)


def test_landing_seo_and_canonical_path():
    landing = build_program_landing()
    assert landing["positioning"]["canonical_path"] == "/partners"
    assert landing["seo"]["title"].startswith("RELIASTRA Partner Network")
    assert "/partners" in landing["seo"]["canonical_url"]
    assert landing["frontend_endpoints"]["dashboard"] == "GET /v1/partners/me/dashboard"


def test_faq_answers_are_real_dom_text():
    landing = build_program_landing()
    required = {
        "what-is-the-network",
        "who-can-join",
        "cost",
        "attribution",
        "earn",
        "recurring",
        "referral-link",
        "see-commissions",
        "paid",
    }
    ids = {item["id"] for item in landing["faq"]}
    assert required <= ids
    for item in landing["faq"]:
        assert len(item["answer"]) > 40
