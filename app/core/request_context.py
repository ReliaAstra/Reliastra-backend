"""Process-wide request context for distributed tracing.

The HTTP layer stores the incoming ``X-Request-ID`` here so that any
service-layer code that dispatches background work (Celery tasks, scheduler
enqueues) can propagate the same identifier without threading it through
every function signature.
"""

from __future__ import annotations

from contextvars import ContextVar

#: Current X-Request-ID, set by ``RequestIdMiddleware`` in ``app.main``.
request_id_var: ContextVar[str | None] = ContextVar(
    "request_id", default=None
)

#: Current authenticated principal (user id or "apikey:<id>"), set by
#: ``get_current_user`` in ``app.dependencies``.
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_request_id() -> str | None:
    """Return the active request id, or ``None`` outside a request."""
    return request_id_var.get()


def set_request_id(request_id: str | None):
    """Set the active request id for the current context.

    Returns the context token so callers can restore the previous value.
    """
    return request_id_var.set(request_id)


def get_user_id() -> str | None:
    """Return the active authenticated principal, or ``None``."""
    return user_id_var.get()


def set_user_id(user_id: str | None):
    """Set the active authenticated principal for the current context.

    Returns the context token so callers can restore the previous value.
    """
    return user_id_var.set(user_id)
