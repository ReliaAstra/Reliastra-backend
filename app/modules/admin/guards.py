from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.db.session import get_db
from app.dependencies import get_current_user
from app.modules.users.models import User


async def require_system_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Require system admin access. Returns the User (not Organization)."""
    if not current_user.is_system_admin:
        raise ForbiddenException("System admin access required")
    return current_user
