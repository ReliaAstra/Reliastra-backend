from __future__ import annotations

import functools
import logging
import uuid
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)


def audit_log(action: str, entity_type: str):
    """Decorator for admin mutation endpoints. Automatically logs to admin_audit_log.

    Usage::

        @audit_log(action="update_user", entity_type="user")
        async def update_user(...):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract the request and current_user from keyword args
            request: Request | None = kwargs.get("request")
            admin_user = kwargs.get("admin_user")
            result = await func(*args, **kwargs)

            # Fire-and-forget audit log via background task on request
            if request and admin_user:
                entity_id = kwargs.get("user_id") or kwargs.get("ticket_id") or ""
                _schedule_audit(
                    admin_user_id=admin_user.id,
                    admin_email=admin_user.email,
                    action=action,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    details={},
                )
            return result
        return wrapper
    return decorator


def _schedule_audit(
    admin_user_id: uuid.UUID,
    admin_email: str,
    action: str,
    entity_type: str,
    entity_id: str,
    ip_address: str | None,
    user_agent: str | None,
    details: dict[str, Any],
) -> None:
    """Schedule an audit log entry as a background task.

    Uses the request's background_tasks if available, otherwise falls back
    to a fire-and-forget async task.
    """
    import asyncio

    async def _write() -> None:
        try:
            from app.db.session import get_session_maker
            from app.modules.admin.models import AdminAuditLog

            session_maker = get_session_maker()
            async with session_maker() as session:
                entry = AdminAuditLog(
                    admin_user_id=admin_user_id,
                    admin_email=admin_email,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                session.add(entry)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to write admin audit log: %s", exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write())
    except RuntimeError:
        asyncio.run(_write())
