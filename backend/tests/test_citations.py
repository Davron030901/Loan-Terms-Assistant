"""Citations are a guard: a page that was never retrieved cannot be cited."""

from app.agent import citations
from app.core import prompts


def test_extracts_a_single_page():
    assert citations.extract_citations("A fee of $25 applies (p. 3).") == [3]


def test_extracts_multiple_pages():
    assert citations.extract_citations("Both apply (p. 3, p. 7).") == [3, 7]
    assert citations.extract_citations("See (pp. 4, 9).") == [4, 9]


def test_valid_citation_passes_and_carries_a_snippet(chunks):
    report = citations.validate("A late fee of $25 applies (p. 3).", chunks)
    assert report.ok is True
    assert report.cited_pages == [3]
    assert report.citations[0].page == 3
    assert "$25" in report.citations[0].quote


def test_hallucinated_page_is_rejected(chunks):
    report = citations.validate("A late fee of $25 applies (p. 12).", chunks)
    assert report.ok is False
    assert report.invalid_pages == [12]
    assert report.needs_repair is False  # fabrication is blocked, not repaired


def test_missing_citation_triggers_one_repair(chunks):
    report = citations.validate("A late fee of $25 applies.", chunks)
    assert report.ok is False
    assert report.needs_repair is True


def test_not_stated_is_exempt(chunks):
    assert citations.validate(prompts.NOT_STATED, chunks).ok is True


def test_page_numbers_are_not_mistaken_for_claims(chunks):
    assert citations.has_factual_claim("Interest accrues daily (p. 7).") is False
    assert citations.has_factual_claim("Interest accrues at 2.5% (p. 7).") is True
