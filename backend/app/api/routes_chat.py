"""The chat endpoints. Both gates run here, server-side, always."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.agent import pipeline
from app.config import settings
from app.core.errors import InvalidQuestionError
from app.core.limiter import CHAT_LIMIT, limiter
from app.core.logging import get_request_id
from app.rag import registry
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


def _validate(payload: ChatRequest) -> tuple[str, str]:
    question = payload.question.strip()
    if not question:
        raise InvalidQuestionError("Please type a question.")
    if len(question) > settings.max_question_chars:
        raise InvalidQuestionError(
            f"Questions are limited to {settings.max_question_chars} characters."
        )
    doc_id = registry.resolve_doc_id(payload.doc_id)  # raises UnknownDocumentError -> 400
    return question, doc_id


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(CHAT_LIMIT)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    question, doc_id = _validate(payload)
    return await pipeline.ask(question, doc_id)


@router.post("/chat/stream")
@limiter.limit(CHAT_LIMIT)
async def chat_stream(request: Request, payload: ChatRequest) -> EventSourceResponse:
    question, doc_id = _validate(payload)

    async def event_source():
        try:
            async for event, data in pipeline.ask_events(question, doc_id):
                if await request.is_disconnected():
                    break
                yield {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}
        except Exception:  # noqa: BLE001 - never leak internals over the wire
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": "Something went wrong.", "request_id": get_request_id()}
                ),
            }
            yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_source())
