"""The chunker is what makes (p. N) truthful. Test it against the real PDFs."""

import re
from functools import lru_cache

import pytest

from app.config import settings
from app.rag import registry
from app.rag.chunking import chunk_pdf, extract_pages

DOC_IDS = registry.document_ids()


# Parsing five PDFs once per test would dominate the suite runtime; do it once per session.
@lru_cache(maxsize=None)
def parsed(doc_id: str):
    path = registry.pdf_path(doc_id)
    return chunk_pdf(path), extract_pages(path)


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_every_chunk_text_really_exists_on_the_page_it_claims(doc_id):
    """If this fails, every citation the agent produces is a lie."""
    chunks, pages = parsed(doc_id)
    for chunk in chunks:
        haystack = re.sub(r"\s+", "", pages[chunk.page - 1]).lower()
        needle = re.sub(r"\s+", "", chunk.text[:120]).lower()
        assert needle in haystack, f"{doc_id}: chunk claims p.{chunk.page} but is not on it"


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_pages_are_one_indexed_and_in_range(doc_id):
    chunks, page_texts = parsed(doc_id)
    total = len(page_texts)
    pages = {c.page for c in chunks}
    assert min(pages) >= 1, "pages must be 1-indexed, as a human sees them in a PDF viewer"
    assert max(pages) <= total


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_chunks_respect_the_window(doc_id):
    for chunk in parsed(doc_id)[0]:
        assert len(chunk.text) <= settings.chunk_size


@pytest.mark.parametrize("doc_id", DOC_IDS)
def test_chunk_indices_are_unique(doc_id):
    indices = [c.chunk_index for c in parsed(doc_id)[0]]
    assert len(indices) == len(set(indices))


def test_hyphen_broken_words_are_rejoined():
    from app.rag.chunking import _normalise

    assert "interest" in _normalise("The inter-\nest rate is variable.")


def test_every_registered_pdf_is_present_and_has_text():
    for doc_id in DOC_IDS:
        assert parsed(doc_id)[0], f"{doc_id} produced no chunks - is it a scan rather than text?"
