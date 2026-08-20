import hashlib
import hmac
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


def _base_token_payload(subject: str, expire: datetime, token_type: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "sub": subject,
        "iat": now,
        "nbf": now,
        "exp": expire,
        "type": token_type,
        "jti": secrets.token_hex(16),
    }


def create_access_token(
    subject: str, additional_claims: dict[str, Any] | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = _base_token_payload(subject, expire, "access")
    if additional_claims:
        to_encode.update(additional_claims)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(
    subject: str, additional_claims: dict[str, Any] | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode = _base_token_payload(subject, expire, "refresh")
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
    """Return a bcrypt hash of the API key.

    bcrypt is GPU-brute-force resistant (unlike raw SHA-256), which matters
    because API keys carry enough entropy to be valuable if the database
    leaks. Keys are short (< 72 bytes), so bcrypt's input limit is a non-issue.
    """
    return bcrypt.hashpw(
        key.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify *raw_key* against *stored_hash*.

    Supports both hash formats so pre-existing rows keep working:

    * ``$2b$...``  — bcrypt (all new keys)
    * 64 hex chars — legacy SHA-256 (checked in constant time)
    """
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(
                raw_key.encode("utf-8"), stored_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False
    legacy_sha256 = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_sha256, stored_hash)


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
        # Log the decryption failure so it isn't silently swallowed;
        # returning empty dict as a safe default for callers.
        import logging
        logging.getLogger(__name__).warning(
            "Failed to decrypt JSONB data — possibly rotated SECRET_KEY: %s", exc
        )
        return {}
