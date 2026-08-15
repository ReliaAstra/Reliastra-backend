import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.users.models import User


class UserRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
        query = select(User).where(User.id == user_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> User | None:
        query = select(User).where(User.email == email.lower())
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_google_id(session: AsyncSession, google_id: str) -> User | None:
        query = select(User).where(User.google_id == google_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_github_id(session: AsyncSession, github_id: str) -> User | None:
        query = select(User).where(User.github_id == github_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        email: str,
        password_hash: str,
        full_name: str,
        is_superuser: bool = False,
        is_email_verified: bool = False,
        google_id: str | None = None,
        github_id: str | None = None,
        avatar_url: str | None = None,
        auth_provider: str | None = None,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            is_superuser=is_superuser,
            is_email_verified=is_email_verified,
            google_id=google_id,
            github_id=github_id,
            avatar_url=avatar_url,
            auth_provider=auth_provider,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def update(session: AsyncSession, user: User, **kwargs: Any) -> User:
        for key, value in kwargs.items():
            if value is not None and hasattr(user, key):
                if key == "email" and isinstance(value, str):
                    setattr(user, key, value.lower())
                else:
                    setattr(user, key, value)
        session.add(user)
        await session.flush()
        return user
