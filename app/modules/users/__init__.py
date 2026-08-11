"""Public module interface."""

from __future__ import annotations

from app.modules.users.router import router
from app.modules.users.schemas import UserResponse, UserUpdateRequest
from app.modules.users.service import UserService

__all__ = ["UserResponse", "UserService", "UserUpdateRequest", "router"]
