"""The ONE module that talks to Gemini.

Nothing else in this codebase may import `google.genai`. Everything else imports
chat(), chat_stream(), embed() and embed_batch() from here. That keeps the provider
swappable and the security surface auditable.
"""

from __future__ import annotations

import math
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
    "rate limit", "resource_exhausted", "unavailable", "deadline", "timeout", "overloaded",
)


class _Retryable(ProviderError):
    """Raised for transient provider failures so tenacity can retry them."""


def _classify(exc: Exception) -> ProviderError:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in _RETRYABLE_MARKERS):
        return _Retryable(str(exc))
    return ProviderError(str(exc))


@lru_cache
def _client() -> Any:
    """Built lazily so the module imports cleanly in tests and without credentials."""
    settings.require_llm()
    from google import genai
    from google.genai import types

    http_options: dict[str, Any] = {"timeout": settings.request_timeout_seconds * 1000}
    if settings.gemini_base_url:
        http_options["base_url"] = settings.gemini_base_url
    return genai.Client(
        api_key=settings.google_api_key,
        http_options=types.HttpOptions(**http_options),
    )


def _generation_config(temperature: float | None, max_output_tokens: int) -> Any:
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_output_tokens=max_output_tokens,
        candidate_count=1,
    )


_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(_Retryable),
)


# ── chat ──────────────────────────────────────────────────────────────────────
@_retry
def chat(prompt: str, *, temperature: float | None = None, max_output_tokens: int = 1024) -> str:
    started = time.perf_counter()
    try:
        response = _client().models.generate_content(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=_generation_config(temperature, max_output_tokens),
        )
    except Exception as exc:  # noqa: BLE001 - normalised into ProviderError below
        raise _classify(exc) from exc
    logger.debug("llm_chat", extra={"latency_ms": int((time.perf_counter() - started) * 1000)})
    return (response.text or "").strip()


def chat_stream(
    prompt: str, *, temperature: float | None = None, max_output_tokens: int = 1024
) -> Iterator[str]:
    try:
        stream = _client().models.generate_content_stream(
            model=settings.gemini_chat_model,
            contents=prompt,
            config=_generation_config(temperature, max_output_tokens),
        )
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc) from exc


# ── embeddings ────────────────────────────────────────────────────────────────
def _l2_normalise(vector: list[float]) -> list[float]:
    """gemini-embedding-001 only returns pre-normalised vectors at 3072 dims.

    At 768 we must normalise ourselves, otherwise cosine similarity is wrong.
    """
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        return vector
    return [component / norm for component in vector]


@_retry
def _embed_raw(texts: list[str], task_type: str) -> list[list[float]]:
    from google.genai import types

    try:
        response = _client().models.embed_content(
            model=settings.gemini_embed_model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=settings.embed_dim,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc) from exc
    return [_l2_normalise(list(item.values)) for item in response.embeddings]


def embed(text: str, *, task_type: str = TASK_DOCUMENT) -> list[float]:
    return _embed_raw([text], task_type)[0]


def embed_batch(
    texts: list[str], *, task_type: str = TASK_DOCUMENT, batch_size: int = 32
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        window = texts[start : start + batch_size]
        vectors.extend(_embed_raw(window, task_type))
        if start and start % (batch_size * 5) == 0:
            logger.info("embed_progress", extra={"done": len(vectors), "total": len(texts)})
    return vectors
