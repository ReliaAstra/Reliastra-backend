from enum import Enum


class ApiScope(str, Enum):
    READ_CHECKS = "read:checks"
    WRITE_DEPENDENCIES = "write:dependencies"
    READ_INCIDENTS = "read:incidents"
    READ_EVIDENCE = "read:evidence"
    WRITE_INCIDENTS = "write:incidents"
    WRITE_CHECKS = "write:checks"
    READ_DEPENDENCIES = "read:dependencies"
    READ_ORGANIZATIONS = "read:organizations"
    WRITE_ORGANIZATIONS = "write:organizations"
    READ_BILLING = "read:billing"
    WRITE_BILLING = "write:billing"
    READ_NOTIFICATIONS = "read:notifications"
    WRITE_NOTIFICATIONS = "write:notifications"
    READ_API_KEYS = "read:api_keys"
    WRITE_API_KEYS = "write:api_keys"


DEFAULT_SCOPES: list[str] = [ApiScope.READ_CHECKS.value, ApiScope.WRITE_DEPENDENCIES.value, ApiScope.READ_INCIDENTS.value, ApiScope.READ_EVIDENCE.value]

VALID_SCOPES: set[str] = {s.value for s in ApiScope}
