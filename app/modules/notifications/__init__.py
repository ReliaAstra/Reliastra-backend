"""Public module interface."""

from __future__ import annotations

from app.modules.notifications.router import router
from app.modules.notifications.schemas import AlertConfigResponse, AlertPayload
from app.modules.notifications.service import NotificationService

__all__ = ["AlertConfigResponse", "AlertPayload", "NotificationService", "router"]
