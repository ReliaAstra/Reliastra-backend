"""Password, token, API-key and secret-at-rest primitives."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel


class TokenClaims(BaseModel):
    sub: UUID
    type: Literal["access", "refresh"]
    exp: datetime
    iat: datetime
    jti: UUID


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(
    user_id: UUID, secret: str, token_type: Literal["access", "refresh"], ttl: timedelta
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(
    token: str, secret: str, expected_type: Literal["access", "refresh"]
) -> TokenClaims:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    claims = TokenClaims.model_validate(payload)
    if claims.type != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return claims


def generate_api_key() -> tuple[str, str, str]:
    plaintext = f"rla_{secrets.token_urlsafe(32)}"
    return plaintext, plaintext[:8], hash_api_key(plaintext)


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_json(value: dict[str, Any], secret: str) -> dict[str, str]:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return {"_encrypted": _fernet(secret).encrypt(payload).decode()}


def decrypt_json(value: dict[str, Any] | None, secret: str) -> dict[str, Any]:
    if not value:
        return {}
    token = value.get("_encrypted")
    if not isinstance(token, str):
        return value
    try:
        decoded = _fernet(secret).decrypt(token.encode())
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt protected configuration") from exc
    result = json.loads(decoded)
    if not isinstance(result, dict):
        raise ValueError("Protected configuration is not an object")
    return result
