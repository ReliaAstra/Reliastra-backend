"""Tests for FIX 7 (per-user idempotency scoping) and FIX 40 (cache non-2xx)."""

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
    assert IdempotencyMiddleware._identity(request_a) != IdempotencyMiddleware._identity(request_b)
    assert IdempotencyMiddleware._identity(request_a).startswith("apikey:")


def test_identity_scoped_by_jwt():
    from starlette.requests import Request

    scope_a = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"authorization", b"Bearer token-user-a")],
    }
    scope_b = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"authorization", b"Bearer token-user-b")],
    }
    assert IdempotencyMiddleware._identity(Request(scope_a)) != IdempotencyMiddleware._identity(
        Request(scope_b)
    )


def test_identity_anonymous_without_credentials():
    from starlette.requests import Request

    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []}
    )
    assert IdempotencyMiddleware._identity(request) == "anonymous"


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
