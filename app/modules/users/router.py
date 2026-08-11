"""Current-user API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import Principal, get_current_principal, get_user_service
from app.modules.users.schemas import UserResponse, UserUpdateRequest
from app.modules.users.service import UserService

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    principal: Principal = Depends(get_current_principal),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.get(principal.require_user_id())


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    principal: Principal = Depends(get_current_principal),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await service.update(principal.require_user_id(), payload)
