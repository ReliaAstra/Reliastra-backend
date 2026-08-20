"""Tests for FIX 36: request-id propagation context."""

import pytest

from app.core.request_context import (
    get_request_id,
    get_user_id,
    set_request_id,
    set_user_id,
)


def test_request_id_context_defaults():
    assert get_request_id() is None
    assert get_user_id() is None


def test_request_id_context_roundtrip():
    set_request_id("req-abc-123")
    try:
        assert get_request_id() == "req-abc-123"
    finally:
        set_request_id(None)
    assert get_request_id() is None


def test_user_id_context_roundtrip():
    set_user_id("user-42")
    try:
        assert get_user_id() == "user-42"
    finally:
        set_user_id(None)


def test_middleware_sets_request_id_header():
    from app.main import RequestIdMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def call_next(request):
        return JSONResponse({"ok": True})

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "client": ("1.2.3.4", 1),
        }
    )
    import asyncio

    response = asyncio.run(RequestIdMiddleware(None).dispatch(request, call_next))
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_celery_tasks_accept_request_id_kwarg():
    """Tasks must accept and forward the propagated request id."""
    from app.modules.evidence.tasks import generate_evidence_report
    from app.modules.incidents.tasks import create_incident

    import inspect

    for task in (generate_evidence_report, create_incident):
        params = inspect.signature(task.run).parameters if hasattr(task, "run") else inspect.signature(task).parameters
        assert "request_id" in params
