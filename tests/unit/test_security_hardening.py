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
    from datetime import datetime, timezone

    payload = decode_token(create_access_token("user-1"))
    now_ts = datetime.now(timezone.utc).timestamp()
    assert abs(payload["iat"] - now_ts) < 30


def test_expired_token_raises_unauthorized():
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.config import settings
    from app.core.exceptions import UnauthorizedException

    expire = datetime.now(timezone.utc) - timedelta(minutes=5)
    token = jwt.encode(
        {
            "sub": "user-1",
            "iat": expire - timedelta(minutes=1),
            "nbf": expire - timedelta(minutes=1),
            "exp": expire,
            "type": "access",
            "jti": "deadbeef",
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedException, match="expired"):
        decode_token(token)


def test_fernet_roundtrip_and_decrypt_failure():
    from app.core.security import decrypt_jsonb, encrypt_jsonb

    payload = {"Authorization": "Bearer secret"}
    encrypted = encrypt_jsonb(payload)
    assert encrypted is not None
    assert decrypt_jsonb(encrypted) == payload
    assert decrypt_jsonb(None) is None
    # Corrupt ciphertext must not raise — callers get a safe empty dict.
    assert decrypt_jsonb("gAAAAA-not-a-valid-fernet-token") == {}
