"""The whole agent: guard -> retrieve -> answer -> verify.

Every exit path returns a fully populated trace, and no path ever falls back to an
ungrounded model answer.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import AsyncIterator

from app.config import settings
from app.core import prompts
from app.core.logging import get_request_id, logger
from app.rag import retrieve
from app.schemas import (
    AnswerTrace,
    ChatResponse,
    Chunk,
    GroundingTrace,
    RetrievalTrace,
    ScopeTrace,
    Trace,
    Verdict,
)


def _fingerprint(question: str) -> str:
    """Log what was asked without logging the question itself (R8)."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]


def _response(
    verdict: Verdict,
    answer: str,
    doc_id: str,
    trace: Trace,
    *,
    citations=None,
    chunks: list[Chunk] | None = None,
) -> ChatResponse:
    return ChatResponse(
        request_id=get_request_id(),
        verdict=verdict,
        answer=answer,
        citations=citations or [],
        chunks=chunks or [],
        doc_id=doc_id,
        trace=trace,
    )


def _run(question: str, doc_id: str) -> ChatResponse:
    # Imported here so a missing vector store can't break module import in tests.
    from app.agent import answer as answer_mod
    from app.agent import citations as citations_mod
    from app.agent import guard, verify

    started = time.perf_counter()
    trace = Trace()

    def finish(verdict: Verdict, text: str, **kw) -> ChatResponse:
        trace.total_latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "agent_result",
            extra={
                "verdict": verdict,
                "doc_id": doc_id,
                "question_sha": _fingerprint(question),
                "latency_ms": trace.total_latency_ms,
            },
        )
        return _response(verdict, text, doc_id, trace, **kw)

    # ── 1. INPUT GATE ────────────────────────────────────────────────────────
    scope = guard.check(question)
    trace.scope_guard = ScopeTrace(
        verdict="ALLOW" if scope.allowed else "REFUSE",
        reason=scope.reason,
        layer=scope.layer,
        latency_ms=scope.latency_ms,
    )
    if not scope.allowed:
        return finish("refused_out_of_scope", prompts.REFUSAL_OUT_OF_SCOPE)

    # ── 2. RETRIEVE ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    chunks = retrieve.search(question, doc_id=doc_id)
    trace.retrieval = RetrievalTrace(
        chunks=len(chunks),
        top_score=round(max((c.score for c in chunks), default=0.0), 4),
        pages=[c.page for c in chunks],
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    if not chunks:
        # No evidence -> no answer. The model is never asked to improvise.
        trace.grounding_guard = GroundingTrace(verdict="GROUNDED", method="none")
        return finish("not_stated", prompts.NOT_STATED)

    # ── 3. ANSWER ────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    draft = answer_mod.write(question, chunks)
    repaired = False

    if citations_mod.is_not_stated(draft):
        trace.answer = AnswerTrace(
            model=settings.gemini_chat_model, latency_ms=int((time.perf_counter() - t0) * 1000)
        )
        trace.grounding_guard = GroundingTrace(verdict="GROUNDED", method="none")
        return finish("not_stated", prompts.NOT_STATED, chunks=chunks)

    # ── 3b. CITATION VALIDATION (one repair retry, then blocked) ─────────────
    report = citations_mod.validate(draft, chunks)
    if report.needs_repair:
        draft = answer_mod.repair(question, chunks, draft)
        repaired = True
        if citations_mod.is_not_stated(draft):
            trace.answer = AnswerTrace(
                model=settings.gemini_chat_model,
                repaired=True,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            trace.grounding_guard = GroundingTrace(verdict="GROUNDED", method="none")
            return finish("not_stated", prompts.NOT_STATED, chunks=chunks)
        report = citations_mod.validate(draft, chunks)

    trace.answer = AnswerTrace(
        model=settings.gemini_chat_model,
        repaired=repaired,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )

    if not report.ok:
        trace.grounding_guard = GroundingTrace(verdict="NOT_GROUNDED", method="citation")
        logger.info("blocked_citation", extra={"reason": report.reason})
        return finish("blocked_not_grounded", prompts.BLOCKED_MESSAGE, chunks=chunks)

    # ── 4. OUTPUT GATE ───────────────────────────────────────────────────────
    grounding = verify.is_grounded(draft, chunks)
    trace.grounding_guard = GroundingTrace(
        verdict="GROUNDED" if grounding.grounded else "NOT_GROUNDED",
        method=grounding.method,
        latency_ms=grounding.latency_ms,
    )
    if not grounding.grounded:
        logger.info("blocked_grounding", extra={"reason": grounding.reason})
        return finish("blocked_not_grounded", prompts.BLOCKED_MESSAGE, chunks=chunks)

    return finish("answered", draft, citations=report.citations, chunks=chunks)


async def ask(question: str, doc_id: str) -> ChatResponse:
    """Async wrapper with a hard ceiling on the whole pipeline."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run, question, doc_id),
            timeout=settings.request_timeout_seconds,
        )
    except TimeoutError:
        logger.warning("pipeline_timeout", extra={"doc_id": doc_id})
        trace = Trace(total_latency_ms=settings.request_timeout_seconds * 1000)
        return _response("error", "That took too long. Please try again.", doc_id, trace)


async def ask_events(question: str, doc_id: str) -> AsyncIterator[tuple[str, dict]]:
    """Server-sent events for the UI.

    Tokens are deliberately NOT streamed before verification: an unverified figure must
    never appear on screen, and correctness outranks perceived speed (API contract, §8).
    """
    yield "trace", {"stage": "scope_guard", "status": "running"}
    response = await ask(question, doc_id)
    t = response.trace

    if t.scope_guard:
        yield "trace", {"stage": "scope_guard", "status": "done", **t.scope_guard.model_dump()}
    if t.retrieval:
        yield "trace", {"stage": "retrieval", "status": "done", **t.retrieval.model_dump()}
    if t.answer:
        yield "trace", {"stage": "answer", "status": "done", **t.answer.model_dump()}
    if t.grounding_guard:
        yield "trace", {
            "stage": "grounding_guard",
            "status": "done",
            **t.grounding_guard.model_dump(),
        }

    for piece in _word_stream(response.answer):
        yield "token", {"text": piece}
        await asyncio.sleep(0.012)

    yield "final", response.model_dump()
    yield "done", {}


def _word_stream(text: str, size: int = 4) -> list[str]:
    words = text.split(" ")
    return [" ".join(words[i : i + size]) + (" " if i + size < len(words) else "")
            for i in range(0, len(words), size)]
