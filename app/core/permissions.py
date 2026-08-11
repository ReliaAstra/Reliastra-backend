from enum import Enum
from app.core.exceptions import ForbiddenException


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ROLE_HIERARCHY: dict[str, int] = {
    Role.OWNER.value: 40,
    Role.ADMIN.value: 30,
    Role.MEMBER.value: 20,
    Role.VIEWER.value: 10,
}


def get_role_level(role: str) -> int:
    return ROLE_HIERARCHY.get(role.lower(), 0)


def has_permission(user_role: str, required_role: str) -> bool:
    """
    Check if user_role satisfies required_role based on hierarchy:
    owner > admin > member > viewer.
    """
    return get_role_level(user_role) >= get_role_level(required_role)


def require_permission(user_role: str, required_role: str) -> None:
    if not has_permission(user_role, required_role):
        raise ForbiddenException(
            f"Action requires at least '{required_role}' role, but user has '{user_role}' role."
        )


class Plan(str, Enum):
    FREE = "free"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    AGENCY = "agency"


PLAN_CHECK_INTERVALS: dict[str, int] = {
    Plan.FREE.value: 300,
    Plan.STANDARD.value: 60,
    Plan.PROFESSIONAL.value: 30,
    Plan.AGENCY.value: 30,
}


PLAN_DEPENDENCY_LIMITS: dict[str, int] = {
    Plan.FREE.value: 5,
    Plan.STANDARD.value: 25,
    Plan.PROFESSIONAL.value: 100,
    Plan.AGENCY.value: 500,
}


def get_min_check_interval(plan: str) -> int:
    return PLAN_CHECK_INTERVALS.get(plan.lower(), 300)


def get_dependency_limit(plan: str) -> int:
    return PLAN_DEPENDENCY_LIMITS.get(plan.lower(), 5)
