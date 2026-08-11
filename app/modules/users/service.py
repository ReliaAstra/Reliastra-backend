import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.core.security import get_password_hash
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserResponse, UserUpdateRequest


class UserService:
    def __init__(self, repository: UserRepository = UserRepository()) -> None:
        self.repository = repository

    async def get_profile(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> UserResponse:
        user = await self.repository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")
        return UserResponse.model_validate(user)

    async def update_profile(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        request: UserUpdateRequest,
    ) -> UserResponse:
        user = await self.repository.get_by_id(session, user_id)
        if not user:
            raise ResourceNotFoundException("User not found")

        update_kwargs = {}
        if request.full_name is not None:
            update_kwargs["full_name"] = request.full_name
        if request.email is not None:
            existing = await self.repository.get_by_email(session, request.email)
            if existing and existing.id != user_id:
                raise ConflictException("Email is already registered by another user")
            update_kwargs["email"] = request.email
        if request.password is not None:
            update_kwargs["password_hash"] = get_password_hash(request.password)

        updated_user = await self.repository.update(session, user, **update_kwargs)
        return UserResponse.model_validate(updated_user)


user_service = UserService()
