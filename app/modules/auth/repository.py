import hashlib
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import (
    RefreshToken,
    EmailVerificationToken,
    PasswordResetToken,
)


class AuthRepository:
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # ── Refresh Token Methods ──────────────────────────────────────

    @staticmethod
    async def create_refresh_token(
        session: AsyncSession,
        user_id: uuid.UUID,
        token_str: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token_hash = AuthRepository._hash_token(token_str)
        rt = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )
        session.add(rt)
        await session.flush()
        return rt

    @staticmethod
    async def get_refresh_token(
        session: AsyncSession, token_str: str
    ) -> RefreshToken | None:
        token_hash = AuthRepository._hash_token(token_str)
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_refresh_token(
        session: AsyncSession, token_str: str
    ) -> bool:
        rt = await AuthRepository.get_refresh_token(session, token_str)
        if rt:
            rt.is_revoked = True
            session.add(rt)
            await session.flush()
            return True
        return False

    # ── Email Verification Token Methods ────────────────────────────

    @staticmethod
    async def create_email_verification_token(
        session: AsyncSession,
        user_id: uuid.UUID,
        token_str: str,
        expires_at: datetime,
    ) -> EmailVerificationToken:
        token_hash = AuthRepository._hash_token(token_str)
        evt = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_used=False,
        )
        session.add(evt)
        await session.flush()
        return evt

    @staticmethod
    async def get_email_verification_token(
        session: AsyncSession, token_str: str
    ) -> EmailVerificationToken | None:
        token_hash = AuthRepository._hash_token(token_str)
        query = select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_email_verification_used(
        session: AsyncSession, token_str: str
    ) -> bool:
        evt = await AuthRepository.get_email_verification_token(session, token_str)
        if evt:
            evt.is_used = True
            session.add(evt)
            await session.flush()
            return True
        return False

    @staticmethod
    async def revoke_all_email_verification_tokens(
        session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        """Mark all unused email verification tokens for a user as used."""
        query = select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.is_used == False,  # noqa: E712
        )
        result = await session.execute(query)
        for token in result.scalars():
            token.is_used = True
            session.add(token)
        await session.flush()

    # ── Password Reset Token Methods ─────────────────────────────────

    @staticmethod
    async def create_password_reset_token(
        session: AsyncSession,
        user_id: uuid.UUID,
        token_str: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        token_hash = AuthRepository._hash_token(token_str)
        prt = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_used=False,
        )
        session.add(prt)
        await session.flush()
        return prt

    @staticmethod
    async def get_password_reset_token(
        session: AsyncSession, token_str: str
    ) -> PasswordResetToken | None:
        token_hash = AuthRepository._hash_token(token_str)
        query = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_password_reset_used(
        session: AsyncSession, token_str: str
    ) -> bool:
        prt = await AuthRepository.get_password_reset_token(session, token_str)
        if prt:
            prt.is_used = True
            session.add(prt)
            await session.flush()
            return True
        return False

    @staticmethod
    async def revoke_all_password_reset_tokens(
        session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        """Mark all unused password reset tokens for a user as used."""
        query = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.is_used == False,  # noqa: E712
        )
        result = await session.execute(query)
        for token in result.scalars():
            token.is_used = True
            session.add(token)
        await session.flush()
