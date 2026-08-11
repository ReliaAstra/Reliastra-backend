from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    create_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_hash_is_bcrypt_and_verifies() -> None:
    hashed = hash_password("CorrectHorseBattery9")
    assert hashed.startswith("$2")
    assert verify_password("CorrectHorseBattery9", hashed)
    assert not verify_password("wrong", hashed)


def test_token_type_is_enforced() -> None:
    secret = "a-secure-test-secret-that-is-over-32-characters"
    token = create_token(uuid4(), secret, "access", timedelta(minutes=1))
    assert decode_token(token, secret, "access").type == "access"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, secret, "refresh")


def test_api_key_plaintext_is_only_recoverable_at_creation() -> None:
    plaintext, prefix, digest = generate_api_key()
    assert plaintext.startswith("rla_")
    assert prefix == plaintext[:8]
    assert digest == hash_api_key(plaintext)
    assert plaintext not in digest
