"""Registration and token lifecycle business logic."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import jwt

from app.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    TokenClaims,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
)
from app.modules.organizations.service import OrganizationService
from app.modules.users.service import UserService


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        users: UserService,
        organizations: OrganizationService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.users = users
        self.organizations = organizations
        self.settings = settings

    async def register(self, request: RegisterRequest) -> RegistrationResponse:
        user = await self.users.create_identity(
            str(request.email), hash_password(request.password), request.full_name
        )
        organization = await self.organizations.create_personal(
            user.id, user.full_name, str(user.email)
        )
        tokens = await self._issue_pair(user.id)
        return RegistrationResponse(user=user, organization=organization, tokens=tokens)

    async def login(self, request: LoginRequest) -> TokenResponse:
        user = await self.users.auth_record(str(request.email))
        if (
            user is None
            or not user.is_active
            or not verify_password(request.password, user.password_hash)
        ):
            raise UnauthorizedError("Invalid email or password")
        return await self._issue_pair(user.id)

    async def refresh(self, request: RefreshRequest) -> TokenResponse:
        claims = self._decode_refresh(request.refresh_token)
        if not await self.repository.is_refresh_allowed(str(claims.jti)):
            raise UnauthorizedError("Refresh token has been revoked")
        secret = self.settings.secret_key.get_secret_value()
        access = create_token(
            claims.sub,
            secret,
            "access",
            timedelta(minutes=self.settings.access_token_expire_minutes),
        )
        return TokenResponse(
            access_token=access, expires_in=self.settings.access_token_expire_minutes * 60
        )

    async def logout(self, request: LogoutRequest) -> None:
        claims = self._decode_refresh(request.refresh_token)
        await self.repository.revoke_refresh(str(claims.jti))

    async def _issue_pair(self, user_id: UUID) -> TokenResponse:
        secret = self.settings.secret_key.get_secret_value()
        access_ttl = timedelta(minutes=self.settings.access_token_expire_minutes)
        refresh_ttl = timedelta(days=self.settings.refresh_token_expire_days)
        access = create_token(user_id, secret, "access", access_ttl)
        refresh = create_token(user_id, secret, "refresh", refresh_ttl)
        claims = decode_token(refresh, secret, "refresh")
        await self.repository.allow_refresh(
            str(claims.jti), str(user_id), int(refresh_ttl.total_seconds())
        )
        return TokenResponse(
            access_token=access, refresh_token=refresh, expires_in=int(access_ttl.total_seconds())
        )

    def _decode_refresh(self, token: str) -> TokenClaims:
        try:
            return decode_token(token, self.settings.secret_key.get_secret_value(), "refresh")
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired refresh token") from exc
