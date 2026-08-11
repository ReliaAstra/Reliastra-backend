import hashlib
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import RefreshToken


class AuthRepository:
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    async def create_refresh_token(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
        token_str: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token_hash = cls._hash_token(token_str)
        rt = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )
        session.add(rt)
        await session.flush()
        return rt

    @classmethod
    async def get_refresh_token(
        cls, session: AsyncSession, token_str: str
    ) -> RefreshToken | None:
        token_hash = cls._hash_token(token_str)
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def revoke_refresh_token(
        cls, session: AsyncSession, token_str: str
    ) -> bool:
        rt = await cls.get_refresh_token(session, token_str)
        if rt:
            rt.is_revoked = True
            session.add(rt)
            await session.flush()
            return True
        return False
