"""Central role hierarchy and permission checks."""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import ForbiddenError


class Role(StrEnum):
    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"


ROLE_LEVEL: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.ADMIN: 2,
    Role.OWNER: 3,
}


def ensure_role(actual: Role, required: Role) -> None:
    if ROLE_LEVEL[actual] < ROLE_LEVEL[required]:
        raise ForbiddenError(f"This action requires the {required.value} role or higher")
