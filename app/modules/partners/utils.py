"""Shared, side-effect-free helpers for the Partner Network.

Everything here is deterministic and cheap: code generation, privacy
preserving hashes, and the masking rules that keep customer PII out of
partner-facing responses.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata

from app.config import settings
from app.modules.partners.constants import (
    CAMPAIGN_CODE_LENGTH,
    CODE_ALPHABET,
    PARTNER_CODE_LENGTH,
    RESERVED_CODES,
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


# ───────────────────────────── code generation ───────────────────────────


def generate_partner_code(length: int = PARTNER_CODE_LENGTH) -> str:
    """Random, unambiguous partner code.

    Uses an alphabet without ``0/O/1/I/L`` because these codes are read
    aloud, printed on slides and typed by hand. Collisions are handled by
    the caller retrying against the DB unique constraint.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def generate_campaign_code(length: int = CAMPAIGN_CODE_LENGTH) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def generate_link_token(length: int = 12) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def is_reserved_code(code: str) -> bool:
    """Case-insensitive check against the reserved-code list.

    Codes resolve case-insensitively at ``/r/{code}``, so reservation has to
    be case-insensitive too — otherwise ``/r/admin`` would slip past a check
    written for ``ADMIN``.
    """
    return code.strip().upper() in RESERVED_CODES


def slugify(value: str, *, max_length: int = 60) -> str:
    """ASCII slug suitable for the public directory URL."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP.sub("-", ascii_only).strip("-")
    slug = slug[:max_length].strip("-")
    return slug or "partner"


def generate_visitor_id() -> str:
    """Opaque first-party visitor identifier (never derived from an IP)."""
    return secrets.token_urlsafe(24)[:32]


def generate_reference(prefix: str = "PPO") -> str:
    """Human-quotable payout reference, e.g. ``PPO-7QK4M2XT9RVB``."""
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
    return f"{prefix}-{body}"


# ────────────────────────────── hashing ──────────────────────────────────


def _pepper() -> bytes:
    return settings.SECRET_KEY.encode("utf-8")


def hash_ip(ip: str | None) -> str | None:
    """Keyed hash of a client IP.

    Raw IPs are never persisted by the click pipeline. The HMAC keyed with
    ``SECRET_KEY`` still supports velocity/clustering analysis while making
    the stored value useless as a location identifier on its own.
    """
    if not ip:
        return None
    return hmac.new(_pepper(), ip.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def hash_email(email: str | None) -> str | None:
    """Keyed hash of a normalised email, used for duplicate-lead detection."""
    if not email:
        return None
    return hmac.new(
        _pepper(), email.strip().lower().encode("utf-8"), hashlib.sha256
    ).hexdigest()


# ────────────────────────────── masking ──────────────────────────────────


def mask_email(email: str | None) -> str | None:
    """``jane.doe@acme.com`` → ``j•••e@acme.com``.

    Partners get enough to recognise a referral they already know about and
    nothing they could use to build a contact list. Applied at **every**
    tier — there is no unmasked variant of this for partners.
    """
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = f"{local[0]}•"
    else:
        masked_local = f"{local[0]}•••{local[-1]}"
    return f"{masked_local}@{domain}"


def mask_account_number(account_number: str | None) -> str | None:
    if not account_number:
        return None
    tail = account_number[-4:]
    return f"••••{tail}"


def account_last4(account_number: str | None) -> str | None:
    if not account_number:
        return None
    return account_number[-4:]


def build_payout_label(
    bank_name: str | None, account_number: str | None, method: str
) -> str:
    masked = mask_account_number(account_number) or ""
    if bank_name:
        return f"{bank_name} {masked}".strip()
    return f"{method} {masked}".strip()


# ────────────────────────── request helpers ──────────────────────────────

_BOT_PATTERNS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "curl/",
    "wget",
    "python-requests",
    "httpx",
    "headlesschrome",
    "phantomjs",
    "facebookexternalhit",
    "preview",
    "monitoring",
    "uptime",
)


def looks_like_bot(user_agent: str | None) -> bool:
    """Best-effort bot detection for click *analytics only*.

    A true result never blocks anything and never affects money — clicks are
    not payable in the first place. It only keeps obvious crawler traffic out
    of the partner's reported click counts.
    """
    if not user_agent:
        return True
    ua = user_agent.lower()
    return any(pattern in ua for pattern in _BOT_PATTERNS)


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:limit]


__all__ = [
    "account_last4",
    "build_payout_label",
    "generate_campaign_code",
    "generate_link_token",
    "generate_partner_code",
    "generate_reference",
    "generate_visitor_id",
    "hash_email",
    "hash_ip",
    "is_reserved_code",
    "looks_like_bot",
    "mask_account_number",
    "mask_email",
    "slugify",
    "truncate",
]
