"""Tests for referral URL construction and the privacy helpers.

The canonical link shape is a product commitment (``/r/{partner_code}``) and
the masking helpers are a privacy commitment, so both are pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.modules.partners.links import ReferralLinkService
from app.modules.partners.schemas import CampaignCreate, ReferralLinkCreate
from app.modules.partners.utils import (
    account_last4,
    build_payout_label,
    generate_campaign_code,
    generate_partner_code,
    hash_email,
    hash_ip,
    is_reserved_code,
    looks_like_bot,
    mask_account_number,
    mask_email,
    slugify,
)


# ─────────────────────────── canonical links ─────────────────────────────


def test_canonical_link_is_public_url_slash_r_slash_code():
    assert ReferralLinkService.build("ABC23456") == "https://reliastra.com/r/ABC23456"


def test_campaign_link_uses_the_campaign_query_parameter():
    url = ReferralLinkService.build("ABC23456", campaign_code="SUMMER")
    assert url.startswith("https://reliastra.com/r/ABC23456?")
    assert parse_qs(urlparse(url).query)["campaign"] == ["SUMMER"]


def test_base_url_is_configuration_driven_not_hardcoded(monkeypatch):
    """Staging must emit staging links without a code change."""
    monkeypatch.setattr(settings, "RELIASTRA_PUBLIC_URL", "https://staging.example.com")
    assert (
        ReferralLinkService.build("ABC23456")
        == "https://staging.example.com/r/ABC23456"
    )


def test_path_prefix_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_REFERRAL_PATH_PREFIX", "/go")
    assert ReferralLinkService.build("ABC23456") == "https://reliastra.com/go/ABC23456"


def test_trailing_slash_in_config_does_not_double_up(monkeypatch):
    monkeypatch.setattr(settings, "RELIASTRA_PUBLIC_URL", "https://reliastra.com/")
    assert ReferralLinkService.build("ABC23456") == "https://reliastra.com/r/ABC23456"


def test_utm_and_destination_are_encoded_into_the_query():
    url = ReferralLinkService.build(
        "ABC23456",
        campaign_code="LAUNCH",
        destination_path="/pricing?plan=pro",
        utm={"utm_source": "news letter", "utm_medium": "email"},
    )
    params = parse_qs(urlparse(url).query)
    assert params["campaign"] == ["LAUNCH"]
    assert params["to"] == ["/pricing?plan=pro"]
    assert params["utm_source"] == ["news letter"]
    assert params["utm_medium"] == ["email"]


def test_partner_code_is_url_escaped():
    url = ReferralLinkService.build("A B/C")
    assert "/r/A%20B%2FC" in url


def test_link_utm_overrides_campaign_defaults():
    campaign = SimpleNamespace(
        campaign_code="SUMMER",
        default_utm={"utm_source": "campaign", "utm_medium": "social"},
        destination_path="/campaign",
    )
    link = SimpleNamespace(utm={"utm_source": "link"}, destination_path=None)
    params = parse_qs(
        urlparse(ReferralLinkService.build_for_link("ABC23456", link, campaign)).query
    )
    assert params["utm_source"] == ["link"]      # link wins
    assert params["utm_medium"] == ["social"]    # campaign default survives
    assert params["to"] == ["/campaign"]         # falls back to the campaign


def test_public_profile_url_uses_the_slug():
    assert (
        ReferralLinkService.public_profile_url("acme-consulting")
        == "https://reliastra.com/partners/acme-consulting"
    )


# ─────────────────────── destination path safety ─────────────────────────


@pytest.mark.parametrize(
    "evil",
    [
        "https://evil.example.com/phish",
        "//evil.example.com",
        "javascript:alert(1)",
        "http://evil.example.com",
    ],
)
def test_absolute_destinations_are_rejected_to_prevent_open_redirects(evil):
    with pytest.raises(ValueError):
        ReferralLinkCreate(destination_path=evil)
    with pytest.raises(ValueError):
        CampaignCreate(name="Test", destination_path=evil)


def test_relative_destinations_are_accepted():
    assert ReferralLinkCreate(destination_path="/pricing").destination_path == "/pricing"


def test_unknown_utm_keys_are_rejected():
    with pytest.raises(ValueError):
        ReferralLinkCreate(utm={"utm_evil": "x"})


def test_campaign_code_is_normalised_to_upper_case():
    assert CampaignCreate(name="Test", campaign_code="summer-24").campaign_code == (
        "SUMMER-24"
    )


# ───────────────────────── codes and identifiers ─────────────────────────


def test_partner_codes_avoid_visually_ambiguous_characters():
    """Codes get read aloud and typed by hand, so 0/O and 1/I/L are out."""
    for _ in range(200):
        code = generate_partner_code()
        assert len(code) == 8
        assert not set(code) & set("01OIL")


def test_campaign_codes_are_short_and_unambiguous():
    code = generate_campaign_code()
    assert len(code) == 6
    assert not set(code) & set("01OIL")


def test_reserved_codes_are_recognised():
    assert is_reserved_code("admin")
    assert is_reserved_code("API")
    assert not is_reserved_code("ABC23456")


def test_slugify_handles_unicode_and_punctuation():
    assert slugify("Åcme Consulting GmbH!") == "acme-consulting-gmbh"
    assert slugify("   ") == "partner"
    assert len(slugify("x" * 200)) <= 60


# ──────────────────────────── privacy helpers ────────────────────────────


def test_emails_are_masked_and_never_returned_whole():
    assert mask_email("jane.doe@acme.com") == "j•••e@acme.com"
    assert mask_email("ab@acme.com") == "a•@acme.com"
    assert mask_email(None) is None
    assert mask_email("not-an-email") is None


def test_masked_email_keeps_no_recoverable_local_part():
    masked = mask_email("jonathan@acme.com")
    assert "onatha" not in masked
    assert masked.endswith("@acme.com")


def test_ip_hash_is_keyed_stable_and_irreversible():
    a = hash_ip("203.0.113.10")
    b = hash_ip("203.0.113.10")
    c = hash_ip("203.0.113.11")
    assert a == b != c
    assert len(a) == 64
    assert "203.0.113.10" not in a
    assert hash_ip(None) is None


def test_email_hash_is_case_and_whitespace_insensitive():
    assert hash_email("  Jane@Acme.com ") == hash_email("jane@acme.com")


def test_account_numbers_are_masked_to_the_last_four():
    assert mask_account_number("0123456789") == "••••6789"
    assert account_last4("0123456789") == "6789"
    label = build_payout_label("GTBank", "0123456789", "paystack_transfer")
    assert label == "GTBank ••••6789"
    assert "012345" not in label


# ───────────────────────────── bot detection ─────────────────────────────


@pytest.mark.parametrize(
    "ua",
    [
        "Mozilla/5.0 (compatible; Googlebot/2.1)",
        "curl/8.1.2",
        "python-requests/2.31",
        "facebookexternalhit/1.1",
        None,
    ],
)
def test_obvious_automated_traffic_is_flagged(ua):
    assert looks_like_bot(ua) is True


def test_real_browsers_are_not_flagged():
    assert (
        looks_like_bot(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        is False
    )
