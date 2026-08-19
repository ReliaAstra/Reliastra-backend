"""Unit tests for the integer commission arithmetic used by the partner program."""

from app.modules.partners.service import apply_rate, mask_email, _build_referral_code


def test_apply_rate_is_exact_integer_arithmetic():
    # $49.00 at 30% -> $14.70 (1470 minor)
    assert apply_rate(4900, 30) == 1470
    # $29.00 at 30% -> $8.70 (870 minor)
    assert apply_rate(2900, 30) == 870
    # $99.00 at 30% -> $29.70 (2970 minor)
    assert apply_rate(9900, 30) == 2970
    # zero revenue -> zero commission
    assert apply_rate(0, 30) == 0


def test_apply_rate_rounds_half_up_without_floats():
    # 4999 minor at 30% = 1499.7 -> rounds to 1500
    assert apply_rate(4999, 30) == 1500


def test_mask_email_hides_local_part():
    assert mask_email("alex@reliastra.com") == "a***@reliastra.com"
    assert mask_email("") == "***"
    assert mask_email("not-an-email") == "***"


def test_build_referral_code_matches_existing_format():
    code = _build_referral_code("Alexander Kof")
    assert code.startswith("ALEX-")
    assert len(code.split("-")[1]) == 4
