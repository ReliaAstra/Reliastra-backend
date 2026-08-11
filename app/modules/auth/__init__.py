"""Public module interface."""

from __future__ import annotations

from app.modules.auth.router import router
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.modules.auth.service import AuthService

__all__ = ["AuthService", "LoginRequest", "RegisterRequest", "TokenResponse", "router"]
