"""Tests for FIX 11 (bcrypt API keys) and FIX 32 (JWT iat claim)."""

import hashlib

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


def test_hash_api_key_uses_bcrypt():
    hashed = hash_api_key("rel_" + "a" * 40)
    # bcrypt hashes carry the $2b$ prefix, not a 64-char hex digest.
    assert hashed.startswith("$2")
    assert hashed != hashlib.sha256(("rel_" + "a" * 40).encode()).hexdigest()


def test_generate_api_key_roundtrip_via_bcrypt():
    full_key, prefix, hashed_key = generate_api_key()
    assert full_key.startswith("rel_")
    assert prefix == full_key[:8]
    assert verify_api_key(full_key, hashed_key) is True
    assert verify_api_key("rel_" + "b" * 40, hashed_key) is False


def test_verify_api_key_supports_legacy_sha256_rows():
    legacy = hashlib.sha256(b"rel_legacy_key").hexdigest()
    assert verify_api_key("rel_legacy_key", legacy) is True
    assert verify_api_key("rel_wrong_key", legacy) is False


def test_access_and_refresh_tokens_carry_iat_claim():
    access = decode_token(create_access_token("user-1"))
    assert "iat" in access
    assert "exp" in access
    assert access["iat"] <= access["exp"]

    refresh = decode_token(create_refresh_token("user-1"))
    assert "iat" in refresh
    assert refresh["type"] == "refresh"


def test_iat_is_within_tolerance():
    import time
    from datetime import datetime, timezone

    payload = decode_token(create_access_token("user-1"))
    now_ts = datetime.now(timezone.utc).timestamp()
    assert abs(payload["iat"] - now_ts) < 30
