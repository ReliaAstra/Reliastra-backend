"""Public module interface."""

from __future__ import annotations

from app.modules.dashboard.router import router
from app.modules.dashboard.schemas import DashboardSummary, DependencyHealth
from app.modules.dashboard.service import DashboardService

__all__ = ["DashboardSummary", "DashboardService", "DependencyHealth", "router"]
