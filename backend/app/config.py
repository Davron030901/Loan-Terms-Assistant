"""Application settings.

Every environment variable in .env.example is declared here, validated, and exposed
through a single cached Settings object. Nothing else in the codebase reads os.environ.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent

_SECRET_KEYS = ("api_key", "secret", "token", "password")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Provider routing ──────────────────────────────────────────────────────
    # Chat may fail over. Embeddings may not - see core/llm.embed_batch().
    chat_provider: str = "openai"
    chat_fallback_provider: str = "gemini"
    embed_provider: str = "gemini"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_base_url: str = ""

    # ── Google Gemini ─────────────────────────────────────────────────────────
    google_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "models/gemini-embedding-001"
    embed_dim: int = 768
    llm_temperature: float = 0.0
    gemini_base_url: str = ""

    # ── Qdrant Cloud ──────────────────────────────────────────────────────────
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "loan_terms"

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retriever_top_k: int = 6
    retriever_score_floor: float = 0.55
    chunk_size: int = 1000
    chunk_overlap: int = 180

    # ── Agent behaviour ───────────────────────────────────────────────────────
    default_doc_id: str = "cibc_personal"
    enable_streaming: bool = True
    max_question_chars: int = 600
    request_timeout_seconds: int = 45

    # ── Server ────────────────────────────────────────────────────────────────
    port: int = 8000
    log_level: str = "INFO"
    environment: str = "development"
    web_concurrency: int = 1
    rate_limit_per_minute: int = 20
    app_version: str = "1.0.0"

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Kept as a raw string: pydantic-settings would otherwise try to JSON-decode a
    # list field and blow up on a plain comma-separated value.
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    # ── Ingestion ─────────────────────────────────────────────────────────────
    auto_ingest: bool = False

    docs_dir: Path = Field(default=BACKEND_ROOT / "docs")

    # ── validators ────────────────────────────────────────────────────────────
    @field_validator("chat_provider", "chat_fallback_provider", "embed_provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("openai", "gemini", "none", ""):
            raise ValueError("provider must be 'openai', 'gemini' or 'none'")
        return v

    @field_validator("embed_dim")
    @classmethod
    def _valid_dim(cls, v: int) -> int:
        if v not in (768, 1536, 3072):
            raise ValueError("EMBED_DIM must be one of 768, 1536, 3072")
        return v

    @field_validator("retriever_score_floor")
    @classmethod
    def _valid_floor(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("RETRIEVER_SCORE_FLOOR must be between 0 and 1")
        return v

    @field_validator("chunk_overlap")
    @classmethod
    def _valid_overlap(cls, v: int, info) -> int:
        size = info.data.get("chunk_size", 1000)
        if v >= size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return v

    @field_validator("cors_origin_regex")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        if v:
            re.compile(v)  # raises if malformed
        return v

    # ── derived ───────────────────────────────────────────────────────────────
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    _KEY_FOR = {"openai": ("OPENAI_API_KEY", "openai_api_key"), "gemini": ("GOOGLE_API_KEY", "google_api_key")}

    def _has_key(self, provider: str) -> bool:
        entry = self._KEY_FOR.get(provider)
        return bool(entry and getattr(self, entry[1]))

    @property
    def chat_chain(self) -> list[str]:
        chain = [self.chat_provider]
        if self.chat_fallback_provider not in ("", "none", self.chat_provider):
            chain.append(self.chat_fallback_provider)
        return chain

    def require_llm(self) -> None:
        """At least one chat provider must be usable, and the embedding provider must be."""
        if not any(self._has_key(p) for p in self.chat_chain):
            names = ", ".join(self._KEY_FOR[p][0] for p in self.chat_chain if p in self._KEY_FOR)
            raise RuntimeError(
                f"No chat provider is configured. Set at least one of: {names} in backend/.env."
            )
        if not self._has_key(self.embed_provider):
            var = self._KEY_FOR[self.embed_provider][0]
            raise RuntimeError(
                f"{var} is missing, and EMBED_PROVIDER={self.embed_provider}. "
                "Embeddings have no fallback: set that key, or change EMBED_PROVIDER "
                "and re-run ingestion with --recreate."
            )

    def require_vector_store(self) -> None:
        missing = [
            name
            for name, value in (("QDRANT_URL", self.qdrant_url), ("QDRANT_API_KEY", self.qdrant_api_key))
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)} missing. Create a free Qdrant Cloud cluster and put the "
                "URL and API key in backend/.env."
            )

    def redacted(self) -> dict[str, object]:
        """Settings safe to write to a log line."""
        out: dict[str, object] = {}
        for name, value in self.model_dump().items():
            if any(k in name for k in _SECRET_KEYS) and value:
                out[name] = f"***set*** (len={len(str(value))})"
            else:
                out[name] = str(value) if isinstance(value, Path) else value
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
