from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user
from app.db.session import get_db
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse, UserUpdateRequest
from app.modules.users.service import UserService, user_service

router = APIRouter(prefix="/v1/users", tags=["Users"])


def get_user_service() -> UserService:
    return user_service


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.get_profile(db, current_user.id)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.update_profile(db, current_user.id, request)
