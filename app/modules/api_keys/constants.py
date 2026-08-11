"""API key scope vocabulary."""

from __future__ import annotations

from enum import StrEnum


class ApiScope(StrEnum):
    READ_ORGANIZATION = "read:organization"
    READ_DEPENDENCIES = "read:dependencies"
    WRITE_DEPENDENCIES = "write:dependencies"
    READ_CHECKS = "read:checks"
    READ_INCIDENTS = "read:incidents"
    WRITE_INCIDENTS = "write:incidents"
    READ_EVIDENCE = "read:evidence"
    GENERATE_EVIDENCE = "generate:evidence"
    READ_DASHBOARD = "read:dashboard"
    MANAGE_NOTIFICATIONS = "manage:notifications"


ALLOWED_SCOPES = {scope.value for scope in ApiScope}
