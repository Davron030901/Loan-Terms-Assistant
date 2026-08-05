"""SECURITY GATE 2 - the grounding guard.

Two independent checks, cheap one first:
  1. a deterministic numeric audit - every figure in the answer must appear in the context
  2. an LLM entailment check on a fresh call with no memory of how the answer was written

The numeric audit is the highest-value code in this repo: it catches the one failure that
actually hurts someone, a wrong interest rate or fee, without spending a token.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

from app.config import settings
from app.core import prompts
from app.core.llm import chat
from app.core.logging import logger
from app.rag.retrieve import build_context
from app.schemas import Chunk

Method = Literal["numeric", "llm", "citation", "none"]

# Numbers only: never let a run of dots in a table of contents become a "figure".
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*\s?%?")
_DURATION = re.compile(r"\b(\d+(?:[.,]\d+)*)\s*(day|days|month|months|year|years|week|weeks)\b", re.I)
_CITATION_BLOCK = re.compile(r"\(\s*pp?\.\s*[^)]*\)", re.I)


@dataclass
class GroundingVerdict:
    grounded: bool
    method: Method
    reason: str = ""
    latency_ms: int = 0


def _canonical(token: str) -> str:
    """25,000.50 and 25000.50 are the same number; 25% and 25 % are the same figure."""
    return token.replace(",", "").replace(" ", "").rstrip(".").lower()


def _numbers_in(text: str) -> set[str]:
    return {_canonical(t) for t in _NUMBER.findall(text) if any(ch.isdigit() for ch in t)}


def numeric_audit(answer: str, context: str) -> tuple[bool, str]:
    """Return (ok, reason). Every figure asserted must be present in the evidence."""
    stripped = _CITATION_BLOCK.sub(" ", answer)  # page numbers are not claims about money
    context_numbers = _numbers_in(context)
    # A duration written as "30 days" in the answer may appear as "30" in the context.
    context_numbers |= {_canonical(m.group(1)) for m in _DURATION.finditer(context)}

    for token in _numbers_in(stripped):
        if token in context_numbers:
            continue
        # 25.0 vs 25 - accept an exact-value match written differently
        try:
            value = float(token.rstrip("%"))
        except ValueError:
            return False, f"Figure '{token}' does not appear in the retrieved clauses."
        if any(_safe_float(other) == value for other in context_numbers):
            continue
        return False, f"Figure '{token}' does not appear in the retrieved clauses."
    return True, ""


def _safe_float(token: str) -> float | None:
    try:
        return float(token.rstrip("%"))
    except ValueError:
        return None


def is_grounded(answer: str, chunks: list[Chunk]) -> GroundingVerdict:
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    # "Not stated in the terms." is always grounded - it is the honest answer.
    from app.agent.citations import is_not_stated

    if is_not_stated(answer):
        return GroundingVerdict(True, "none", "not_stated is always grounded", elapsed())

    context = build_context(chunks)

    ok, reason = numeric_audit(answer, context)
    if not ok:
        logger.info("grounding_guard", extra={"grounded": False, "method": "numeric"})
        return GroundingVerdict(False, "numeric", reason, elapsed())

    try:
        raw = chat(
            prompts.GROUNDING_PROMPT.format(context=context, answer=answer),
            temperature=0,
            max_output_tokens=settings.verdict_max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed (R7)
        logger.warning("grounding_provider_error", extra={"detail": type(exc).__name__})
        # Blocking is right here - an unverified answer must never ship - but the reason
        # is an outage, not a detected fabrication.
        return GroundingVerdict(False, "none", "The verifier could not be reached.", elapsed())

    # NOT_GROUNDED is checked first: it contains "GROUNDED" as a substring, so word-level
    # parsing is the only safe way to read it.
    verdict = prompts.read_verdict(raw, "GROUNDED", "NOT_GROUNDED")
    if verdict is None:
        logger.warning("grounding_no_verdict", extra={"reply": raw[:80]})
        return GroundingVerdict(False, "llm", "The verifier returned no verdict.", elapsed())
    grounded = verdict
    logger.info("grounding_guard", extra={"grounded": grounded, "method": "llm"})
    return GroundingVerdict(
        grounded=grounded,
        method="llm",
        reason="" if grounded else "The verifier could not trace every claim to the document.",
        latency_ms=elapsed(),
    )
