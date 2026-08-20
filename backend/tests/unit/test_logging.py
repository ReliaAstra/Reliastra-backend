"""Structured JSON logging."""

import json
import logging

from app.core.logging import JsonFormatter
from app.core.request_context import set_request_id, set_user_id


def test_json_formatter_includes_request_context():
    set_request_id("req-123")
    set_user_id("user-9")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        set_request_id(None)
        set_user_id(None)

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "user-9"
    assert "timestamp" in payload
