from enum import Enum


class HttpMethod(str, Enum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"


DEFAULT_REGIONS: list[str] = ["us-east", "eu-west"]
DEFAULT_EXPECTED_STATUS_CODES: list[int] = [200]
DEFAULT_TIMEOUT_SECONDS: int = 10
