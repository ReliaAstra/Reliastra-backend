import logging
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.modules.auth.constants import TOKEN_CLAIM_TYPE_REFRESH, TOKEN_TYPE_BEARER
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        auth_repository: AuthRepository = AuthRepository(),
        user_repository: UserRepository = UserRepository(),
        org_repository: OrganizationRepository = OrganizationRepository(),
    ) -> None:
        self.auth_repository = auth_repository
        self.user_repository = user_repository
        self.org_repository = org_repository

    def _generate_token_pair(self, user_id: uuid.UUID) -> TokenResponse:
        access_token = create_access_token(subject=str(user_id))
        refresh_token = create_refresh_token(subject=str(user_id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=TOKEN_TYPE_BEARER,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register(
        self, session: AsyncSession, request: RegisterRequest
    ) -> TokenResponse:
        existing = await self.user_repository.get_by_email(session, request.email)
        if existing:
            raise ConflictException("Email is already registered")

        password_hash = get_password_hash(request.password)
        user = await self.user_repository.create(
            session=session,
            email=request.email,
            password_hash=password_hash,
            full_name=request.full_name,
        )

        org_name = request.org_name or f"{request.full_name}'s Organization"
        slug = f"org-{user.id.hex[:8]}"
        # Ensure slug uniqueness (append suffix if collision)
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
        from app.modules.agencies.repository import AgencyRepository

        await AgencyRepository.create_application(
            session,
            org_id=org.id,
            name="Default",
            description="Default application",
        )

        # Process referral if ref_code provided
        if request.ref_code:
            from app.modules.referrals.service import referral_service
            await referral_service.process_referral_on_register(
                session=session,
                ref_code=request.ref_code,
                new_user_id=user.id,
                new_user_email=request.email,
                new_user_org_id=org.id,
            )

        # Bind partner attribution. This runs alongside — never instead of —
        # the PLG referral flow above: the two systems answer different
        # questions (peer rewards vs. commissionable partner ownership) and a
        # user can legitimately arrive through both.
        #
        # Attribution must never be able to fail a registration, so any
        # error here is logged and swallowed.
        if request.partner_visitor_id or request.partner_code:
            try:
                from app.modules.partners.tracking import tracking_service

                await tracking_service.bind_signup(
                    session,
                    user_id=user.id,
                    organization_id=org.id,
                    visitor_id=request.partner_visitor_id,
                    partner_code=request.partner_code,
                    campaign_code=request.partner_campaign_code,
                    email=request.email,
                )
            except Exception:
                logger.exception(
                    "Partner attribution failed during registration for user %s",
                    user.id,
                )

        tokens = self._generate_token_pair(user.id)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self.auth_repository.create_refresh_token(
            session, user.id, tokens.refresh_token, expires_at
        )
        return tokens

    async def login(
        self, session: AsyncSession, request: LoginRequest
    ) -> TokenResponse:
        user = await self.user_repository.get_by_email(session, request.email)
        if not user or not verify_password(request.password, user.password_hash):
            raise UnauthorizedException("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedException("User account is disabled")

        tokens = self._generate_token_pair(user.id)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self.auth_repository.create_refresh_token(
            session, user.id, tokens.refresh_token, expires_at
        )
        return tokens

    async def refresh(
        self, session: AsyncSession, refresh_token_str: str
    ) -> TokenResponse:
        payload = decode_token(refresh_token_str)
        if payload.get("type") != TOKEN_CLAIM_TYPE_REFRESH:
            raise UnauthorizedException("Invalid token type")

        stored_rt = await self.auth_repository.get_refresh_token(
            session, refresh_token_str
        )
        if stored_rt and stored_rt.is_revoked:
            raise UnauthorizedException("Refresh token has been revoked")

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise UnauthorizedException("Invalid token payload")

        user_id = uuid.UUID(user_id_str)
        user = await self.user_repository.get_by_id(session, user_id)
        if not user or not user.is_active:
            raise UnauthorizedException("User account not found or disabled")

        # FIX 28: token family reuse detection. When a token is presented
        # whose sequence is below the family's latest, it was already rotated
        # (or is a stolen copy of one) — revoke the entire family.
        family = stored_rt.token_family if stored_rt else uuid.uuid4()
        sequence = stored_rt.token_sequence if stored_rt else 1
        latest_sequence = await self.auth_repository.get_latest_sequence(
            session, family
        )
        if latest_sequence > sequence:
            await self.auth_repository.revoke_family(session, family)
            logger.warning(
                "Refresh token reuse detected for family %s — family revoked",
                family,
            )
            raise UnauthorizedException(
                "Refresh token reuse detected; session has been revoked"
            )

        tokens = self._generate_token_pair(user.id)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self.auth_repository.create_refresh_token(
            session,
            user.id,
            tokens.refresh_token,
            expires_at,
            token_family=family,
            token_sequence=sequence + 1,
        )
        if stored_rt:
            await self.auth_repository.revoke_refresh_token(
                session, refresh_token_str
            )
        return tokens

    async def logout(
        self, session: AsyncSession, refresh_token_str: str
    ) -> None:
        await self.auth_repository.revoke_refresh_token(
            session, refresh_token_str
        )


auth_service = AuthService()
