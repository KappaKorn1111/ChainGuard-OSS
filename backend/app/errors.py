from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from .logging import get_logger

logger = get_logger("chainguard.errors")


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: Any = Field(default_factory=dict)
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details if details is not None else {}
        self.headers = headers


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details if details is not None else {},
            request_id=request_id(request),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            exc.code,
            exc.message,
            exc.details,
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return error_response(
            request,
            422,
            "validation_error",
            "request validation failed",
            details,
        )

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            401: "authentication_required",
            403: "permission_denied",
            404: "not_found",
            409: "conflict",
            413: "payload_too_large",
            429: "rate_limited",
            503: "service_unavailable",
        }
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        details = {} if isinstance(exc.detail, str) else exc.detail
        return error_response(
            request,
            exc.status_code,
            codes.get(exc.status_code, "http_error"),
            message,
            details,
            exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, _: IntegrityError) -> JSONResponse:
        return error_response(request, 409, "conflict", "resource conflicts with existing data")

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_request_error",
            request_id=request_id(request),
            error_type=type(exc).__name__,
        )
        return error_response(request, 500, "internal_error", "an unexpected error occurred")
