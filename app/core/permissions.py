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
    STARTER = "starter"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    AGENCY = "agency"


# ── Pricing Tier Configuration (matches pricing page) ────────────────────────
# All values are sourced from the official Reliastra pricing page.

# Monthly prices in USD (used for Paystack amount calculation in kobo)
PLAN_PRICES_USD: dict[str, int] = {
    Plan.FREE.value: 0,
    Plan.STARTER.value: 19,
    Plan.STANDARD.value: 49,
    Plan.PROFESSIONAL.value: 99,
    Plan.AGENCY.value: 199,
}

# Vendor (dependency) monitoring limits per plan
PLAN_DEPENDENCY_LIMITS: dict[str, int] = {
    Plan.FREE.value: 3,
    Plan.STARTER.value: 10,
    Plan.STANDARD.value: 30,
    Plan.PROFESSIONAL.value: 100,
    Plan.AGENCY.value: 500,
}

# Minimum check intervals in seconds per plan
PLAN_CHECK_INTERVALS: dict[str, int] = {
    Plan.FREE.value: 60,           # 1-minute
    Plan.STARTER.value: 60,        # 1-minute
    Plan.STANDARD.value: 15,       # 15-second
    Plan.PROFESSIONAL.value: 5,    # 5-second
    Plan.AGENCY.value: 5,          # 5-second
}

# Data retention in days per plan
PLAN_RETENTION_DAYS: dict[str, int] = {
    Plan.FREE.value: 1,             # 24-hour retention
    Plan.STARTER.value: 7,
    Plan.STANDARD.value: 30,
    Plan.PROFESSIONAL.value: 90,
    Plan.AGENCY.value: 90,
}

# Plan feature flags — used by the public pricing endpoint and frontend
PLAN_FEATURES: dict[str, dict] = {
    Plan.FREE.value: {
        "custom_endpoint_urls": True,
        "data_retention_days": 1,
        "email_alerts": True,
        "basic_incident_detection": True,
        "slack_alerts": False,
        "api_access": False,
        "attribution": False,
        "evidence_generation": False,
        "historical_analysis": False,
        "custom_branded_evidence": False,
        "client_groups_isolation": False,
        "client_facing_reports": False,
        "agency_branding": False,
    },
    Plan.STARTER.value: {
        "custom_endpoint_urls": True,
        "data_retention_days": 7,
        "email_alerts": True,
        "basic_incident_detection": True,
        "slack_alerts": False,
        "api_access": False,
        "attribution": "limited",
        "evidence_generation": False,
        "historical_analysis": True,
        "custom_branded_evidence": False,
        "client_groups_isolation": False,
        "client_facing_reports": False,
        "agency_branding": False,
    },
    Plan.STANDARD.value: {
        "custom_endpoint_urls": True,
        "data_retention_days": 30,
        "email_alerts": True,
        "basic_incident_detection": True,
        "slack_alerts": True,
        "api_access": True,
        "attribution": "deterministic",
        "evidence_generation": True,
        "historical_analysis": True,
        "custom_branded_evidence": False,
        "client_groups_isolation": False,
        "client_facing_reports": False,
        "agency_branding": False,
    },
    Plan.PROFESSIONAL.value: {
        "custom_endpoint_urls": True,
        "data_retention_days": 90,
        "email_alerts": True,
        "basic_incident_detection": True,
        "slack_alerts": True,
        "api_access": True,
        "attribution": "deterministic",
        "evidence_generation": True,
        "historical_analysis": True,
        "custom_branded_evidence": True,
        "client_groups_isolation": False,
        "client_facing_reports": False,
        "agency_branding": False,
    },
    Plan.AGENCY.value: {
        "custom_endpoint_urls": True,
        "data_retention_days": 90,
        "email_alerts": True,
        "basic_incident_detection": True,
        "slack_alerts": True,
        "api_access": True,
        "attribution": "deterministic",
        "evidence_generation": True,
        "historical_analysis": True,
        "custom_branded_evidence": True,
        "client_groups_isolation": True,
        "client_facing_reports": True,
        "agency_branding": True,
    },
}

# Display tags for the pricing page
PLAN_TAGS: dict[str, str | None] = {
    Plan.FREE.value: None,
    Plan.STARTER.value: None,
    Plan.STANDARD.value: "most_popular",
    Plan.PROFESSIONAL.value: None,
    Plan.AGENCY.value: "built_for_agencies",
}

# Display descriptions for the pricing page
PLAN_DESCRIPTIONS: dict[str, str] = {
    Plan.FREE.value: "Start measuring your dependencies.",
    Plan.STARTER.value: "Track more of your stack.",
    Plan.STANDARD.value: "Investigate and prove dependency failures.",
    Plan.PROFESSIONAL.value: "Operate dependency intelligence at team scale.",
    Plan.AGENCY.value: "Manage reliability across your entire client portfolio.",
}

# Backward-compatible alias
PLAN_AMOUNTS = PLAN_PRICES_USD


# ── Helper Functions ──────────────────────────────────────────────────────────


def get_min_check_interval(plan: str) -> int:
    return PLAN_CHECK_INTERVALS.get(plan.lower(), 60)


def get_dependency_limit(plan: str) -> int:
    return PLAN_DEPENDENCY_LIMITS.get(plan.lower(), 3)


def get_plan_price_usd(plan: str) -> int:
    return PLAN_PRICES_USD.get(plan.lower(), 0)


def get_retention_days(plan: str) -> int:
    return PLAN_RETENTION_DAYS.get(plan.lower(), 1)


def is_valid_plan(plan: str) -> bool:
    """Check if a plan string is a valid plan value."""
    return plan.lower() in {p.value for p in Plan}


def is_paid_plan(plan: str) -> bool:
    """Check if a plan requires payment."""
    return get_plan_price_usd(plan) > 0
