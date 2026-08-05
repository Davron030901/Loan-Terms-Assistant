"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded

from app.api import routes_chat, routes_docs, routes_health
from app.config import settings
from app.core.errors import register_exception_handlers
from app.core.limiter import limiter
from app.core.logging import RequestIdMiddleware, configure_logging, get_request_id
from app.core.security import SecurityHeadersMiddleware

logger = configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"settings": settings.redacted()})

    # An unindexed collection is the most common cause of "it answers nothing" - and it
    # looks identical to a working system from the outside. Check once, and shout.
    try:
        from app.rag import store

        points = store.count()
        if points == 0:
            logger.error(
                "index_is_empty",
                extra={
                    "action": "run: python -m scripts.ingest_all --all --recreate",
                    "consequence": "every question will return 'Not stated in the terms.'",
                },
            )
        else:
            logger.info("index_ready", extra={"points": points})
    except Exception as exc:  # noqa: BLE001 - never block boot on a vector-store probe
        logger.error("index_unreachable", extra={"detail": str(exc)[:200]})
    if settings.auto_ingest:
        try:
            from app.rag import ingest, store

            if store.count() == 0:
                logger.info("auto_ingest_start")
                ingest.ingest_all(recreate=True)
        except Exception as exc:  # noqa: BLE001 - never block boot on ingestion
            logger.warning("auto_ingest_failed", extra={"detail": str(exc)})
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Loan Terms Assistant API",
        description=(
            "A scoped, grounded assistant for bank loan Terms & Conditions. "
            "Two security gates: a scope guard on input, a grounding guard on output."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "30"},
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests. Try again in about 30 seconds.",
                    "request_id": get_request_id(),
                }
            },
        )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type", "x-request-id"],
        expose_headers=["x-request-id"],
        max_age=600,
    )

    register_exception_handlers(app)

    app.include_router(routes_health.router, prefix="/api")
    app.include_router(routes_docs.router, prefix="/api")
    app.include_router(routes_chat.router, prefix="/api")

    @app.get("/", include_in_schema=False)
    async def root():
        return {"service": "loan-terms-assistant", "docs": "/api/docs", "health": "/api/health"}

    return app


app = create_app()
