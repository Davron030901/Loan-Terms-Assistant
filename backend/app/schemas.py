"""Pydantic models shared by the RAG layer, the agent and the HTTP API.

The frontend's lib/types.ts mirrors this file exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Verdict = Literal[
    "answered",
    "refused_out_of_scope",
    "blocked_not_grounded",
    "not_stated",
    "error",
]


# ── retrieval ─────────────────────────────────────────────────────────────────
class Chunk(BaseModel):
    text: str
    page: int
    score: float = 0.0
    chunk_index: int = 0
    doc_id: str = ""
    language: str = "en"


class Citation(BaseModel):
    page: int
    quote: str
    score: float = 0.0


# ── trace ─────────────────────────────────────────────────────────────────────
class ScopeTrace(BaseModel):
    verdict: Literal["ALLOW", "REFUSE"]
    reason: str = ""
    layer: Literal["pattern", "llm", "none"] = "none"
    latency_ms: int = 0


class RetrievalTrace(BaseModel):
    chunks: int = 0
    top_score: float = 0.0
    pages: list[int] = Field(default_factory=list)
    latency_ms: int = 0


class AnswerTrace(BaseModel):
    model: str = ""
    repaired: bool = False
    latency_ms: int = 0


class GroundingTrace(BaseModel):
    verdict: Literal["GROUNDED", "NOT_GROUNDED", "SKIPPED"] = "SKIPPED"
    method: Literal["numeric", "llm", "citation", "none"] = "none"
    latency_ms: int = 0


class Trace(BaseModel):
    scope_guard: ScopeTrace | None = None
    retrieval: RetrievalTrace | None = None
    answer: AnswerTrace | None = None
    grounding_guard: GroundingTrace | None = None
    total_latency_ms: int = 0


# ── API ───────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    doc_id: str | None = None

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ChatResponse(BaseModel):
    request_id: str
    verdict: Verdict
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    doc_id: str
    trace: Trace


class DocumentInfo(BaseModel):
    doc_id: str
    bank: str
    title: str
    jurisdiction: str
    language: str
    pages: int
    chunks: int = 0
    source_url: str = ""
    is_default: bool = False


class DocumentsResponse(BaseModel):
    default_doc_id: str
    documents: list[DocumentInfo]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str


class ReadyResponse(BaseModel):
    ready: bool
    collection: str
    points: int
    documents: int
    chat_providers: list[str] = Field(default_factory=list)
    provider_health: dict[str, str] = Field(default_factory=dict)
    key_pools: dict[str, dict] = Field(default_factory=dict)
    embed_provider: str = ""
    embed_model: str = ""
