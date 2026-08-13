import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    AppException,
    ConflictException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import get_password_hash
from app.modules.auth.constants import TOKEN_TYPE_BEARER
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import TokenResponse
from app.modules.auth.service import AuthService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class GoogleAuthService:
    """Handles Google OAuth2 flow: token exchange, user creation/linking, token generation."""

    def __init__(
        self,
        auth_service: AuthService = AuthService(),
        user_repository: UserRepository = UserRepository(),
        org_repository: OrganizationRepository = OrganizationRepository(),
        auth_repository: AuthRepository = AuthRepository(),
    ) -> None:
        self.auth_service = auth_service
        self.user_repository = user_repository
        self.org_repository = org_repository
        self.auth_repository = auth_repository

    def _check_enabled(self) -> None:
        if not settings.GOOGLE_AUTH_ENABLED:
            raise AppException(
                "Google authentication is not enabled",
                status_code=403,
                code="GOOGLE_AUTH_DISABLED",
            )
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise AppException(
                "Google OAuth is not configured (missing CLIENT_ID or CLIENT_SECRET)",
                status_code=500,
                code="GOOGLE_AUTH_MISCONFIGURED",
            )

    def get_authorization_url(self, state_token: str) -> str:
        """Build the Google OAuth consent URL."""
        self._check_enabled()
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": state_token,
        }
        import urllib.parse
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange the authorization code for Google access tokens."""
        self._check_enabled()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                logger.error(
                    "Google token exchange failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise UnauthorizedException(
                    "Failed to exchange authorization code with Google"
                )
            return resp.json()

    async def get_google_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user profile from Google using the access token."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                logger.error(
                    "Google userinfo fetch failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise UnauthorizedException(
                    "Failed to retrieve user info from Google"
                )
            return resp.json()

    async def authenticate_with_code(
        self, session: AsyncSession, code: str
    ) -> TokenResponse:
        """
        Full Google OAuth flow:
        1. Exchange code for access token
        2. Fetch Google user profile
        3. Find or create local user
        4. Generate JWT token pair
        """
        # Step 1: Exchange code
        token_data = await self.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise UnauthorizedException("No access token in Google response")

        # Step 2: Get user info
        google_user = await self.get_google_user_info(access_token)
        google_id = google_user.get("id")
        google_email = google_user.get("email")
        google_name = google_user.get("name", "")
        google_picture = google_user.get("picture")
        verified = google_user.get("email_verified", False)

        if not google_id or not google_email:
            raise ValidationException(
                "Google account must provide an email address",
                details={"google_id": google_id, "email": google_email},
            )

        if not verified:
            raise UnauthorizedException(
                "Google email is not verified. Please verify your email with Google first."
            )

        # Step 3: Find existing user by google_id or email
        user = await self.user_repository.get_by_google_id(session, google_id)

        if not user:
            # Check if email already exists (account linking scenario)
            user = await self.user_repository.get_by_email(session, google_email)
            if user:
                # Link existing account with Google
                await self.user_repository.update(
                    session,
                    user,
                    google_id=google_id,
                    avatar_url=google_picture,
                    auth_provider="google",
                )
                logger.info(
                    "Linked Google account %s to existing user %s",
                    google_id,
                    user.id,
                )
            else:
                # Create new user from Google data
                random_password = secrets.token_urlsafe(32)
                password_hash = get_password_hash(random_password)

                full_name = google_name if google_name else google_email.split("@")[0]
                user = await self.user_repository.create(
                    session=session,
                    email=google_email,
                    password_hash=password_hash,
                    full_name=full_name,
                    google_id=google_id,
                    avatar_url=google_picture,
                    auth_provider="google",
                )
                logger.info(
                    "Created new user %s from Google OAuth (google_id=%s)",
                    user.id,
                    google_id,
                )

                # Auto-create org for new users (same as email registration)
                org_name = f"{full_name}'s Organization"
                slug = f"org-{user.id.hex[:8]}"
                existing_slug = await self.org_repository.get_by_slug(session, slug)
                suffix = 2
                while existing_slug:
                    slug = f"org-{user.id.hex[:8]}-{suffix}"
                    existing_slug = await self.org_repository.get_by_slug(session, slug)
                    suffix += 1
                org = await self.org_repository.create(
                    session=session,
                    name=org_name,
                    slug=slug,
                    plan="free",
                )
                await self.org_repository.add_member(
                    session=session,
                    org_id=org.id,
                    user_id=user.id,
                    role="owner",
                )

        if not user.is_active:
            raise UnauthorizedException("User account is disabled")

        # Step 4: Generate token pair
        tokens = self.auth_service._generate_token_pair(user.id)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self.auth_repository.create_refresh_token(
            session, user.id, tokens.refresh_token, expires_at
        )
        return tokens


google_auth_service = GoogleAuthService()
