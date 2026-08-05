"""The document registry: the closed list of documents this agent may talk about."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.errors import UnknownDocumentError

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "documents.json"


@lru_cache
def _registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def all_documents() -> list[dict[str, Any]]:
    return list(_registry()["documents"])


def document_ids() -> list[str]:
    return [doc["doc_id"] for doc in all_documents()]


def default_doc_id() -> str:
    return _registry().get("default_doc_id") or settings.default_doc_id


def get_document(doc_id: str) -> dict[str, Any]:
    for doc in all_documents():
        if doc["doc_id"] == doc_id:
            return doc
    raise UnknownDocumentError(
        f"Unknown document '{doc_id}'. Available: {', '.join(document_ids())}."
    )


def resolve_doc_id(doc_id: str | None) -> str:
    """Fall back to the default document, but never to an unknown one."""
    if not doc_id:
        return default_doc_id()
    get_document(doc_id)  # raises UnknownDocumentError
    return doc_id


def pdf_path(doc_id: str) -> Path:
    return settings.docs_dir / get_document(doc_id)["file"]
