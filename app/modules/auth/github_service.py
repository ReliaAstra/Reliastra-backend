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
    UnauthorizedException,
    ValidationException,
)
from app.core.security import get_password_hash
from app.infrastructure.redis_client import get_redis
from app.modules.auth.constants import TOKEN_TYPE_BEARER
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import TokenResponse
from app.modules.auth.service import AuthService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USERINFO_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"

# Redis key prefix for OAuth state tokens
_OAUTH_STATE_PREFIX = "oauth:github:state:"
_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


class GitHubAuthService:
    """Handles GitHub OAuth2 flow: token exchange, user creation/linking, token generation.

    Production features:
    - CSRF state validation via Redis
    - Verified primary email resolution from GitHub API
    - Automatic organization + agency creation for new users
    - Account linking when email matches existing user
    - Returns is_new_user flag for frontend routing
    - Handles private emails gracefully (uses noreply fallback)
    """

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
        if not settings.GITHUB_AUTH_ENABLED:
            raise AppException(
                "GitHub authentication is not enabled",
                status_code=403,
                code="GITHUB_AUTH_DISABLED",
            )
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            raise AppException(
                "GitHub OAuth is not configured (missing CLIENT_ID or CLIENT_SECRET)",
                status_code=500,
                code="GITHUB_AUTH_MISCONFIGURED",
            )

    async def _store_state(self, state_token: str) -> None:
        """Store the OAuth state token in Redis for CSRF validation."""
        try:
            redis = get_redis()
            await redis.set(f"{_OAUTH_STATE_PREFIX}{state_token}", "1", ex=_OAUTH_STATE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Failed to store OAuth state in Redis (CSRF protection degraded): %s", exc)

    async def _validate_state(self, state_token: str) -> bool:
        """Validate the OAuth state token against Redis. Returns True if valid."""
        try:
            redis = get_redis()
            key = f"{_OAUTH_STATE_PREFIX}{state_token}"
            exists = await redis.exists(key)
            if exists:
                # Delete on use (one-time token)
                await redis.delete(key)
                return True
            return False
        except Exception as exc:
            logger.warning("Failed to validate OAuth state via Redis: %s", exc)
            return True

    def get_authorization_url(self, state_token: str) -> str:
        """Build the GitHub OAuth authorization URL."""
        self._check_enabled()
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "response_type": "code",
            "scope": "read:user user:email",
            "state": state_token,
        }
        import urllib.parse
        return f"{GITHUB_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _github_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange the authorization code for GitHub access token."""
        self._check_enabled()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GITHUB_TOKEN_URL,
                json={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(
                    "GitHub token exchange failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise UnauthorizedException(
                    "Failed to exchange authorization code with GitHub"
                )
            data = resp.json()
            if "error" in data:
                logger.error("GitHub token error: %s", data)
                raise UnauthorizedException(
                    f"GitHub OAuth error: {data.get('error_description', data.get('error'))}"
                )
            return data

    async def get_github_user_info(
        self, access_token: str
    ) -> dict[str, Any]:
        """Fetch user profile from GitHub using the access token."""
        headers = self._github_headers(access_token)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GITHUB_USERINFO_URL, headers=headers)
            if resp.status_code != 200:
                logger.error(
                    "GitHub userinfo fetch failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise UnauthorizedException(
                    "Failed to retrieve user info from GitHub"
                )
            return resp.json()

    async def get_github_emails(
        self, access_token: str
    ) -> list[dict[str, Any]]:
        """Fetch user emails from GitHub (some users keep email private)."""
        headers = self._github_headers(access_token)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "GitHub emails fetch failed: status=%s (will use fallback)",
                    resp.status_code,
                )
                return []
            return resp.json()

    def _resolve_email(
        self, github_user: dict[str, Any], emails: list[dict[str, Any]]
    ) -> tuple[str | None, bool]:
        """
        Get the best available email from GitHub data.
        Returns (email, is_verified).

        Priority: profile email (if public) > primary verified email >
                  any verified email > noreply fallback (not verified).
        """
        # 1. Check if profile has a public email
        profile_email = github_user.get("email")
        if profile_email:
            # Profile email is always verified if present
            return profile_email, True

        # 2. Find primary verified email from emails list
        for email_entry in emails:
            if email_entry.get("primary") and email_entry.get("verified"):
                return email_entry["email"], True

        # 3. Use any verified email
        for email_entry in emails:
            if email_entry.get("verified"):
                return email_entry["email"], True

        # 4. Fallback: GitHub noreply address (NOT verified)
        login = github_user.get("login", "unknown")
        return f"{login}@users.noreply.github.com", False

    async def _create_org_and_agency(
        self,
        session: AsyncSession,
        user: "User",
        full_name: str,
    ) -> None:
        """Create a default organization and agency for a new OAuth user."""
        org_name = f"{full_name}'s Organization"
        slug = f"org-{user.id.hex[:8]}"
        existing_slug = await self.org_repository.get_by_slug(session, slug)
        suffix = 2
        while existing_slug:
            slug = f"org-{user.id.hex[:8]}-{suffix}"
            existing_slug = await self.org_repository.get_by_slug(
                session, slug
            )
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

        from app.modules.agencies.repository import AgencyRepository
        await AgencyRepository.create_application(
            session,
            org_id=org.id,
            name="Default",
            description="Default application",
        )

    async def authenticate_with_code(
        self, session: AsyncSession, code: str, state: str | None = None
    ) -> tuple[TokenResponse, bool]:
        """
        Full GitHub OAuth flow:
        1. Validate state token for CSRF protection
        2. Exchange code for access token
        3. Fetch GitHub user profile + emails
        4. Find or create local user
        5. Generate JWT token pair

        Returns (token_response, is_new_user).
        """
        # Step 0: Validate state if provided (CSRF protection)
        if state:
            is_valid = await self._validate_state(state)
            if not is_valid:
                logger.warning("Invalid or expired OAuth state token received (possible CSRF)")
                raise ValidationException(
                    "Invalid or expired authorization state. Please try again.",
                    details={"code": "INVALID_OAUTH_STATE"},
                )

        # Step 1: Exchange code
        token_data = await self.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise UnauthorizedException("No access token in GitHub response")

        # Step 2: Get user info and emails in parallel
        import asyncio

        github_user_task = self.get_github_user_info(access_token)
        github_emails_task = self.get_github_emails(access_token)
        github_user, github_emails = await asyncio.gather(
            github_user_task, github_emails_task
        )

        github_id = str(github_user.get("id"))
        github_login = github_user.get("login", "")
        github_name = github_user.get("name") or github_login
        github_avatar = github_user.get("avatar_url")

        email, email_verified = self._resolve_email(github_user, github_emails)

        if not github_id:
            raise ValidationException(
                "GitHub account did not return a valid user ID",
            )

        # Step 3: Find existing user by github_id or email
        user = await self.user_repository.get_by_github_id(session, github_id)
        is_new_user = False

        if not user:
            # Check if email already exists (account linking scenario)
            user = await self.user_repository.get_by_email(session, email)
            if user:
                # Link existing account with GitHub
                await self.user_repository.update(
                    session,
                    user,
                    github_id=github_id,
                    avatar_url=github_avatar or user.avatar_url,
                    auth_provider="github",
                )
                logger.info(
                    "Linked GitHub account %s to existing user %s",
                    github_id,
                    user.id,
                )
            else:
                # Create new user from GitHub data
                random_password = secrets.token_urlsafe(32)
                password_hash = get_password_hash(random_password)

                full_name = github_name if github_name else github_login
                user = await self.user_repository.create(
                    session=session,
                    email=email,
                    password_hash=password_hash,
                    full_name=full_name,
                    github_id=github_id,
                    avatar_url=github_avatar,
                    auth_provider="github",
                    # Auto-verify email only if GitHub confirmed it
                    is_email_verified=email_verified,
                )
                is_new_user = True
                logger.info(
                    "Created new user %s from GitHub OAuth (github_id=%s, login=%s)",
                    user.id,
                    github_id,
                    github_login,
                )

                # Auto-create org and agency (same as email registration)
                await self._create_org_and_agency(session, user, full_name)

        else:
            # Returning GitHub user — update avatar if changed
            if github_avatar:
                await self.user_repository.update(session, user, avatar_url=github_avatar)

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
        return tokens, is_new_user


github_auth_service = GitHubAuthService()
