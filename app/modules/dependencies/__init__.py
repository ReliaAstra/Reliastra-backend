"""Public module interface."""

from __future__ import annotations

from app.modules.dependencies.router import router
from app.modules.dependencies.schemas import DependencyResponse
from app.modules.dependencies.service import DependencyService

__all__ = ["DependencyResponse", "DependencyService", "router"]
