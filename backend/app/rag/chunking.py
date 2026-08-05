"""Page-aware chunking.

Why not naive slicing: `text[i:i+900]` cuts sentences and clause numbers in half, which
is the number one cause of broken citations and of figures that no longer match the
contract. Every chunk here stays inside exactly one page, so the page number attached to
it is always literally true.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from pypdf import PdfReader

from app.config import settings

# Sentence-ish boundary: end punctuation followed by whitespace, or a numbered clause head.
_SENTENCE_SPLIT = re.compile(r"(?<=[.;:!?])\s+|\n(?=\s*\d+\.\d*\s)")
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_MULTISPACE = re.compile(r"[ \t ]+")
_MULTINEWLINE = re.compile(r"\n{3,}")
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)

MIN_CHUNK_ALNUM = 60


@dataclass
class PageChunk:
    text: str
    page: int
    chunk_index: int = 0
    char_start: int = 0
    char_end: int = 0
    meta: dict = field(default_factory=dict)


def _normalise(raw: str) -> str:
    """Tidy whitespace without ever touching digits, currency symbols or punctuation."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # inter-\nest -> interest
    text = _MULTISPACE.sub(" ", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def _repeated_lines(pages: list[str], threshold: float = 0.6) -> set[str]:
    """Running headers/footers appear on most pages and only dilute the embeddings."""
    if len(pages) < 4:
        return set()
    counter: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.split("\n") if line.strip()]
        for line in set(lines[:2] + lines[-2:]):
            if 3 <= len(line) <= 90:
                counter[line] += 1
    cutoff = max(2, int(len(pages) * threshold))
    return {line for line, count in counter.items() if count >= cutoff}


def _strip_boilerplate(text: str, boilerplate: set[str]) -> str:
    if not boilerplate:
        return text
    kept = [line for line in text.split("\n") if line.strip() not in boilerplate]
    return "\n".join(kept).strip()


def _alnum_len(text: str) -> int:
    return len(_ALNUM.findall(text))


def _pack(sentences: list[str], size: int, overlap: int) -> list[str]:
    """Greedily pack sentences up to `size`, carrying `overlap` characters forward."""
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        piece = sentence.strip()
        if not piece:
            continue
        # A single sentence longer than the window: hard-split it, last resort only.
        if len(piece) > size:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(piece), size - overlap):
                chunks.append(piece[start : start + size].strip())
            continue
        if len(current) + len(piece) + 1 <= size:
            current = f"{current} {piece}".strip()
        else:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            # Resume the carry-over at a word boundary so we never split a figure.
            if " " in tail:
                tail = tail[tail.index(" ") + 1 :]
            # Never let the carry-over push a chunk past the window.
            if len(tail) + len(piece) + 1 > size:
                tail = ""
            current = f"{tail} {piece}".strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def extract_pages(pdf_path) -> list[str]:
    """One entry per page, 1-indexed by position (index 0 == page 1)."""
    reader = PdfReader(str(pdf_path))
    return [_normalise(page.extract_text() or "") for page in reader.pages]


def chunk_pdf(
    pdf_path,
    *,
    size: int | None = None,
    overlap: int | None = None,
    language: str = "en",
) -> list[PageChunk]:
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    pages = extract_pages(pdf_path)
    boilerplate = _repeated_lines(pages)

    chunks: list[PageChunk] = []
    index = 0
    for page_number, page_text in enumerate(pages, start=1):  # 1-indexed: matches a PDF viewer
        cleaned = _strip_boilerplate(page_text, boilerplate)
        if _alnum_len(cleaned) < MIN_CHUNK_ALNUM:
            continue
        if len(cleaned) <= size:
            pieces = [cleaned]
        else:
            sentences = _SENTENCE_SPLIT.split(cleaned)
            pieces = _pack(sentences, size, overlap)
        cursor = 0
        for piece in pieces:
            if _alnum_len(piece) < MIN_CHUNK_ALNUM:
                continue
            start = page_text.find(piece[:40], cursor)
            start = start if start >= 0 else cursor
            chunks.append(
                PageChunk(
                    text=piece,
                    page=page_number,
                    chunk_index=index,
                    char_start=start,
                    char_end=start + len(piece),
                    meta={"language": language},
                )
            )
            cursor = start + max(1, len(piece) - overlap)
            index += 1
    return chunks
