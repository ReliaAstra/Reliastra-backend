"""Billing plan feature matrix."""

from __future__ import annotations

from app.modules.organizations.constants import Plan

PLAN_FEATURES: dict[Plan, set[str]] = {
    Plan.FREE: {"monitoring"},
    Plan.STANDARD: {"monitoring", "evidence"},
    Plan.PROFESSIONAL: {"monitoring", "evidence", "advanced_regions"},
    Plan.AGENCY: {"monitoring", "evidence", "advanced_regions", "multi_client"},
}
