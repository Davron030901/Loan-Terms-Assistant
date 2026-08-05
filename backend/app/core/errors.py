"""Typed application errors and the single JSON error envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_request_id, logger

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI


class AppError(Exception):
    code = "internal_error"
    http_status = 500
    message = "Something went wrong."

    def __init__(self, message: str | None = None, *, code: str | None = None):
        self.message = message or self.message
        if code:
            self.code = code
        super().__init__(self.message)


class ConfigError(AppError):
    code = "config_error"
    http_status = 500
    message = "The server is misconfigured."


class ProviderError(AppError):
    code = "provider_error"
    http_status = 502
    message = "The AI provider is unavailable. Please try again."


class RetrievalError(AppError):
    code = "retrieval_error"
    http_status = 502
    message = "The document index is unavailable."


class UnknownDocumentError(AppError):
    code = "unknown_document"
    http_status = 400
    message = "Unknown document."


class InvalidQuestionError(AppError):
    code = "invalid_question"
    http_status = 400
    message = "That question could not be processed."


class RateLimitedError(AppError):
    code = "rate_limited"
    http_status = 429
    message = "Too many requests. Please slow down."


def _envelope(code: str, message: str, status: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": get_request_id()}},
    )


def register_exception_handlers(app: "FastAPI") -> None:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        logger.warning("app_error", extra={"code": exc.code, "detail": exc.message})
        return _envelope(exc.code, exc.message, exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return _envelope("invalid_request", "The request body was not valid.", 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return _envelope("http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        # Never leak internal exception text to the client (R7).
        logger.exception("unhandled_exception", extra={"detail": type(exc).__name__})
        return _envelope("internal_error", "Something went wrong on our side.", 500)
