"""SECURITY GATE 2. Prove the guard actually blocks."""

import pytest

from app.agent import verify
from app.core import prompts
from app.schemas import Chunk


@pytest.fixture
def ctx() -> list[Chunk]:
    return [
        Chunk(
            text="A late payment fee of $25 applies to each missed instalment.",
            page=3,
            score=0.9,
            doc_id="d",
        )
    ]


def _grounded(monkeypatch, answer, ctx, llm="GROUNDED"):
    monkeypatch.setattr("app.agent.verify.chat", lambda *a, **k: llm)
    return verify.is_grounded(answer, ctx)


def test_correct_figure_is_grounded(monkeypatch, ctx):
    assert _grounded(monkeypatch, "A late fee of $25 applies (p. 3).", ctx).grounded is True


def test_wrong_number_is_caught_by_the_numeric_audit_with_no_llm_call(ctx):
    # No monkeypatch: if the LLM were reached, the missing client would raise.
    verdict = verify.is_grounded("A late fee of $50 applies (p. 3).", ctx)
    assert verdict.grounded is False
    assert verdict.method == "numeric"


def test_fabricated_page_is_not_grounded(monkeypatch, ctx):
    assert _grounded(monkeypatch, "A late fee of $25 applies (p. 9).", ctx, "NOT_GROUNDED").grounded is False


def test_advice_is_not_grounded(monkeypatch, ctx):
    verdict = _grounded(
        monkeypatch, "You should pay on time to protect your credit (p. 3).", ctx, "NOT_GROUNDED"
    )
    assert verdict.grounded is False


def test_not_stated_is_always_grounded(ctx):
    assert verify.is_grounded(prompts.NOT_STATED, ctx).grounded is True


def test_verifier_failure_fails_closed(monkeypatch, ctx):
    def explode(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.agent.verify.chat", explode)
    assert verify.is_grounded("A late fee of $25 applies (p. 3).", ctx).grounded is False


def test_thousands_separators_do_not_cause_false_blocks(monkeypatch):
    ctx = [Chunk(text="The maximum loan amount is $25,000.", page=2, score=0.9, doc_id="d")]
    assert _grounded(monkeypatch, "The maximum is $25000 (p. 2).", ctx).grounded is True


def test_dotted_table_of_contents_is_not_read_as_a_figure(monkeypatch):
    ctx = [Chunk(text="7. How we Calculate Interest ......... 4", page=1, score=0.9, doc_id="d")]
    assert _grounded(monkeypatch, "Interest is explained in section 7 (p. 1).", ctx).grounded is True
