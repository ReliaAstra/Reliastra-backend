from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService, auth_service

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


def get_auth_service() -> AuthService:
    return auth_service


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.register(db, request)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.login(db, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.refresh(db, request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(db, request.refresh_token)
