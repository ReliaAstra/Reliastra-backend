import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.api_keys.models import ApiKey


class ApiKeyRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, key_id: uuid.UUID
    ) -> ApiKey | None:
        query = select(ApiKey).where(ApiKey.id == key_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_hashed_key(
        session: AsyncSession, hashed_key: str
    ) -> ApiKey | None:
        """Exact-match lookup — only valid for deterministic hashes (legacy
        SHA-256). bcrypt hashes must be located via ``list_by_prefix``."""
        query = select(ApiKey).where(ApiKey.hashed_key == hashed_key)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_prefix(
        session: AsyncSession, prefix: str
    ) -> list[ApiKey]:
        query = (
            select(ApiKey)
            .where(ApiKey.prefix == prefix)
            .order_by(ApiKey.created_at.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_for_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[ApiKey]:
        query = (
            select(ApiKey)
            .where(ApiKey.org_id == org_id)
            .order_by(ApiKey.created_at.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        prefix: str,
        hashed_key: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> ApiKey:
        api_key = ApiKey(
            org_id=org_id,
            name=name,
            prefix=prefix,
            hashed_key=hashed_key,
            scopes=scopes,
            expires_at=expires_at,
        )
        session.add(api_key)
        await session.flush()
        return api_key

    @staticmethod
    async def delete(session: AsyncSession, api_key: ApiKey) -> None:
        await session.delete(api_key)
        await session.flush()

    @staticmethod
    async def update_last_used(session: AsyncSession, api_key: ApiKey) -> None:
        api_key.last_used_at = datetime.now(timezone.utc)
        session.add(api_key)
        await session.flush()

    @staticmethod
    async def update_last_used_batch(
        session: AsyncSession,
        timestamps: dict[uuid.UUID, datetime],
    ) -> int:
        """Set ``last_used_at`` for many keys at once (FIX 21 flush path).

        Uses ``greatest`` so a newer value already in the DB is never
        overwritten by an older Redis timestamp.
        """
        from sqlalchemy import case, func, update

        if not timestamps:
            return 0
        whens = [
            (ApiKey.id == key_id, func.greatest(ApiKey.last_used_at, value))
            for key_id, value in timestamps.items()
        ]
        stmt = (
            update(ApiKey)
            .where(ApiKey.id.in_([key_id for key_id in timestamps]))
            .values(last_used_at=case(*whens, else_=ApiKey.last_used_at))
        )
        result = await session.execute(stmt)
        return int(result.rowcount or 0)
