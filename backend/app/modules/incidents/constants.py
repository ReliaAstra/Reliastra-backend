from enum import Enum


class IncidentSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class IncidentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class RootCause(str, Enum):
    VENDOR_FAILURE = "vendor_failure"
    NETWORK_ISSUE = "network_issue"
    CONFIG_ERROR = "config_error"
    UNKNOWN = "unknown"


class CorrelationMethod(str, Enum):
    TEMPORAL = "temporal"
    MANUAL = "manual"
    ML = "ml"


DEFAULT_CORRELATION_CONFIDENCE: float = 0.85
TEMPORAL_WINDOW_SECONDS: int = 300
