"""The four steps, wired. Every verdict must be reachable and correctly traced."""

import pytest

from app.agent import pipeline
from app.core import prompts
from app.schemas import Chunk

CHUNKS = [
    Chunk(text="A late payment fee of $25 applies.", page=3, score=0.8, doc_id="cibc_personal"),
    Chunk(text="Interest accrues at the prime rate.", page=4, score=0.7, doc_id="cibc_personal"),
]


@pytest.fixture
def wired(monkeypatch):
    """Wire the pipeline to controllable stand-ins for the model and the index."""

    state = {
        "scope": True,
        "chunks": CHUNKS,
        "draft": "A late payment fee of $25 applies (p. 3).",
        "grounded": True,
    }

    from app.agent import guard, verify

    monkeypatch.setattr(
        guard, "check", lambda q: guard.ScopeVerdict(state["scope"], "test", "llm", 1)
    )
    monkeypatch.setattr("app.rag.retrieve.search", lambda q, doc_id, k=None: state["chunks"])
    monkeypatch.setattr("app.agent.answer.write", lambda q, c: state["draft"])
    monkeypatch.setattr("app.agent.answer.repair", lambda q, c, d: state["draft"])
    monkeypatch.setattr(
        verify,
        "is_grounded",
        lambda a, c: verify.GroundingVerdict(state["grounded"], "llm", "", 1),
    )
    return state


async def test_in_scope_question_is_answered_with_a_citation(wired):
    response = await pipeline.ask("What is the late fee?", "cibc_personal")
    assert response.verdict == "answered"
    assert "(p. 3)" in response.answer
    assert response.citations[0].page == 3
    assert response.trace.scope_guard.verdict == "ALLOW"
    assert response.trace.grounding_guard.verdict == "GROUNDED"


async def test_off_topic_is_refused_before_retrieval(wired, monkeypatch):
    wired["scope"] = False
    called = {"retrieved": False}

    def spy(*_a, **_k):
        called["retrieved"] = True
        return CHUNKS

    monkeypatch.setattr("app.rag.retrieve.search", spy)
    response = await pipeline.ask("Write me a poem.", "cibc_personal")
    assert response.verdict == "refused_out_of_scope"
    assert response.answer == prompts.REFUSAL_OUT_OF_SCOPE
    assert called["retrieved"] is False, "retrieval must never run for an out-of-scope question"


async def test_empty_retrieval_answers_not_stated_without_calling_the_model(wired, monkeypatch):
    wired["chunks"] = []

    def boom(*_a, **_k):
        raise AssertionError("the answer model must not be called without evidence")

    monkeypatch.setattr("app.agent.answer.write", boom)
    response = await pipeline.ask("What is the rate on a beach house?", "cibc_personal")
    assert response.verdict == "not_stated"
    assert response.answer == prompts.NOT_STATED


async def test_ungrounded_answer_is_blocked(wired):
    wired["grounded"] = False
    response = await pipeline.ask("What is the late fee?", "cibc_personal")
    assert response.verdict == "blocked_not_grounded"
    assert response.answer == prompts.BLOCKED_MESSAGE
    assert response.trace.grounding_guard.verdict == "NOT_GROUNDED"


async def test_hallucinated_citation_is_blocked(wired):
    wired["draft"] = "A late payment fee of $25 applies (p. 99)."
    response = await pipeline.ask("What is the late fee?", "cibc_personal")
    assert response.verdict == "blocked_not_grounded"
    assert response.trace.grounding_guard.method == "citation"


async def test_model_saying_not_stated_is_passed_through(wired):
    wired["draft"] = prompts.NOT_STATED
    response = await pipeline.ask("Does it cover pet insurance?", "cibc_personal")
    assert response.verdict == "not_stated"


async def test_trace_is_always_populated(wired):
    response = await pipeline.ask("What is the late fee?", "cibc_personal")
    assert response.trace.total_latency_ms >= 0
    assert response.trace.retrieval.pages == [3, 4]


# ── an outage must not masquerade as a refusal ────────────────────────────────
async def test_a_gate_that_could_not_run_reports_an_error_not_a_refusal(wired, monkeypatch):
    """A rate-limited guard used to return "I can only answer questions about this loan
    product's terms" - claiming a scope decision it never made. That misreports an outage
    as correct behaviour, and would earn rubric marks for a guard that never fired."""
    from app.agent import guard

    monkeypatch.setattr(
        guard,
        "check",
        lambda q: guard.ScopeVerdict(
            allowed=False,
            reason="The topic gate could not be evaluated.",
            layer="llm",
            latency_ms=1,
            evaluated=False,
        ),
    )
    response = await pipeline.ask("How is interest calculated?", "cibc_personal")
    assert response.verdict == "error"
    assert response.answer == prompts.GATE_UNAVAILABLE
    assert response.answer != prompts.REFUSAL_OUT_OF_SCOPE


async def test_a_real_refusal_is_still_a_refusal(wired, monkeypatch):
    from app.agent import guard

    monkeypatch.setattr(
        guard,
        "check",
        lambda q: guard.ScopeVerdict(False, "Out of scope.", "llm", 1, evaluated=True),
    )
    response = await pipeline.ask("Write me a poem.", "cibc_personal")
    assert response.verdict == "refused_out_of_scope"
    assert response.answer == prompts.REFUSAL_OUT_OF_SCOPE


async def test_the_question_is_still_never_answered_when_a_gate_fails(wired, monkeypatch):
    """Honesty must not cost safety: an unevaluated gate still blocks everything."""
    from app.agent import guard

    called = {"retrieved": False}
    monkeypatch.setattr(
        "app.rag.retrieve.search",
        lambda *a, **k: called.__setitem__("retrieved", True) or [],
    )
    monkeypatch.setattr(
        guard, "check", lambda q: guard.ScopeVerdict(False, "down", "llm", 1, evaluated=False)
    )
    response = await pipeline.ask("What is the rate?", "cibc_personal")
    assert response.verdict == "error"
    assert called["retrieved"] is False, "retrieval must not run when the gate did not"
