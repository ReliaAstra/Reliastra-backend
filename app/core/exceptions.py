import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_SERVER_ERROR",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details if details is not None else []


class ResourceNotFoundException(AppException):
    def __init__(
        self,
        message: str = "Resource not found",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            details=details,
        )


class ForbiddenException(AppException):
    def __init__(
        self,
        message: str = "Forbidden",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            details=details,
        )


class UnauthorizedException(AppException):
    def __init__(
        self,
        message: str = "Unauthorized",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            details=details,
        )


class ConflictException(AppException):
    def __init__(
        self,
        message: str = "Resource conflict",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            details=details,
        )


class RateLimitExceededException(AppException):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMIT_EXCEEDED",
            details=details,
        )


class ValidationException(AppException):
    def __init__(
        self,
        message: str = "Validation error",
        details: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=422,
            code="VALIDATION_ERROR",
            details=details,
        )


def _normalize_details(
    details: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if details is None:
        return []
    if isinstance(details, list):
        return details
    if "errors" in details and isinstance(details["errors"], list):
        return [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "issue": err.get("msg", "invalid"),
            }
            for err in details["errors"]
            if isinstance(err, dict)
        ]
    return [{"field": key, "issue": str(value)} for key, value in details.items()]


def error_payload(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": _normalize_details(details),
            "request_id": request_id or get_request_id() or "unknown",
        }
    }


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or get_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=request_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or get_request_id()
        details = []
        for err in exc.errors():
            loc = [p for p in err.get("loc", []) if p not in {"body", "query", "path", "header"}]
            details.append(
                {
                    "field": ".".join(str(p) for p in loc) or str(err.get("loc", ["request"])[-1]),
                    "issue": err.get("msg", "invalid"),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details=details,
                request_id=request_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or get_request_id()
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMIT_EXCEEDED",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=str(exc.detail),
                details=[],
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception occurred: %s", exc)
        request_id = getattr(request.state, "request_id", None) or get_request_id()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred",
                details=[],
                request_id=request_id,
            ),
        )
