"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import get_auth_service
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, service: AuthService = Depends(get_auth_service)
) -> RegistrationResponse:
    return await service.register(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return await service.login(payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return await service.refresh(payload)


@router.post("/logout", status_code=204)
async def logout(
    payload: LogoutRequest, service: AuthService = Depends(get_auth_service)
) -> Response:
    await service.logout(payload)
    return Response(status_code=204)
