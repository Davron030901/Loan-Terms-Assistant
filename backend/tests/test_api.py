"""HTTP surface: contract strings, validation, headers, and the four verdicts."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import prompts
from app.main import create_app
from app.schemas import ChatResponse, Trace


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_security_headers_are_present(client):
    r = await client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in r.headers


async def test_documents_lists_the_closed_corpus(client):
    r = await client.get("/api/documents")
    body = r.json()
    assert r.status_code == 200
    assert body["default_doc_id"] == "cibc_personal"
    assert {d["doc_id"] for d in body["documents"]} == {
        "cibc_personal",
        "cimb_personal",
        "sib_personal",
        "sc_vietnam",
        "nbu_uz_green",
    }


async def test_unknown_document_is_rejected(client):
    r = await client.post("/api/chat", json={"question": "What is the fee?", "doc_id": "nope"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unknown_document"


async def test_oversized_question_is_rejected(client):
    r = await client.post("/api/chat", json={"question": "x" * 700, "doc_id": "cibc_personal"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_question"


@pytest.mark.parametrize(
    ("verdict", "answer"),
    [
        ("answered", "A fee of $25 applies (p. 3)."),
        ("refused_out_of_scope", prompts.REFUSAL_OUT_OF_SCOPE),
        ("blocked_not_grounded", prompts.BLOCKED_MESSAGE),
        ("not_stated", prompts.NOT_STATED),
    ],
)
async def test_every_verdict_is_reachable(client, monkeypatch, verdict, answer):
    async def fake_ask(question, doc_id):
        return ChatResponse(
            request_id="req_test",
            verdict=verdict,
            answer=answer,
            doc_id=doc_id,
            trace=Trace(),
        )

    monkeypatch.setattr("app.agent.pipeline.ask", fake_ask)
    r = await client.post("/api/chat", json={"question": "Any question?", "doc_id": "cibc_personal"})
    assert r.status_code == 200
    assert r.json()["verdict"] == verdict
    assert r.json()["answer"] == answer


async def test_fixed_strings_match_the_api_contract():
    assert prompts.REFUSAL_OUT_OF_SCOPE == (
        "I can only answer questions about this loan product's terms and conditions."
    )
    assert prompts.BLOCKED_MESSAGE == "I can't confirm this from the document."
    assert prompts.NOT_STATED == "Not stated in the terms."
