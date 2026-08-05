"""The closed list of documents this agent may talk about."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.rag import registry
from app.schemas import DocumentInfo, DocumentsResponse

router = APIRouter(tags=["documents"])

_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, int]] = {}


def _chunk_count(doc_id: str) -> int:
    now = time.time()
    hit = _cache.get(doc_id)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        from app.rag import store

        count = store.count(doc_id)
    except Exception:  # noqa: BLE001 - the list must render even if Qdrant is down
        count = 0
    _cache[doc_id] = (now, count)
    return count


def _to_info(doc: dict) -> DocumentInfo:
    return DocumentInfo(
        doc_id=doc["doc_id"],
        bank=doc["bank"],
        title=doc["title"],
        jurisdiction=doc["jurisdiction"],
        language=doc["language"],
        pages=doc["pages"],
        chunks=_chunk_count(doc["doc_id"]),
        source_url=doc.get("source_url", ""),
        is_default=bool(doc.get("is_default")),
    )


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents() -> DocumentsResponse:
    return DocumentsResponse(
        default_doc_id=registry.default_doc_id(),
        documents=[_to_info(doc) for doc in registry.all_documents()],
    )


@router.get("/documents/{doc_id}", response_model=DocumentInfo)
async def get_document(doc_id: str) -> DocumentInfo:
    return _to_info(registry.get_document(doc_id))  # raises UnknownDocumentError -> 400
