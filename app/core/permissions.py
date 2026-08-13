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


# Pricing page check intervals (seconds)
PLAN_CHECK_INTERVALS: dict[str, int] = {
    Plan.FREE.value: 60,          # 1-minute
    Plan.STANDARD.value: 15,       # 15-second
    Plan.PROFESSIONAL.value: 5,   # 5-second
    Plan.AGENCY.value: 5,         # 5-second
}


# Pricing page vendor (dependency) limits
PLAN_DEPENDENCY_LIMITS: dict[str, int] = {
    Plan.FREE.value: 5,
    Plan.STANDARD.value: 25,
    Plan.PROFESSIONAL.value: 10_000,  # Effectively unlimited; 10k safety cap
    Plan.AGENCY.value: 10_000,       # Effectively unlimited; 10k safety cap
}


# Monthly prices in USD (used for Paystack amount calculation in kobo)
PLAN_PRICES_USD: dict[str, int] = {
    Plan.STANDARD.value: 49,
    Plan.PROFESSIONAL.value: 99,
    Plan.AGENCY.value: 0,  # Custom pricing — not self-serve
}


# Founding customer discount: 40% off standard and professional plans for lifetime
FOUNDING_DISCOUNT_PCT: int = 40
FOUNDING_MAX_SPOTS: int = 25


def get_min_check_interval(plan: str) -> int:
    return PLAN_CHECK_INTERVALS.get(plan.lower(), 60)


def get_dependency_limit(plan: str) -> int:
    return PLAN_DEPENDENCY_LIMITS.get(plan.lower(), 5)


def get_plan_price_usd(plan: str) -> int:
    return PLAN_PRICES_USD.get(plan.lower(), 0)


def get_discounted_price_usd(plan: str) -> int:
    """Calculate the founding-customer discounted price.
    Returns 0 for free/agency plans or if the plan has no base price.
    """
    base = PLAN_PRICES_USD.get(plan.lower(), 0)
    if base <= 0:
        return 0
    discount = base * FOUNDING_DISCOUNT_PCT // 100
    return base - discount
