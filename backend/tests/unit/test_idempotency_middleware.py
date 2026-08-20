"""Tests for FIX 7 (per-user idempotency scoping) and FIX 40 (cache non-2xx).

The merged implementation derives the principal as:
* ``user:{jwt sub}``  — verified JWT subject
* ``key:{sha256[:32]}`` — digest of the API key credential
* ``ip:{client ip}``  — anonymous callers
"""

from app.main import IdempotencyMiddleware


def test_identity_scoped_by_api_key():
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope_a = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": Headers({"x-api-key": "rel_aaa"}).raw,
    }
    scope_b = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": Headers({"x-api-key": "rel_bbb"}).raw,
    }
    request_a = Request(scope_a)
    request_b = Request(scope_b)
    principal_a = IdempotencyMiddleware._idempotency_principal(request_a)
    principal_b = IdempotencyMiddleware._idempotency_principal(request_b)
    assert principal_a != principal_b
    assert principal_a.startswith("key:")


def test_identity_scoped_by_jwt():
    from starlette.requests import Request
    from app.core.security import create_access_token

    token_a = create_access_token(subject="user-a")
    token_b = create_access_token(subject="user-b")

    def make_request(token: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [(b"authorization", f"Bearer {token}".encode())],
            }
        )

    principal_a = IdempotencyMiddleware._idempotency_principal(make_request(token_a))
    principal_b = IdempotencyMiddleware._idempotency_principal(make_request(token_b))
    assert principal_a == "user:user-a"
    assert principal_b == "user:user-b"
    assert principal_a != principal_b


def test_identity_ip_fallback_without_credentials():
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("203.0.113.5", 1234),
        }
    )
    assert (
        IdempotencyMiddleware._idempotency_principal(request)
        == "ip:203.0.113.5"
    )


def test_cacheable_statuses_fix_40():
    assert IdempotencyMiddleware._is_cacheable_status(200) is True
    assert IdempotencyMiddleware._is_cacheable_status(201) is True
    assert IdempotencyMiddleware._is_cacheable_status(404) is True
    assert IdempotencyMiddleware._is_cacheable_status(409) is True
    assert IdempotencyMiddleware._is_cacheable_status(422) is True
    # 5xx and auth failures must never be cached.
    assert IdempotencyMiddleware._is_cacheable_status(500) is False
    assert IdempotencyMiddleware._is_cacheable_status(503) is False
    assert IdempotencyMiddleware._is_cacheable_status(401) is False
    assert IdempotencyMiddleware._is_cacheable_status(403) is False
