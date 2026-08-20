"""Header-based tenant resolution.

Organization context is no longer encoded in the URL. Clients MUST send one of:

* ``X-Organization-ID``
* ``Reliastra-Organization``

The value is a UUID. Middleware stores it on ``request.state.organization_id``
so ``get_current_org`` can authorize membership without a path parameter.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.exceptions import error_payload
from fastapi.responses import JSONResponse

ORG_HEADER_CANDIDATES = ("x-organization-id", "reliastra-organization")


def extract_organization_id(request: Request) -> uuid.UUID | None:
    for name in ORG_HEADER_CANDIDATES:
        raw = request.headers.get(name)
        if not raw:
            continue
        try:
            return uuid.UUID(raw.strip())
        except ValueError:
            raise ValueError(raw)
    return None


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            org_id = extract_organization_id(request)
        except ValueError as exc:
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=400,
                content=error_payload(
                    code="VALIDATION_ERROR",
                    message="Invalid organization header",
                    details=[{"field": "X-Organization-ID", "issue": f"must be a UUID, got {exc}"}],
                    request_id=request_id,
                ),
            )
        request.state.organization_id = org_id
        return await call_next(request)
