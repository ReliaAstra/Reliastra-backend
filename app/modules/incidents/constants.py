"""Incident status, severity, root-cause, and correlation enums."""

from __future__ import annotations

from enum import StrEnum


class IncidentSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class RootCause(StrEnum):
    VENDOR_FAILURE = "vendor_failure"
    NETWORK_ISSUE = "network_issue"
    CONFIG_ERROR = "config_error"
    UNKNOWN = "unknown"


class CorrelationMethod(StrEnum):
    TEMPORAL = "temporal"
    MANUAL = "manual"


CORRELATION_WINDOW_SECONDS = 300
TEMPORAL_CONFIDENCE = 0.85
