"""Supabase Authentication integration.

Supports two modes of JWT verification:

1. **HS256** via ``SUPABASE_JWT_SECRET`` (simpler, uses the JWT secret
   from Supabase project settings → API → JWT Settings).
2. **RS256** via JWKS endpoint at ``SUPABASE_URL + /auth/v1/.well-known/jwks``
   (more secure, used when ``SUPABASE_JWT_SECRET`` is empty).

Usage:

.. code-block:: python

    from app.core.supabase import verify_supabase_token

    payload = await verify_supabase_token(token)
    # → {"sub": "...", "email": "...", "aud": "authenticated", ...}
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache the JWKS response
_jwks_cache: dict[str, Any] = {"keys": [], "expires_at": 0.0}


async def _fetch_jwks(supabase_url: str) -> list[dict[str, Any]]:
    """Fetch and parse the Supabase JWKS endpoint."""
    global _jwks_cache
    now = time.time()
    if _jwks_cache["expires_at"] > now:
        return _jwks_cache["keys"]

    url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        keys = data.get("keys", [])
        _jwks_cache["keys"] = keys
        _jwks_cache["expires_at"] = now + 3600  # cache 1 hour
        logger.info("Fetched %d JWKS keys from %s", len(keys), url)
        return keys
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", url, exc)
        return _jwks_cache.get("keys", [])


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode and return the JWT payload WITHOUT signature verification.

    Returns ``None`` on malformed tokens.
    """
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # Pad for base64 decoding
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return None


async def verify_supabase_token(
    token: str,
    supabase_url: str,
    jwt_secret: str = "",
) -> dict[str, Any] | None:
    """Verify a Supabase JWT and return its payload.

    Args:
        token: The raw JWT string (``Authorization: Bearer <token>``).
        supabase_url: The Supabase project URL (e.g. ``https://xyz.supabase.co``).
        jwt_secret: The ``SUPABASE_JWT_SECRET`` for HS256 verification.
                    If empty, RS256 via JWKS is used.

    Returns:
        The decoded JWT payload dict, or ``None`` if verification fails.
    """
    import jwt as pyjwt

    if not token:
        return None

    if jwt_secret:
        # HS256 — verify using the shared JWT secret
        try:
            payload = pyjwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
            return payload
        except Exception as exc:
            logger.debug("Supabase HS256 verification failed: %s", exc)
            return None

    # RS256 — verify using JWKS
    try:
        keys = await _fetch_jwks(supabase_url)
        if not keys:
            logger.warning("No JWKS keys available; cannot verify RS256 token")
            return None

        # Try each key until one works
        for key_data in keys:
            try:
                payload = pyjwt.decode(
                    token,
                    key_data,
                    algorithms=["RS256"],
                    audience="authenticated",
                    options={"require": ["exp", "sub"]},
                )
                return payload
            except Exception:
                continue

        logger.debug("Supabase RS256 verification failed — no matching key")
        return None
    except Exception as exc:
        logger.warning("Supabase token verification error: %s", exc)
        return None


def map_supabase_user(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a verified Supabase JWT payload to a user dict for the app.

    Fields:

    * ``email`` — from ``email`` or ``user_metadata.email``
    * ``full_name`` — from ``user_metadata.full_name`` or ``user_metadata.name``
    * ``sub`` — the Supabase user UUID (maps to external_auth_id)
    * ``is_email_verified`` — from ``email_verified`` or
      ``app_metadata.email_verified``
    """
    user_meta = payload.get("user_metadata") or {}
    app_meta = payload.get("app_metadata") or {}

    email = payload.get("email") or user_meta.get("email", "")
    full_name = (
        user_meta.get("full_name")
        or user_meta.get("name")
        or payload.get("email", "").split("@")[0]
    )
    is_verified = payload.get("email_verified") or app_meta.get(
        "email_verified", False
    )

    return {
        "external_auth_id": f"supabase:{payload.get('sub', '')}",
        "email": email,
        "full_name": full_name,
        "is_email_verified": is_verified,
    }