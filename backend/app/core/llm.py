"""The ONE module that talks to a language model.

Nothing else in this codebase may import `openai` or `google.genai`. Everything else
imports chat(), chat_stream(), embed() and embed_batch() from here.

Two providers, two very different policies:

  CHAT       OpenAI first, Gemini on failure. Safe to fail over: a scope verdict or a
             grounded answer is just text, and either model can produce it.

  EMBEDDINGS ONE provider, pinned, never failing over. See the note on embed_batch().
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.errors import ProviderError
from app.core.logging import logger

TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"

_RETRYABLE_MARKERS = (
    "429", "500", "502", "503", "504",
    "rate limit", "rate_limit", "resource_exhausted", "unavailable",
    "deadline", "timeout", "overloaded", "connection", "temporarily",
)

# The SDK clients are cached for the life of the process, but their underlying transport
# can die under them - the pipeline runs in asyncio.to_thread workers, and an SDK that
# manages its own event loop internally will tear the transport down with that loop. The
# cache then keeps handing back a corpse. Detect it, rebuild, retry.
_STALE_CLIENT_MARKERS = (
    "client has been closed",
    "cannot send a request",
    "event loop is closed",
    "attached to a different loop",
    "client is closed",
)

# Retrying these is pointless: the key is wrong, revoked, or out of credit. Retrying
# costs ~10s per call, and a single question makes three chat calls.
_FATAL_MARKERS = (
    "401", "403", "invalid_api_key", "incorrect api key", "invalid api key",
    "unauthorized", "permission_denied", "api key not valid",
    "insufficient_quota", "billing", "account is not active",
)

# How long to skip a provider after it fails, so the failover penalty is paid once
# rather than on every call.
CIRCUIT_OPEN_SECONDS = 60.0
_unhealthy_until: dict[str, float] = {}


class _Retryable(ProviderError):
    """A transient provider failure, worth retrying on the same provider."""


class _Fatal(ProviderError):
    """A configuration failure. Fail over immediately; do not retry."""


class _StaleClient(_Retryable):
    """The cached SDK client is dead. Rebuild it and retry on the same provider."""


class _RateLimited(_Retryable):
    """A quota ceiling. Recoverable, but only after a genuine wait."""


_RETRY_DELAY = re.compile(r"retry in (\d+(?:\.\d+)?)s|'retryDelay': '(\d+)s'", re.I)


def retry_after_seconds(text: str) -> float | None:
    """Providers tell us exactly how long to wait. Listen to them."""
    match = _RETRY_DELAY.search(text)
    if not match:
        return None
    return float(match.group(1) or match.group(2))


def _classify(exc: Exception) -> ProviderError:
    text = f"{type(exc).__name__}: {exc}".lower()

    # A dead transport, checked first so it is not mistaken for a connection error and
    # retried against the same corpse three times before failing over.
    if any(marker in text for marker in _STALE_CLIENT_MARKERS):
        return _StaleClient(str(exc))

    # 429 wins over everything. Google's rate-limit message contains the words "plan and
    # billing details", which used to match the fatal list - so a transient limit that
    # says "Please retry in 11s" was treated as a permanently broken key and never
    # retried. Status code beats prose.
    if "429" in text or "resource_exhausted" in text or "rate limit" in text:
        return _RateLimited(str(exc))

    if any(marker in text for marker in _FATAL_MARKERS):
        return _Fatal(str(exc))
    if any(marker in text for marker in _RETRYABLE_MARKERS):
        return _Retryable(str(exc))
    return ProviderError(str(exc))


def _handle(provider: Any, exc: Exception) -> ProviderError:
    """Normalise an SDK exception, dropping the cached client if it has gone stale."""
    error = _classify(exc)
    if isinstance(error, _StaleClient):
        provider.reset_client()
        logger.info("llm_client_rebuilt", extra={"provider": provider.name})
    return error


def _trip_circuit(name: str) -> None:
    _unhealthy_until[name] = time.monotonic() + CIRCUIT_OPEN_SECONDS


def _circuit_open(name: str) -> bool:
    return time.monotonic() < _unhealthy_until.get(name, 0.0)


def reset_circuits() -> None:
    _unhealthy_until.clear()


def _l2_normalise(vector: list[float]) -> list[float]:
    """Cosine distance assumes unit vectors. OpenAI returns them normalised already;
    gemini-embedding-001 only does so at 3072 dims, so normalise both to be safe."""
    norm = math.sqrt(sum(c * c for c in vector))
    return [c / norm for c in vector] if norm else vector


_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(_Retryable),
)

# Embedding a whole corpus is a burst of hundreds of calls straight into a per-minute
# ceiling. Give it more patience and much longer waits than an interactive chat call.
_embed_retry = retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=4, min=5, max=60),
    retry=retry_if_exception_type(_Retryable),
)


class _Pacer:
    """Keeps outbound calls under a requests-per-minute ceiling.

    The Gemini SDK sends one HTTP request per text even when handed a list, so a
    323-chunk corpus is 323 requests - and the free tier allows 100 a minute. Without
    pacing, ingestion reliably dies about 94 chunks in.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait(self, per_minute: int) -> None:
        if per_minute <= 0:
            return
        interval = 60.0 / per_minute
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_slot - now)
            self._next_slot = max(now, self._next_slot) + interval
        if sleep_for:
            time.sleep(sleep_for)


_embed_pacer = _Pacer()


# ── OpenAI ────────────────────────────────────────────────────────────────────
class OpenAIProvider:
    name = "openai"

    @classmethod
    def reset_client(cls) -> None:
        cls._client.cache_clear()

    @staticmethod
    @lru_cache
    def _client() -> Any:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not set.")
        from openai import OpenAI

        kwargs: dict[str, Any] = {
            "api_key": settings.openai_api_key,
            "timeout": settings.request_timeout_seconds,
            "max_retries": 0,  # tenacity owns retries, so they stay observable
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return OpenAI(**kwargs)

    @classmethod
    @_retry
    def chat(cls, prompt: str, *, temperature: float, max_output_tokens: int) -> str:
        try:
            response = cls._client().chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_output_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc
        return (response.choices[0].message.content or "").strip()

    @classmethod
    def chat_stream(cls, prompt: str, *, temperature: float, max_output_tokens: int) -> Iterator[str]:
        try:
            stream = cls._client().chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_output_tokens,
                stream=True,
            )
            for chunk in stream:
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc

    @classmethod
    @_embed_retry
    def embed_batch(cls, texts: list[str], task_type: str) -> list[list[float]]:
        # OpenAI has no task_type; asymmetric query/document embedding is Gemini-only.
        del task_type
        try:
            response = cls._client().embeddings.create(
                model=settings.openai_embed_model,
                input=texts,
                dimensions=settings.embed_dim,
            )
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc
        return [_l2_normalise(list(item.embedding)) for item in response.data]


# ── Gemini ────────────────────────────────────────────────────────────────────
class GeminiProvider:
    name = "gemini"

    @classmethod
    def reset_client(cls) -> None:
        cls._client.cache_clear()

    @staticmethod
    @lru_cache
    def _client() -> Any:
        if not settings.google_api_key:
            raise ProviderError("GOOGLE_API_KEY is not set.")
        from google import genai
        from google.genai import types

        http_options: dict[str, Any] = {"timeout": settings.request_timeout_seconds * 1000}
        if settings.gemini_base_url:
            http_options["base_url"] = settings.gemini_base_url
        return genai.Client(
            api_key=settings.google_api_key,
            http_options=types.HttpOptions(**http_options),
        )

    @staticmethod
    def _config(temperature: float, max_output_tokens: int) -> Any:
        from google.genai import types

        kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "candidate_count": 1,
        }
        # gemini-2.5-* are thinking models: reasoning tokens come out of the SAME
        # budget as the answer. A short budget is spent entirely on hidden thinking and
        # the visible text arrives empty. This agent never needs chain-of-thought - it
        # classifies, quotes, and verifies - so turn it off. It is also much faster.
        if settings.gemini_disable_thinking:
            try:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except (AttributeError, TypeError):  # SDK without thinking support
                pass
        return types.GenerateContentConfig(**kwargs)

    @classmethod
    @_retry
    def chat(cls, prompt: str, *, temperature: float, max_output_tokens: int) -> str:
        try:
            response = cls._client().models.generate_content(
                model=settings.gemini_chat_model,
                contents=prompt,
                config=cls._config(temperature, max_output_tokens),
            )
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc
        return (response.text or "").strip()

    @classmethod
    def chat_stream(cls, prompt: str, *, temperature: float, max_output_tokens: int) -> Iterator[str]:
        try:
            for chunk in cls._client().models.generate_content_stream(
                model=settings.gemini_chat_model,
                contents=prompt,
                config=cls._config(temperature, max_output_tokens),
            ):
                if getattr(chunk, "text", None):
                    yield chunk.text
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc

    @classmethod
    @_embed_retry
    def embed_batch(cls, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        try:
            response = cls._client().models.embed_content(
                model=settings.gemini_embed_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embed_dim,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise _handle(cls, exc) from exc
        return [_l2_normalise(list(item.values)) for item in response.embeddings]


PROVIDERS: dict[str, Any] = {"openai": OpenAIProvider, "gemini": GeminiProvider}


def _provider(name: str) -> Any:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ProviderError(f"Unknown provider '{name}'. Choose one of: {', '.join(PROVIDERS)}.") from None


def chat_provider_names() -> list[str]:
    """Primary first, then the fallback if one is configured and different."""
    names = [settings.chat_provider]
    fallback = settings.chat_fallback_provider
    if fallback and fallback != "none" and fallback != settings.chat_provider:
        names.append(fallback)
    return names


# ── public surface ────────────────────────────────────────────────────────────
def chat(prompt: str, *, temperature: float | None = None, max_output_tokens: int = 1024) -> str:
    """Ask the primary chat provider; fall back to the secondary if it fails.

    Failing over is safe here precisely because of how this system is built: whatever
    comes back still has to pass the citation validator and the grounding guard before
    a user sees it. A weaker fallback model cannot loosen any guarantee - at worst it
    produces an answer that gets blocked.
    """
    temp = settings.llm_temperature if temperature is None else temperature
    names = chat_provider_names()
    resolved = [(name, _provider(name)) for name in names]  # raises on a bad config name
    last: Exception | None = None

    # A provider that just failed is skipped for a minute. Without this, every one of
    # the three chat calls per question pays the full failover penalty again.
    live = [(n, p) for n, p in resolved if not _circuit_open(n)] or resolved

    for index, (name, provider) in enumerate(live):
        started = time.perf_counter()
        try:
            result = provider.chat(prompt, temperature=temp, max_output_tokens=max_output_tokens)
            _unhealthy_until.pop(name, None)
            logger.debug(
                "llm_chat",
                extra={
                    "provider": name,
                    "failed_over": index > 0,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not isinstance(exc, _StaleClient):
                _trip_circuit(name)
            remaining = [n for n, _ in live[index + 1 :]]
            logger.warning(
                "llm_provider_failed",
                extra={
                    "provider": name,
                    "detail": type(exc).__name__,
                    "error": str(exc)[:200],
                    "fatal": isinstance(exc, _Fatal),
                    "falling_back_to": remaining[0] if remaining else None,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            )

    raise ProviderError(f"All chat providers failed ({', '.join(names)}): {last}")


def provider_health() -> dict[str, str]:
    """For /api/ready: which providers are currently being skipped."""
    return {
        name: ("cooling down" if _circuit_open(name) else "ok") for name in chat_provider_names()
    }


def chat_stream(
    prompt: str, *, temperature: float | None = None, max_output_tokens: int = 1024
) -> Iterator[str]:
    """Same failover, but only before the first token - never mid-stream."""
    temp = settings.llm_temperature if temperature is None else temperature
    resolved = [(name, _provider(name)) for name in chat_provider_names()]
    last: Exception | None = None

    for name, provider in resolved:
        try:
            stream = provider.chat_stream(
                prompt, temperature=temp, max_output_tokens=max_output_tokens
            )
            first = next(stream, None)
            if first is None:
                return
            yield first
            yield from stream
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("llm_stream_failed", extra={"provider": name, "detail": type(exc).__name__})

    raise ProviderError(f"All chat providers failed while streaming: {last}")


def embed_batch(
    texts: list[str], *, task_type: str = TASK_DOCUMENT, batch_size: int = 32
) -> list[list[float]]:
    """Embed with the ONE pinned provider. There is deliberately no failover.

    Two embedding models produce two different vector spaces. Even at identical
    dimensions, a Gemini query vector searched against OpenAI document vectors returns
    numerically valid, semantically meaningless neighbours - the retrieval would quietly
    become nonsense while every health check stayed green. Given that this agent's whole
    purpose is to be provably grounded, that is the worst possible failure mode.

    So: if the embedding provider is down, ingestion or search fails loudly and the user
    sees an honest error, rather than confident answers drawn from the wrong clauses.
    """
    provider = _provider(settings.embed_provider)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        window = texts[start : start + batch_size]
        # One HTTP request per text on Gemini, so pace by text rather than by batch.
        for _ in window:
            _embed_pacer.wait(settings.embed_requests_per_minute)
        vectors.extend(provider.embed_batch(window, task_type))
        logger.info("embed_progress", extra={"done": len(vectors), "total": len(texts)})
    return vectors


def embed(text: str, *, task_type: str = TASK_DOCUMENT) -> list[float]:
    return embed_batch([text], task_type=task_type)[0]


def embedding_fingerprint() -> dict[str, str | int]:
    """Identifies the vector space, so a mismatch can be detected instead of guessed at."""
    provider = settings.embed_provider
    model = settings.openai_embed_model if provider == "openai" else settings.gemini_embed_model
    return {"embed_provider": provider, "embed_model": model, "embed_dim": settings.embed_dim}
