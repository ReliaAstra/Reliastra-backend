"""Structured logging for the API and Celery workers.

Production (or ``LOG_JSON=true``) emits one JSON object per line so log
aggregators can parse level, request id, and exception without regex.
Development keeps a short human-readable format.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.request_context import get_request_id, get_user_id


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        user_id = get_user_id()
        if user_id:
            payload["user_id"] = user_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)


def _should_use_json() -> bool:
    from app.config import settings

    if settings.LOG_JSON:
        return True
    return settings.ENVIRONMENT == "production"


def configure_logging(level: int = logging.INFO) -> None:
    """Install a process-wide formatter. Safe to call more than once."""
    root = logging.getLogger()
    formatter: logging.Formatter
    if _should_use_json():
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )

    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(formatter)
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)
