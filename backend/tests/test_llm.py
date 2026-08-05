"""Provider routing: chat may fail over, embeddings may not."""

import pytest

from app.core import llm
from app.core.errors import ProviderError


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(llm.settings, "chat_provider", "openai")
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "gemini")
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")


def _stub(monkeypatch, *, openai_chat=None, gemini_chat=None):
    calls: list[str] = []

    def make(name, behaviour):
        def fn(prompt, *, temperature, max_output_tokens):
            calls.append(name)
            if isinstance(behaviour, Exception):
                raise behaviour
            return behaviour
        return fn

    monkeypatch.setattr(llm.OpenAIProvider, "chat", make("openai", openai_chat))
    monkeypatch.setattr(llm.GeminiProvider, "chat", make("gemini", gemini_chat))
    return calls


def test_primary_provider_is_used_when_healthy(monkeypatch):
    calls = _stub(monkeypatch, openai_chat="ALLOW", gemini_chat="REFUSE")
    assert llm.chat("q") == "ALLOW"
    assert calls == ["openai"], "the fallback must not be touched when the primary works"


def test_falls_over_to_gemini_when_openai_fails(monkeypatch):
    calls = _stub(monkeypatch, openai_chat=ProviderError("openai down"), gemini_chat="ALLOW")
    assert llm.chat("q") == "ALLOW"
    assert calls == ["openai", "gemini"]


def test_raises_only_when_every_provider_fails(monkeypatch):
    _stub(monkeypatch, openai_chat=ProviderError("down"), gemini_chat=ProviderError("also down"))
    with pytest.raises(ProviderError, match="All chat providers failed"):
        llm.chat("q")


def test_failover_can_be_disabled(monkeypatch):
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "none")
    calls = _stub(monkeypatch, openai_chat=ProviderError("down"), gemini_chat="ALLOW")
    with pytest.raises(ProviderError):
        llm.chat("q")
    assert calls == ["openai"], "no fallback should be attempted"


def test_provider_order_follows_configuration(monkeypatch):
    monkeypatch.setattr(llm.settings, "chat_provider", "gemini")
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "openai")
    assert llm.chat_provider_names() == ["gemini", "openai"]


def test_a_provider_is_never_listed_twice(monkeypatch):
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "openai")
    assert llm.chat_provider_names() == ["openai"]


# ── embeddings: the deliberate absence of failover ────────────────────────────
def test_embeddings_never_fall_over(monkeypatch):
    """Mixing vector spaces would corrupt retrieval silently. Fail loudly instead."""
    tried: list[str] = []

    def openai_embed(texts, task_type):
        tried.append("openai")
        return [[0.0] * 768 for _ in texts]

    def gemini_embed(texts, task_type):
        tried.append("gemini")
        raise ProviderError("gemini embeddings down")

    monkeypatch.setattr(llm.OpenAIProvider, "embed_batch", staticmethod(openai_embed))
    monkeypatch.setattr(llm.GeminiProvider, "embed_batch", staticmethod(gemini_embed))

    with pytest.raises(ProviderError, match="gemini embeddings down"):
        llm.embed_batch(["text"])
    assert tried == ["gemini"], "embeddings must not silently switch vector space"


def test_embeddings_use_the_pinned_provider(monkeypatch):
    monkeypatch.setattr(llm.settings, "embed_provider", "openai")
    monkeypatch.setattr(
        llm.OpenAIProvider, "embed_batch", staticmethod(lambda texts, task_type: [[1.0] * 4])
    )
    assert llm.embed("x") == [1.0] * 4


def test_fingerprint_identifies_the_vector_space(monkeypatch):
    monkeypatch.setattr(llm.settings, "embed_provider", "openai")
    assert llm.embedding_fingerprint()["embed_model"] == llm.settings.openai_embed_model
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")
    assert llm.embedding_fingerprint()["embed_model"] == llm.settings.gemini_embed_model


def test_vectors_are_unit_length():
    assert llm._l2_normalise([3.0, 4.0]) == [0.6, 0.8]
    assert llm._l2_normalise([0.0, 0.0]) == [0.0, 0.0]


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(llm.settings, "chat_provider", "anthropic")
    with pytest.raises(ProviderError, match="Unknown provider"):
        llm.chat("q")


# ── retrieval refuses to search a foreign vector space ────────────────────────
def test_search_refuses_a_mismatched_index(monkeypatch):
    from app.core.errors import RetrievalError
    from app.rag import retrieve

    monkeypatch.setattr(retrieve, "embed", lambda q, task_type=None: [0.0] * 768)
    monkeypatch.setattr(
        retrieve.store,
        "search",
        lambda vector, doc_id, limit: [
            {"score": 0.9, "payload": {"text": "t", "page": 1, "embed_model": "some-other-model"}}
        ],
    )
    with pytest.raises(RetrievalError, match="--recreate"):
        retrieve.search("q", doc_id="cibc_personal")


# ── regressions from the first live deployment ────────────────────────────────
def test_auth_failures_are_fatal_and_not_retried(monkeypatch):
    """A revoked key is not a transient outage. Retrying it cost ~10s per call, and a
    single question makes three chat calls."""
    attempts = {"n": 0}

    def dead_key(prompt, *, temperature, max_output_tokens):
        attempts["n"] += 1
        raise llm._classify(Exception("Error code: 401 - Incorrect API key provided"))

    monkeypatch.setattr(llm.OpenAIProvider, "chat", staticmethod(dead_key))
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(lambda *a, **k: "ALLOW"))
    llm.reset_circuits()

    assert llm.chat("q") == "ALLOW"
    assert attempts["n"] == 1, "an auth error must fail over immediately, not retry"


def test_a_failed_provider_is_skipped_on_the_next_call(monkeypatch):
    """Without a circuit breaker every call re-pays the failover penalty."""
    tried: list[str] = []

    def broken(prompt, *, temperature, max_output_tokens):
        tried.append("openai")
        raise ProviderError("openai down")

    monkeypatch.setattr(llm.OpenAIProvider, "chat", staticmethod(broken))
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(lambda *a, **k: "ALLOW"))
    llm.reset_circuits()

    llm.chat("first")   # pays the penalty once
    llm.chat("second")  # must not touch OpenAI again
    llm.chat("third")
    assert tried == ["openai"], f"OpenAI retried while cooling down: {tried}"
    assert llm.provider_health()["openai"] == "cooling down"


def test_a_recovered_provider_clears_its_circuit(monkeypatch):
    llm.reset_circuits()
    monkeypatch.setattr(llm.OpenAIProvider, "chat", staticmethod(lambda *a, **k: "ALLOW"))
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(lambda *a, **k: "REFUSE"))
    assert llm.chat("q") == "ALLOW"
    assert llm.provider_health()["openai"] == "ok"


def test_every_provider_down_still_raises(monkeypatch):
    llm.reset_circuits()
    monkeypatch.setattr(llm.OpenAIProvider, "chat", staticmethod(lambda *a, **k: (_ for _ in ()).throw(ProviderError("a"))))
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(lambda *a, **k: (_ for _ in ()).throw(ProviderError("b"))))
    with pytest.raises(ProviderError):
        llm.chat("q")
    # Both circuits open, but the call must still be attempted rather than skipped entirely.
    with pytest.raises(ProviderError):
        llm.chat("q")
