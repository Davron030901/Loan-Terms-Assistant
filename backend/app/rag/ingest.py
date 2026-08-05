"""PDF -> page-aware chunks -> embeddings -> Qdrant Cloud."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from app.core.llm import TASK_DOCUMENT, embed_batch, embedding_fingerprint
from app.core.logging import logger
from app.rag import registry, store
from app.rag.chunking import chunk_pdf, extract_pages


@dataclass
class IngestReport:
    doc_id: str
    pages: int
    chunks: int
    seconds: float

    def as_dict(self) -> dict:
        return asdict(self)


def ingest_document(doc_id: str) -> IngestReport:
    started = time.perf_counter()
    document = registry.get_document(doc_id)
    path = registry.pdf_path(doc_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing PDF for '{doc_id}': {path}")

    language = document.get("language", "en")
    chunks = chunk_pdf(path, language=language)
    pages = len(extract_pages(path))
    if not chunks:
        raise ValueError(f"No extractable text in {path.name}. Is it a scan rather than text?")

    fingerprint = embedding_fingerprint()
    logger.info(
        "ingest_start",
        extra={"doc_id": doc_id, "pages": pages, "chunks": len(chunks), **fingerprint},
    )

    vectors = embed_batch([c.text for c in chunks], task_type=TASK_DOCUMENT)

    store.ensure_collection()
    store.delete_document(doc_id)  # idempotent: replace, never duplicate
    points = [
        store.make_point(
            vector,
            {
                "doc_id": doc_id,
                "text": chunk.text,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "bank": document["bank"],
                "title": document["title"],
                "language": language,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                # Which vector space this point belongs to. Retrieval refuses to search
                # across a mismatch rather than returning meaningless neighbours.
                **fingerprint,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    store.upsert_chunks(points)

    report = IngestReport(
        doc_id=doc_id,
        pages=pages,
        chunks=len(points),
        seconds=round(time.perf_counter() - started, 2),
    )
    logger.info("ingest_done", extra=report.as_dict())
    return report


def ingest_all(recreate: bool = False, skip_existing: bool = False) -> list[IngestReport]:
    """Ingest every document, surviving a failure in any one of them.

    Each document is upserted on its own, so a run that dies half way still leaves the
    completed documents in place. Continuing means one rate-limit wall does not cost you
    the work already done.
    """
    if recreate:
        store.ensure_collection(recreate=True)
    else:
        store.ensure_collection()

    reports: list[IngestReport] = []
    failures: list[tuple[str, str]] = []
    for doc_id in registry.document_ids():
        if skip_existing and store.count(doc_id) > 0:
            logger.info("ingest_skipped", extra={"doc_id": doc_id, "reason": "already indexed"})
            continue
        try:
            reports.append(ingest_document(doc_id))
        except Exception as exc:  # noqa: BLE001 - report and carry on
            failures.append((doc_id, str(exc)[:160]))
            logger.error("ingest_failed", extra={"doc_id": doc_id, "detail": str(exc)[:200]})

    if failures:
        logger.error("ingest_incomplete", extra={"failed": [d for d, _ in failures]})
        for doc_id, detail in failures:
            print(f"  FAILED  {doc_id}: {detail}")
        print("\n  Re-run with --resume to pick up only what is missing.")
    return reports
