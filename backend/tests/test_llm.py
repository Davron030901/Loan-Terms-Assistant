"""Provider routing: chat may fail over, embeddings may not."""

import json

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


# ── regression: a cached SDK client that died under a worker thread ───────────
STALE_MESSAGES = [
    "Cannot send a request, as the client has been closed.",
    "RuntimeError: Event loop is closed",
    "Future attached to a different loop",
]


@pytest.mark.parametrize("message", STALE_MESSAGES)
def test_a_dead_client_is_rebuilt_and_retried(message, monkeypatch):
    """The pipeline runs in asyncio.to_thread workers. An SDK that manages its own event
    loop can tear its transport down between calls, and the lru_cache then hands back a
    corpse forever. Detect it, drop the cache, retry on the same provider."""
    state = {"calls": 0, "resets": 0}

    def flaky(prompt, *, temperature, max_output_tokens):
        state["calls"] += 1
        if state["calls"] == 1:
            raise llm._handle(llm.GeminiProvider, RuntimeError(message))
        return "ALLOW"

    monkeypatch.setattr(
        llm.GeminiProvider, "reset_client", classmethod(lambda cls: state.__setitem__("resets", state["resets"] + 1))
    )
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(flaky))
    monkeypatch.setattr(llm.settings, "chat_provider", "gemini")
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "none")
    llm.reset_circuits()

    # _handle already reset the cache once while classifying; the retry then succeeds.
    with pytest.raises(llm.ProviderError):
        llm.GeminiProvider.chat("q", temperature=0, max_output_tokens=8)
    assert state["resets"] == 1, "a stale client must invalidate the cache"
    assert llm.GeminiProvider.chat("q", temperature=0, max_output_tokens=8) == "ALLOW"


@pytest.mark.parametrize("message", STALE_MESSAGES)
def test_stale_client_errors_are_retryable_not_fatal(message):
    error = llm._classify(RuntimeError(message))
    assert isinstance(error, llm._Retryable), "a dead transport is recoverable, not a config error"
    assert not isinstance(error, llm._Fatal)


def test_auth_errors_are_still_fatal_not_stale():
    error = llm._classify(Exception("Error code: 401 - Incorrect API key provided"))
    assert isinstance(error, llm._Fatal)


def test_both_providers_can_rebuild_their_client():
    for provider in (llm.OpenAIProvider, llm.GeminiProvider):
        assert callable(provider.reset_client)
        provider.reset_client()  # must not raise even when nothing is cached


# ── regression: a rate limit is not a billing failure ─────────────────────────
GOOGLE_429 = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current "
    "quota, please check your plan and billing details. ... Quota exceeded for metric: "
    "generativelanguage.googleapis.com/embed_content_free_tier_requests, limit: 100. "
    "Please retry in 11.503138329s.'}}"
)


def test_a_rate_limit_is_retryable_even_though_it_mentions_billing():
    """Google's 429 text contains "plan and billing details", which used to match the
    fatal list - so a limit that explicitly says "Please retry in 11s" was treated as a
    permanently broken key and never retried. Ingestion died 94 chunks in."""
    error = llm._classify(Exception(GOOGLE_429))
    assert isinstance(error, llm._Retryable), "a 429 must be retried, not given up on"
    assert not isinstance(error, llm._Fatal)


def test_a_genuine_billing_failure_is_still_fatal():
    error = llm._classify(Exception("You have insufficient_quota. Please add a payment method."))
    assert isinstance(error, llm._Fatal)


def test_the_provider_retry_delay_is_read_from_the_message():
    assert llm.retry_after_seconds(GOOGLE_429) == pytest.approx(11.503, rel=1e-3)
    assert llm.retry_after_seconds("'retryDelay': '30s'") == 30.0
    assert llm.retry_after_seconds("no delay here") is None


def test_embeddings_are_paced_under_the_per_minute_ceiling(monkeypatch):
    """The Gemini SDK sends one HTTP request per text, so 323 chunks is 323 requests
    into a 100-per-minute ceiling. Without pacing, ingestion cannot finish."""
    import time as _time

    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")
    monkeypatch.setattr(llm.settings, "embed_requests_per_minute", 60)  # 1 per second
    monkeypatch.setattr(
        llm.GeminiProvider, "embed_batch", staticmethod(lambda texts, task_type: [[0.0] * 4] * len(texts))
    )
    llm._embed_pacer._next_slot = _time.monotonic()

    llm.embed_batch(["a", "b", "c", "d", "e"], batch_size=32)
    assert sum(slept) >= 3.0, f"expected pacing to throttle five calls, slept {slept}"


def test_pacing_can_be_switched_off(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(llm.settings, "embed_requests_per_minute", 0)
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")
    monkeypatch.setattr(
        llm.GeminiProvider, "embed_batch", staticmethod(lambda texts, task_type: [[0.0] * 4] * len(texts))
    )
    llm.embed_batch(["a", "b"], batch_size=32)
    assert not slept


# ── startup warmup ────────────────────────────────────────────────────────────
def test_warmup_touches_every_configured_chat_provider(monkeypatch):
    touched: list[str] = []
    monkeypatch.setattr(
        llm.OpenAIProvider, "chat",
        staticmethod(lambda p, **k: touched.append("openai") or "ok"),
    )
    monkeypatch.setattr(
        llm.GeminiProvider, "chat",
        staticmethod(lambda p, **k: touched.append("gemini") or "ok"),
    )
    monkeypatch.setattr(llm.settings, "chat_provider", "openai")
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "gemini")
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")
    llm.reset_circuits()

    report = llm.warm_up()
    assert touched == ["openai", "gemini"]
    assert all("warm in" in v for v in report.values())


def test_warmup_never_raises_and_reports_a_dead_provider(monkeypatch):
    """Boot must not fail because a key is wrong - the app still serves /api/health."""
    monkeypatch.setattr(
        llm.OpenAIProvider, "chat",
        staticmethod(lambda p, **k: (_ for _ in ()).throw(llm._Fatal("401 invalid key"))),
    )
    monkeypatch.setattr(llm.GeminiProvider, "chat", staticmethod(lambda p, **k: "ok"))
    monkeypatch.setattr(llm.settings, "chat_provider", "openai")
    monkeypatch.setattr(llm.settings, "chat_fallback_provider", "gemini")
    monkeypatch.setattr(llm.settings, "embed_provider", "gemini")
    llm.reset_circuits()

    report = llm.warm_up()
    assert "unavailable" in report["openai"]
    assert "warm in" in report["gemini"]
    # A provider that is dead at boot is skipped on the first real request too.
    assert llm.provider_health()["openai"] == "cooling down"


# ── rotating key pool ─────────────────────────────────────────────────────────
def _pool(monkeypatch, provider, keys):
    pool = llm.KeyPool(provider.name, keys)
    monkeypatch.setattr(provider, "pool", pool)
    return pool


def test_a_spent_key_hands_over_to_the_next_one(monkeypatch):
    """Ten free keys is ten times the allowance - if the pool actually rotates."""
    pool = _pool(monkeypatch, llm.GeminiProvider, [f"key-{i}" for i in range(1, 6)])
    used: list[str] = []

    def call(api_key: str) -> str:
        used.append(api_key)
        if api_key in ("key-1", "key-2"):
            raise llm._QuotaExhausted("429 quota exceeded")
        return "ALLOW"

    assert llm.GeminiProvider._with_key(call) == "ALLOW"
    assert used == ["key-1", "key-2", "key-3"], "must walk the pool in order"
    assert pool.available() == [2, 3, 4], "spent keys are rested, the rest stay available"


def test_the_next_call_starts_from_a_healthy_key(monkeypatch):
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b", "c"])
    pool.rest(0, "quota_exhausted")
    used: list[str] = []
    llm.GeminiProvider._with_key(lambda k: used.append(k) or "ok")
    assert "a" not in used, "a resting key must not be tried again while it rests"


def test_all_keys_down_raises_rather_than_pretending(monkeypatch):
    _pool(monkeypatch, llm.GeminiProvider, ["a", "b"])

    def dead(api_key: str):
        raise llm._QuotaExhausted("429 quota exceeded")

    with pytest.raises(ProviderError):
        llm.GeminiProvider._with_key(dead)


def test_cooldown_length_matches_the_failure(monkeypatch):
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b", "c", "d"])
    for index, reason in enumerate(["rate_limited", "quota_exhausted", "fatal"]):
        pool.rest(index, reason)
    resting = {r["key"]: r for r in pool.status()["resting"]}
    assert resting["#1"]["retry_in_seconds"] <= 60, "a per-minute limit rests for a minute"
    assert resting["#2"]["retry_in_seconds"] > 600, "a daily allowance rests for much longer"
    assert resting["#3"]["retry_in_seconds"] > 600, "a dead key is not worth re-trying soon"


def test_a_key_that_recovers_is_revived(monkeypatch):
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b"])
    pool.rest(0, "rate_limited")
    llm.GeminiProvider._with_key(lambda k: "ok")   # succeeds on "b"
    assert 1 in pool.available()


def test_every_key_resting_still_makes_one_last_attempt(monkeypatch):
    """Refusing to try at all would turn a stale cooldown into an outage."""
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b"])
    pool.rest(0, "fatal")
    pool.rest(1, "fatal")
    assert pool.available() == []
    assert llm.GeminiProvider._with_key(lambda k: "ok") == "ok"


def test_status_never_leaks_key_material(monkeypatch):
    secret = "AIzaSyVERYSECRETKEYMATERIAL123"
    pool = _pool(monkeypatch, llm.GeminiProvider, [secret, "other"])
    pool.rest(0, "quota_exhausted")
    serialised = json.dumps(pool.status())
    assert secret not in serialised
    assert secret[:-4] not in serialised
    assert pool.fingerprint(secret) == f"…{secret[-4:]}"
    assert len(pool.fingerprint(secret)) == 5, "four characters is enough to tell keys apart"


def test_key_lists_are_parsed_and_deduplicated():
    from app.config import Settings

    parsed = Settings._split_keys("a, b ,\nc", "b, d")
    assert parsed == ["a", "b", "c", "d"], "order preserved, duplicates dropped"
    assert Settings._split_keys('"quoted"', "") == ["quoted"]
    assert Settings._split_keys("", "") == []


def test_a_single_key_still_works(monkeypatch):
    """The plural variable is optional; nobody's existing setup should break."""
    from app.config import Settings

    s = Settings(google_api_key="solo", google_api_keys="")
    assert s.google_key_list == ["solo"]


def test_embeddings_rotate_keys_because_the_model_is_unchanged(monkeypatch):
    """Rotating KEYS keeps the same vector space. Rotating PROVIDERS would not - that
    remains forbidden, and is covered by test_embeddings_never_fall_over."""
    pool = _pool(monkeypatch, llm.GeminiProvider, ["k1", "k2"])
    seen: list[str] = []

    def once(api_key: str):
        seen.append(api_key)
        if api_key == "k1":
            raise llm._QuotaExhausted("429")
        return [[0.0] * 768]

    assert llm.GeminiProvider._with_key(once) == [[0.0] * 768]
    assert seen == ["k1", "k2"]
    assert pool.available() == [1]


# ── round-robin rotation ──────────────────────────────────────────────────────
def test_keys_are_used_in_a_cycle_and_wrap_around(monkeypatch):
    """Ten keys, ten calls, ten different keys - then back to the first.

    Sticky selection would send every call to key #1 until it hit its per-minute
    ceiling, eat a 429, and repeat with key #2. Spreading the calls means the ceiling is
    never reached at all.
    """
    pool = _pool(monkeypatch, llm.GeminiProvider, [f"k{i}" for i in range(1, 11)])
    used = [llm.GeminiProvider._with_key(lambda key: key) for _ in range(10)]
    assert used == [f"k{i}" for i in range(1, 11)], f"expected one full cycle, got {used}"

    wrapped = [llm.GeminiProvider._with_key(lambda key: key) for _ in range(3)]
    assert wrapped == ["k1", "k2", "k3"], "after the last key it must start again at the first"
    assert pool.available() == list(range(10)), "a healthy cycle rests nobody"


def test_the_cycle_skips_resting_keys_and_still_wraps(monkeypatch):
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b", "c", "d"])
    pool.rest(1, "quota_exhausted")   # "b" is spent
    used = [llm.GeminiProvider._with_key(lambda key: key) for _ in range(6)]
    assert "b" not in used
    assert used == ["a", "c", "d", "a", "c", "d"], f"expected a 3-key cycle, got {used}"


def test_load_is_spread_evenly_across_the_pool(monkeypatch):
    """The point of the cycle: no single key carries a disproportionate share."""
    from collections import Counter

    _pool(monkeypatch, llm.GeminiProvider, [f"k{i}" for i in range(1, 11)])
    counts = Counter(llm.GeminiProvider._with_key(lambda key: key) for _ in range(100))
    assert len(counts) == 10
    assert set(counts.values()) == {10}, f"uneven distribution: {counts}"


def test_rotation_survives_a_key_dying_mid_cycle(monkeypatch):
    pool = _pool(monkeypatch, llm.GeminiProvider, ["a", "b", "c"])
    dead = {"b"}

    def call(api_key: str) -> str:
        if api_key in dead:
            raise llm._QuotaExhausted("429")
        return api_key

    used = [llm.GeminiProvider._with_key(call) for _ in range(5)]
    assert "b" not in [u for u in used]
    assert pool.available() == [0, 2]
    assert used == ["a", "c", "a", "c", "a"], f"cycle should close over the survivors, got {used}"


# ── the cycle adapts to any pool size ─────────────────────────────────────────
@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 10, 13, 25, 50])
def test_the_cycle_fits_whatever_number_of_keys_you_configure(size, monkeypatch):
    """Nothing assumes ten. One key, thirteen, fifty - each cycles and wraps."""
    _pool(monkeypatch, llm.GeminiProvider, [f"k{i}" for i in range(size)])
    used = [llm.GeminiProvider._with_key(lambda key: key) for _ in range(size * 2)]
    expected = [f"k{i}" for i in range(size)] * 2
    assert used == expected, f"pool of {size} did not cycle cleanly"


@pytest.mark.parametrize("size", [1, 4, 9, 17])
def test_load_stays_even_at_any_pool_size(size, monkeypatch):
    from collections import Counter

    _pool(monkeypatch, llm.GeminiProvider, [f"k{i}" for i in range(size)])
    counts = Counter(llm.GeminiProvider._with_key(lambda key: key) for _ in range(size * 20))
    assert len(counts) == size
    assert set(counts.values()) == {20}, f"uneven across {size} keys: {counts}"


def test_the_cursor_is_not_tied_to_how_many_keys_are_healthy(monkeypatch):
    """Shrinking the healthy set must not trap the cursor in a narrow range.

    Wrapping the counter modulo the *healthy* count meant that after most keys went
    quiet the cursor lived in 0-2, and stayed lopsided even after they recovered.
    """
    from collections import Counter

    pool = _pool(monkeypatch, llm.GeminiProvider, [f"k{i}" for i in range(10)])

    for index in range(3, 10):          # only k0, k1, k2 remain healthy
        pool.rest(index, "quota_exhausted")
    for _ in range(9):
        llm.GeminiProvider._with_key(lambda key: key)

    for index in range(3, 10):          # everyone recovers
        pool.revive(index)

    counts = Counter(llm.GeminiProvider._with_key(lambda key: key) for _ in range(100))
    assert len(counts) == 10, f"only {len(counts)} keys used after recovery: {counts}"
    assert max(counts.values()) - min(counts.values()) <= 1, f"lopsided: {counts}"


def test_a_pool_of_one_key_still_works(monkeypatch):
    """The common case: somebody sets a single GOOGLE_API_KEY and nothing else."""
    _pool(monkeypatch, llm.GeminiProvider, ["solo"])
    assert [llm.GeminiProvider._with_key(lambda k: k) for _ in range(5)] == ["solo"] * 5


def test_an_empty_pool_fails_with_a_clear_message(monkeypatch):
    _pool(monkeypatch, llm.GeminiProvider, [])
    with pytest.raises(ProviderError, match="No API key configured"):
        llm.GeminiProvider._with_key(lambda k: k)
