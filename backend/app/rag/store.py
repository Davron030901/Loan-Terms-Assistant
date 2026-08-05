"""Qdrant Cloud vector store.

Cloud rather than embedded on purpose: Render's free tier has an ephemeral filesystem
(a local qdrant_data/ folder is wiped on every deploy), and embedded mode single-locks
its directory so ingestion and the web app could never run at the same time.

qdrant_client is imported lazily inside functions. It pulls in grpcio and numpy, which
costs ~300 ms of cold-start time we do not want on a sleeping free-tier instance, and it
lets the agent and chunking layers be unit-tested without a vector database present.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from app.config import settings
from app.core.errors import RetrievalError
from app.core.logging import logger

_NAMESPACE = uuid.NAMESPACE_URL
UPSERT_BATCH = 64


@lru_cache
def get_client() -> Any:
    settings.require_vector_store()
    from qdrant_client import QdrantClient

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=30,
        prefer_grpc=False,
    )


def point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic, so re-ingesting a document updates in place instead of duplicating."""
    return str(uuid.uuid5(_NAMESPACE, f"{doc_id}:{chunk_index}"))


def collection_exists() -> bool:
    return get_client().collection_exists(settings.qdrant_collection)


def ensure_collection(recreate: bool = False) -> None:
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    client = get_client()
    name = settings.qdrant_collection
    if recreate and client.collection_exists(name):
        client.delete_collection(name)
        logger.info("collection_deleted", extra={"collection": name})
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=settings.embed_dim, distance=Distance.COSINE),
        )
        logger.info("collection_created", extra={"collection": name, "dim": settings.embed_dim})
    # Without this index, per-document filtering degrades as the corpus grows.
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="doc_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception as exc:  # noqa: BLE001 - "already exists" is the normal case
        logger.debug("payload_index_skipped", extra={"detail": str(exc)})


def _doc_filter(doc_id: str) -> Any:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])


def delete_document(doc_id: str) -> None:
    from qdrant_client.models import FilterSelector

    if not collection_exists():
        return
    get_client().delete(
        collection_name=settings.qdrant_collection,
        points_selector=FilterSelector(filter=_doc_filter(doc_id)),
        wait=True,
    )


def make_point(vector: list[float], payload: dict[str, Any]) -> Any:
    from qdrant_client.models import PointStruct

    return PointStruct(
        id=point_id(payload["doc_id"], payload["chunk_index"]),
        vector=vector,
        payload=payload,
    )


def upsert_chunks(points: list[Any]) -> int:
    client = get_client()
    for start in range(0, len(points), UPSERT_BATCH):
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[start : start + UPSERT_BATCH],
            wait=True,
        )
    return len(points)


def count(doc_id: str | None = None) -> int:
    if not collection_exists():
        return 0
    result = get_client().count(
        collection_name=settings.qdrant_collection,
        count_filter=_doc_filter(doc_id) if doc_id else None,
        exact=True,
    )
    return int(result.count)


def search(vector: list[float], doc_id: str, limit: int) -> list[dict[str, Any]]:
    try:
        response = get_client().query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=_doc_filter(doc_id),
        )
    except Exception as exc:  # noqa: BLE001
        raise RetrievalError(f"Vector search failed: {exc}") from exc
    return [{"score": p.score, "payload": p.payload or {}} for p in response.points]


def collection_stats() -> dict[str, Any]:
    if not collection_exists():
        return {"collection": settings.qdrant_collection, "exists": False, "points": 0}
    info = get_client().get_collection(settings.qdrant_collection)
    return {
        "collection": settings.qdrant_collection,
        "exists": True,
        "points": info.points_count or 0,
        "dim": settings.embed_dim,
        "status": str(info.status),
    }
