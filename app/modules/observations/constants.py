from enum import Enum


class ObservationSourceType(str, Enum):
    VENDOR_PROBE = "vendor_probe"
    CUSTOMER_CHECK = "customer_check"
    SYNTHETIC = "synthetic"


class ErrorType(str, Enum):
    NONE = "none"
    TIMEOUT = "timeout"
    DNS_FAILURE = "dns_failure"
    TLS_FAILURE = "tls_failure"
    CONNECTION_REFUSED = "connection_refused"
    HTTP_ERROR = "http_error"


ERROR_TYPE_NONE = ErrorType.NONE.value
