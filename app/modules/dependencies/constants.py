"""Monitored endpoint protocol and plan limits."""

from __future__ import annotations

from enum import StrEnum

from app.modules.organizations.constants import Plan


class HttpMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"


PLAN_MIN_INTERVAL: dict[Plan, int] = {
    Plan.FREE: 300,
    Plan.STANDARD: 60,
    Plan.PROFESSIONAL: 30,
    Plan.AGENCY: 10,
}
PLAN_DEPENDENCY_LIMIT: dict[Plan, int] = {
    Plan.FREE: 3,
    Plan.STANDARD: 20,
    Plan.PROFESSIONAL: 100,
    Plan.AGENCY: 1000,
}
DEFAULT_REGIONS = ["us-east", "eu-west"]
