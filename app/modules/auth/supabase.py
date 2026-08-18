"""Supabase Authentication — FastAPI router and dependencies.

Integrates with Supabase Auth by accepting Bearer JWTs issued by Supabase,
verifying them (HS256 via JWT secret or RS256 via JWKS), and provisioning
or linking a local Reliastra user account on first login.

Flow
----
1. Client authenticates with Supabase Auth (email/password, magic link,
   Google, GitHub, etc.) and receives an ``access_token``.
2. Client calls ANY Reliastra endpoint with
   ``Authorization: Bearer <supabase-access-token>``.
3. The ``SupabaseAuthMiddleware`` or ``require_supabase_user`` dependency
   verifies the token against the Supabase project's JWKS/JWT secret.
4. On first login, a local ``User`` + ``Organization`` + ``OrganizationMember``
   are auto-created, mirroring the Supabase user's email and name.
5. The local user's ``external_auth_id`` is set to ``supabase:<sub>`` so
   subsequent requests map instantly.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.supabase import map_supabase_user, verify_supabase_token
from app.core.permissions import Plan
from app.db.session import get_db
from app.modules.auth.service import auth_service
from app.modules.auth.schemas import TokenResponse, LoginRequest
from app.modules.users.repository import UserRepository
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.models import Organization, OrganizationMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth/supabase", tags=["Supabase Auth"])


async def get_supabase_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """FastAPI dependency that extracts and verifies the Supabase JWT.

    Usage::

        @router.get("/protected")
        async def protected(supabase_user: dict = Depends(get_supabase_user)):
            return {"email": supabase_user["email"]}

    Raises HTTPException(401) when the token is missing or invalid.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Supabase access token",
        )

    payload = await verify_supabase_token(
        token=token,
        supabase_url=settings.SUPABASE_URL,
        jwt_secret=settings.SUPABASE_JWT_SECRET,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase token",
        )

    return payload


@router.post("/login", response_model=TokenResponse)
async def supabase_login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange Supabase credentials for Reliastra tokens.

    This is NOT a Supabase Auth endpoint — it uses the standard Reliastra
    login flow.  For true Supabase JWT login, simply present the Supabase
    access token in the ``Authorization`` header on any protected endpoint.
    """
    return await auth_service.login(db, request)


@router.get("/me", response_model=dict)
async def supabase_me(
    supabase_user: dict[str, Any] = Depends(get_supabase_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the current Supabase-authenticated user profile.

    The first time a Supabase user hits this endpoint, a local Reliastra
    user account + organization are auto-provisioned.
    """
    mapped = map_supabase_user(supabase_user)
    external_id = mapped["external_auth_id"]

    # Check if this Supabase user already has a local account
    user = await UserRepository.get_by_external_auth_id(db, external_id)

    if not user:
        # Try by email as fallback
        if mapped["email"]:
            user = await UserRepository.get_by_email(db, mapped["email"])

        if user:
            # Link the existing local account to Supabase
            await UserRepository.update(
                db, user, external_auth_id=external_id
            )
        else:
            # Auto-provision a local account
            user = await UserRepository.create(
                db,
                email=mapped["email"] or f"{uuid.uuid4().hex[:8]}@supabase.local",
                password_hash="",
                full_name=mapped["full_name"],
                is_email_verified=mapped["is_email_verified"],
                external_auth_id=external_id,
                is_active=True,
            )

            # Create a personal org for the new user
            slug = f"user-{user.id.hex[:8]}"
            org = await OrganizationRepository.create(
                db,
                name=f"{mapped['full_name']}'s Organization",
                slug=slug,
                plan=Plan.FREE.value,
            )
            await OrganizationRepository.add_member(
                db,
                org_id=org.id,
                user_id=user.id,
                role="owner",
            )
            logger.info(
                "Auto-provisioned local account for Supabase user %s",
                external_id,
            )

    # Issuing native Reliastra tokens allows the client to continue using
    # standard Reliastra auth for subsequent requests (no need to re-verify
    # the Supabase JWT on every call).  The access_token expires in 15 min
    # and can be refreshed with /v1/auth/refresh.
    tokens = auth_service._generate_token_pair(user.id)
    expires_at = datetime.now(timezone.utc) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    await auth_service.auth_repository.create_refresh_token(
        db, user.id, tokens.refresh_token, expires_at
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }