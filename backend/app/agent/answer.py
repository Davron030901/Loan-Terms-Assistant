"""Write an answer from the retrieved clauses - and from nothing else."""

from __future__ import annotations

from collections.abc import Iterator

from app.core import prompts
from app.core.llm import chat, chat_stream
from app.rag.retrieve import build_context
from app.schemas import Chunk


def build_prompt(question: str, chunks: list[Chunk]) -> str:
    return prompts.ANSWER_PROMPT.format(context=build_context(chunks), question=question)


def write(question: str, chunks: list[Chunk]) -> str:
    return chat(build_prompt(question, chunks), temperature=0, max_output_tokens=700)


def write_stream(question: str, chunks: list[Chunk]) -> Iterator[str]:
    yield from chat_stream(build_prompt(question, chunks), temperature=0, max_output_tokens=700)


def repair(question: str, chunks: list[Chunk], draft: str) -> str:
    """One - and only one - retry when the model forgot its citation."""
    prompt = build_prompt(question, chunks) + prompts.CITATION_REPAIR_SUFFIX.format(draft=draft)
    return chat(prompt, temperature=0, max_output_tokens=700)
