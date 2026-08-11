import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt
from cryptography.fernet import Fernet
from app.config import settings
from app.core.exceptions import UnauthorizedException


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    subject: str, additional_claims: dict[str, Any] | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": "access",
        "jti": secrets.token_hex(16),
    }
    if additional_claims:
        to_encode.update(additional_claims)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(
    subject: str, additional_claims: dict[str, Any] | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    if additional_claims:
        to_encode.update(additional_claims)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedException("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedException("Invalid token") from exc


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a secure programmatic access key.
    Returns (full_key, prefix, hashed_key).
    """
    token_part = secrets.token_hex(20)
    full_key = f"rel_{token_part}"
    prefix = full_key[:8]
    hashed_key = hash_api_key(full_key)
    return full_key, prefix, hashed_key


def hash_api_key(key: str) -> str:
    """Return SHA-256 hex digest of the API key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def get_fernet() -> Fernet:
    return Fernet(settings.fernet_key)


def encrypt_jsonb(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    fernet = get_fernet()
    json_bytes = json.dumps(data).encode("utf-8")
    encrypted = fernet.encrypt(json_bytes)
    return encrypted.decode("utf-8")


def decrypt_jsonb(encrypted_str: str | None) -> dict[str, Any] | None:
    if encrypted_str is None:
        return None
    fernet = get_fernet()
    try:
        decrypted_bytes = fernet.decrypt(encrypted_str.encode("utf-8"))
        return json.loads(decrypted_bytes.decode("utf-8"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to decrypt JSONB data — possibly rotated SECRET_KEY: %s", exc
        )
        return None
