"""SECURITY GATE 1 - the scope guard.

Defence in depth, cheapest layer first:
  A. deterministic patterns  - zero cost, zero latency, cannot be talked around
  B. an LLM topic classifier - judgement for everything the patterns don't catch
  C. fail-closed parsing     - anything that isn't a clean ALLOW is a refusal
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.config import settings
from app.core import prompts
from app.core.llm import chat
from app.core.logging import logger

# Characters used to smuggle patterns past naive filters.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(all\s+|the\s+|your\s+)?(previous|above|prior|earlier)\s+(instruction|rule|prompt)",
    # An injection buried mid-question is still an injection: "…by the way, ignore your rules."
    r"ignore\s+(your|the|any|these|those)\s+\w*\s*(rule|instruction|guard|grounding|constraint|restriction)",
    r"(ignore|bypass|override|skip)\s+.{0,20}(grounding|citation|guard|safety|filter)",
    r"disregard\s+.{0,30}(rule|instruction|prompt|guideline)",
    r"forget\s+(everything|all|your)\s+(you|instruction|rule)",
    r"\byou\s+are\s+now\b",
    r"\bact\s+as\b",
    # "Pretend the fee is $500" is an attempt to plant a fact, not just a persona swap.
    r"\bpretend\b",
    r"\b(assume|imagine|suppose)\s+(the|that)\s+\w+(\s+\w+){0,3}\s+(is|are|was|were)\b",
    r"\brole[- ]?play\b",
    r"system\s+prompt",
    r"reveal\s+your\s+(prompt|instruction|rule|config)",
    r"(print|repeat|show|output)\s+(your|the)\s+(prompt|instruction|system|config|env)",
    r"repeat\s+everything\s+above",
    r"developer\s+mode",
    r"\bjailbreak\b",
    r"\bDAN\b",
    r"unrestricted\s+(assistant|mode|ai)",
    r"disable\s+your\s+(filter|guard|rule|restriction)",
    r"\bAPI[_ ]?KEY\b",
    r"\bsk-[A-Za-z0-9]",
    r"BEGIN\s+PRIVATE\s+KEY",
    r"\bbase64\b",
    r"the\s+document\s+says\s+you\s+must",
    # Bulk translation / rewriting is a different task, not a question about the terms.
    # Narrow on purpose: "what does this clause mean?" must still be allowed.
    r"\btranslate\s+(the\s+|this\s+)?(entire|whole|full|complete)?\s*(document|contract|agreement|terms|pdf|it)\b",
    r"\b(write|compose|draft|generate|produce)\s+.{0,40}\b(email|letter|blog|post|article|advert|marketing|poem|story|song)\b",
)

ADVICE_PATTERNS: tuple[str, ...] = (
    r"\bshould\s+i\b",
    r"\bshould\s+we\b",
    r"\bis\s+(this|it|that)\s+a\s+good\b",
    r"\bis\s+(this|it)\s+worth\b",
    r"\bis\s+(this|it)\s+fair\b",
    r"\bdo\s+you\s+recommend\b",
    r"\bwould\s+you\s+recommend\b",
    r"\bwhat\s+would\s+you\s+do\b",
    r"\badvise\s+me\b",
    r"\bgive\s+me\s+advice\b",
    r"\bbetter\s+(deal\s+)?than\b",
    r"\bcompared?\s+(it\s+)?(to|with)\s+(another|other|hsbc|chase|barclays)",
)

_INJECTION_RE = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_ADVICE_RE = [re.compile(p, re.I) for p in ADVICE_PATTERNS]
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)

Layer = Literal["pattern", "llm", "none"]


@dataclass
class ScopeVerdict:
    allowed: bool
    reason: str
    layer: Layer
    latency_ms: int = 0


def sanitise(question: str) -> str:
    """Strip the tricks before matching: zero-width joiners, control chars, NFKC lookalikes."""
    text = unicodedata.normalize("NFKC", question or "")
    text = text.translate(_ZERO_WIDTH)
    text = _CONTROL.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pattern_layer(text: str) -> ScopeVerdict | None:
    if len(text) < 3:
        return ScopeVerdict(False, "Question is too short.", "pattern")
    if len(text) > settings.max_question_chars:
        return ScopeVerdict(False, "Question exceeds the maximum length.", "pattern")
    if not _ALNUM.search(text):
        return ScopeVerdict(False, "Question contains no readable text.", "pattern")
    for pattern in _INJECTION_RE:
        if pattern.search(text):
            return ScopeVerdict(False, "Prompt-injection pattern detected.", "pattern")
    for pattern in _ADVICE_RE:
        if pattern.search(text):
            return ScopeVerdict(False, "Requests advice or an opinion.", "pattern")
    return None


def check(question: str) -> ScopeVerdict:
    started = time.perf_counter()
    text = sanitise(question)

    verdict = _pattern_layer(text)
    if verdict is not None:
        verdict.latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info("scope_guard", extra={"allowed": False, "layer": "pattern"})
        return verdict

    try:
        raw = chat(
            prompts.SCOPE_GUARD_PROMPT.format(scope=prompts.SCOPE, question=text),
            temperature=0,
            max_output_tokens=8,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed (R7)
        logger.warning("scope_guard_provider_error", extra={"detail": type(exc).__name__})
        return ScopeVerdict(
            False,
            "The topic gate could not be evaluated.",
            "llm",
            int((time.perf_counter() - started) * 1000),
        )

    token = re.sub(r"[^A-Z_]", "", raw.upper().split()[0] if raw.split() else "")
    allowed = token == "ALLOW"
    logger.info("scope_guard", extra={"allowed": allowed, "layer": "llm"})
    return ScopeVerdict(
        allowed=allowed,
        reason="In scope for this document's terms." if allowed else "Outside this document's terms.",
        layer="llm",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
