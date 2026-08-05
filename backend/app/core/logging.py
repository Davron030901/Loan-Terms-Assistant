"""Structured JSON logging with a per-request correlation id."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "urllib3", "qdrant_client"):
        logging.getLogger(noisy).setLevel("WARNING")
    return logging.getLogger("loan_terms")


logger = logging.getLogger("loan_terms")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Read X-Request-ID from the client or mint one; echo it back on the response."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        set_request_id(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
