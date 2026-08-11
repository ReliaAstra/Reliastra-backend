"""User identity business operations."""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserAuthDTO, UserResponse, UserUpdateRequest


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def create_identity(self, email: str, password_hash: str, full_name: str) -> UserResponse:
        if await self.repository.get_by_email(email):
            raise ConflictError("A user with this email already exists")
        user = await self.repository.create(email, password_hash, full_name)
        return UserResponse.model_validate(user)

    async def auth_record(self, email: str) -> UserAuthDTO | None:
        user = await self.repository.get_by_email(email)
        if user is None:
            return None
        return UserAuthDTO.model_validate(user, from_attributes=True)

    async def get(self, user_id: UUID) -> UserResponse:
        user = await self.repository.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return UserResponse.model_validate(user)

    async def update(self, user_id: UUID, request: UserUpdateRequest) -> UserResponse:
        user = await self.repository.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        values = request.model_dump(exclude_unset=True)
        if email := values.get("email"):
            existing = await self.repository.get_by_email(str(email))
            if existing and existing.id != user_id:
                raise ConflictError("A user with this email already exists")
            values["email"] = str(email).lower()
        return UserResponse.model_validate(await self.repository.update(user, values))
