"""Citation extraction and validation.

This is a guard, not a formatting nicety. A model that cites p. 12 when it was only
shown pages 2, 6 and 7 is fabricating, and the answer must be blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import prompts
from app.schemas import Chunk, Citation

# (p. 4)  ·  (p. 4, p. 7)  ·  (pp. 4, 7)
_CITATION_BLOCK = re.compile(r"\(\s*pp?\.\s*([0-9]+(?:\s*(?:,|and|;)\s*(?:p\.\s*)?[0-9]+)*)\s*\)", re.I)
_PAGE_NUM = re.compile(r"\d+")
# A claim worth citing: a figure, a percentage, a currency amount or a duration.
_FACTUAL = re.compile(
    r"(\d+(?:[.,]\d+)*\s*%)|([$€£₹₫]\s?\d)|(\b\d+(?:[.,]\d+)*\s*(?:days?|months?|years?|business days?)\b)|(\b\d+(?:[.,]\d+)*\b)",
    re.I,
)

SNIPPET_CHARS = 600


@dataclass
class CitationReport:
    ok: bool
    citations: list[Citation] = field(default_factory=list)
    cited_pages: list[int] = field(default_factory=list)
    invalid_pages: list[int] = field(default_factory=list)
    needs_repair: bool = False
    reason: str = ""


def extract_citations(answer: str) -> list[int]:
    pages: list[int] = []
    for block in _CITATION_BLOCK.findall(answer or ""):
        pages.extend(int(n) for n in _PAGE_NUM.findall(block))
    seen: set[int] = set()
    return [p for p in pages if not (p in seen or seen.add(p))]


def is_not_stated(answer: str) -> bool:
    return (answer or "").strip().rstrip(".").strip().lower() == prompts.NOT_STATED.rstrip(".").lower()


def has_factual_claim(answer: str) -> bool:
    stripped = _CITATION_BLOCK.sub(" ", answer or "")
    return bool(_FACTUAL.search(stripped))


def attach_snippets(pages: list[int], chunks: list[Chunk]) -> list[Citation]:
    """For each cited page, the best-scoring chunk from that page - real evidence for the UI."""
    citations: list[Citation] = []
    for page in pages:
        candidates = [c for c in chunks if c.page == page]
        if not candidates:
            continue
        best = max(candidates, key=lambda c: c.score)
        quote = best.text[:SNIPPET_CHARS] + ("…" if len(best.text) > SNIPPET_CHARS else "")
        citations.append(Citation(page=page, quote=quote, score=round(best.score, 4)))
    return citations


def validate(answer: str, chunks: list[Chunk]) -> CitationReport:
    if is_not_stated(answer):
        return CitationReport(ok=True, reason="not_stated is exempt from citation rules")

    available = {c.page for c in chunks}
    cited = extract_citations(answer)

    invalid = [p for p in cited if p not in available]
    if invalid:
        return CitationReport(
            ok=False,
            cited_pages=cited,
            invalid_pages=invalid,
            reason=f"Answer cited page(s) {invalid} that were never retrieved.",
        )

    if not cited:
        if has_factual_claim(answer):
            return CitationReport(
                ok=False,
                needs_repair=True,
                reason="Answer states a figure but carries no page citation.",
            )
        return CitationReport(
            ok=False,
            needs_repair=True,
            reason="Answer carries no page citation.",
        )

    return CitationReport(ok=True, citations=attach_snippets(cited, chunks), cited_pages=cited)
