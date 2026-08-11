"""User persistence queries."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return cast(
            User | None, await self.session.scalar(select(User).where(User.email == email.lower()))
        )

    async def create(self, email: str, password_hash: str, full_name: str) -> User:
        user = User(email=email.lower(), password_hash=password_hash, full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, values: dict[str, object]) -> User:
        for field, value in values.items():
            setattr(user, field, value)
        await self.session.flush()
        return user
