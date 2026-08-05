"""Find the clauses that answer a question - and know when there aren't any."""

from __future__ import annotations

import re

from app.config import settings
from app.core.llm import TASK_QUERY, embed, embedding_fingerprint
from app.core.errors import RetrievalError
from app.core.logging import logger
from app.rag import store
from app.rag.constants import expand
from app.schemas import Chunk

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
DEDUP_THRESHOLD = 0.85


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _dedupe(chunks: list[Chunk]) -> list[Chunk]:
    """Overlapping windows mean near-duplicate neighbours; keep the best-scoring one."""
    kept: list[Chunk] = []
    kept_tokens: list[set[str]] = []
    for chunk in chunks:
        tokens = _tokens(chunk.text)
        if any(_overlap(tokens, seen) > DEDUP_THRESHOLD for seen in kept_tokens):
            continue
        kept.append(chunk)
        kept_tokens.append(tokens)
    return kept


def _assert_same_vector_space(payload: dict) -> None:
    """A query embedded by one model cannot meaningfully search another model's vectors.

    The numbers still work - cosine similarity happily returns neighbours - but they are
    the wrong clauses, and every health check stays green while the agent cites nonsense.
    Fail loudly instead.
    """
    indexed = payload.get("embed_model")
    if not indexed:
        return  # index predates fingerprinting; nothing to compare against
    current = embedding_fingerprint()["embed_model"]
    if indexed != current:
        raise RetrievalError(
            f"The index was built with '{indexed}' but EMBED_PROVIDER now resolves to "
            f"'{current}'. Re-run: python -m scripts.ingest_all --all --recreate"
        )


def search(question: str, doc_id: str, k: int | None = None) -> list[Chunk]:
    """Return the surviving evidence, or [] when there is none.

    Returning [] is a feature: the pipeline then answers "Not stated in the terms."
    without ever asking the model to write anything.
    """
    limit = k or settings.retriever_top_k
    vector = embed(expand(question), task_type=TASK_QUERY)
    hits = store.search(vector, doc_id=doc_id, limit=limit * 2)
    if hits:
        _assert_same_vector_space(hits[0]["payload"])

    chunks = [
        Chunk(
            text=hit["payload"].get("text", ""),
            page=int(hit["payload"].get("page", 0)),
            score=float(hit["score"]),
            chunk_index=int(hit["payload"].get("chunk_index", 0)),
            doc_id=hit["payload"].get("doc_id", doc_id),
            language=hit["payload"].get("language", "en"),
        )
        for hit in hits
        if float(hit["score"]) >= settings.retriever_score_floor
    ]
    chunks = _dedupe(chunks)[:limit]
    chunks.sort(key=lambda c: (-c.score, c.page))
    return chunks


def build_context(chunks: list[Chunk]) -> str:
    """The exact string handed to the answer and verification prompts."""
    return "\n\n".join(f"[p. {c.page}] {c.text}" for c in chunks)
