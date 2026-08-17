"""Tests for FIX 29: rate limiting keyed by X-Forwarded-For, not the LB IP."""

from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.rate_limit import client_ip_from_request


def _make_request(headers: dict | None = None, client_host: str = "10.0.0.5"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_uses_last_trusted_hop_from_xff():
    request = _make_request(
        {"x-forwarded-for": "203.0.113.9, 70.41.3.18"}, client_host="10.0.0.5"
    )
    # With one trusted hop, the LB appended 70.41.3.18 (the client);
    # the spoofed first entry must be ignored.
    assert client_ip_from_request(request) == "70.41.3.18"


def test_rejects_malformed_xff_and_falls_back_to_peer():
    request = _make_request(
        {"x-forwarded-for": "not-an-ip, garbage"}, client_host="10.1.2.3"
    )
    assert client_ip_from_request(request) == "10.1.2.3"


def test_spoofing_attempt_ignored():
    # A client appending its own XFF values cannot escape the trusted hop.
    request = _make_request(
        {"x-forwarded-for": "6.6.6.6, 10.0.0.5, 169.254.169.254"},
        client_host="10.0.0.5",
    )
    assert client_ip_from_request(request) == "169.254.169.254"


def test_no_xff_uses_socket_peer():
    request = _make_request({}, client_host="198.51.100.7")
    assert client_ip_from_request(request) == "198.51.100.7"
