from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.rate_limit import ip_limiter, enforce_rate_limit
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
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.register(db, body)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.login(db, body)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.refresh(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(db, body.refresh_token)
