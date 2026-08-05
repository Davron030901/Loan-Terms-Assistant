"""Liveness and readiness.

/api/health is deliberately dependency-free: the frontend pings it on mount to wake a
sleeping Render free-tier instance, and it must answer instantly.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.config import settings
from app.rag import registry
from app.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", version=settings.app_version, environment=settings.environment
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    from app.rag import store

    try:
        points = store.count()
    except Exception:  # noqa: BLE001 - readiness never raises, it reports
        points = 0
    if points == 0:
        response.status_code = 503
    from app.core.llm import chat_provider_names, embedding_fingerprint

    fingerprint = embedding_fingerprint()
    return ReadyResponse(
        ready=points > 0,
        collection=settings.qdrant_collection,
        points=points,
        documents=len(registry.all_documents()),
        chat_providers=chat_provider_names(),
        embed_provider=str(fingerprint["embed_provider"]),
        embed_model=str(fingerprint["embed_model"]),
    )
