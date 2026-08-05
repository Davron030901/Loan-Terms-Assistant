import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Tests never touch a real provider or a real vector database.
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from app.schemas import Chunk  # noqa: E402


@pytest.fixture
def chunks() -> list[Chunk]:
    return [
        Chunk(
            text="A late payment fee of $25 applies to each missed instalment.",
            page=3,
            score=0.82,
            chunk_index=0,
            doc_id="test_doc",
        ),
        Chunk(
            text="Interest accrues daily at the prime rate plus 2.5% per annum.",
            page=7,
            score=0.71,
            chunk_index=1,
            doc_id="test_doc",
        ),
    ]


@pytest.fixture
def no_llm(monkeypatch):
    """Any LLM call during this test is a bug - fail loudly instead of silently passing."""

    def boom(*_args, **_kwargs):
        raise AssertionError("The LLM was called when it should not have been.")

    monkeypatch.setattr("app.core.llm.chat", boom)
    monkeypatch.setattr("app.agent.guard.chat", boom)
    return boom
