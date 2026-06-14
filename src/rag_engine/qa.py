"""Single-turn retrieval-augmented question answering (Step 4).

The pure generation helpers (``generate_answer`` / ``stream_answer``) take an
already-resolved chat model and chunks, so a UI can stream tokens and tests can
run offline with the echo model. ``answer_question`` orchestrates the full flow
(retrieve -> resolve model -> generate) and returns a structured ``RagAnswer``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage
from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel, resolve_chat_model
from rag_engine.models import RagAnswer, RetrievedChunk
from rag_engine.prompts import QA_SYSTEM_PROMPT, format_context
from rag_engine.retrieval import RetrievalResult, retrieve

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = ["answer_question", "generate_answer", "stream_answer"]


def _qa_chain(chat_model: BaseChatModel, chunks: Sequence[RetrievedChunk]) -> tuple[Any, dict]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", QA_SYSTEM_PROMPT), ("human", "{question}")]
    )
    return prompt | chat_model | StrOutputParser(), {"context": format_context(chunks)}


def generate_answer(
    chat_model: BaseChatModel, question: str, chunks: Sequence[RetrievedChunk]
) -> str:
    """Generate a single answer string from *question* and *chunks*."""
    chain, base = _qa_chain(chat_model, chunks)
    return chain.invoke({**base, "question": question})


def stream_answer(
    chat_model: BaseChatModel, question: str, chunks: Sequence[RetrievedChunk]
) -> Iterator[str]:
    """Yield answer tokens for *question* and *chunks* as they are generated."""
    chain, base = _qa_chain(chat_model, chunks)
    yield from chain.stream({**base, "question": question})


def answer_question(
    run_dir: Path | str,
    question: str,
    config: RagConfig,
    *,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
) -> RagAnswer:
    """Answer a single *question* over the index in *run_dir*."""
    question = question.strip()
    if not question:
        return RagAnswer(answer="", errors=[messages.empty_question()])

    retrieval = retriever(run_dir, question, config)
    if retrieval.errors:
        return RagAnswer(
            answer="",
            sources=retrieval.chunks,
            warnings=retrieval.warnings,
            errors=retrieval.errors,
        )

    resolved, chat_warnings = chat_resolver(
        config.llm_model, temperature=config.temperature, max_tokens=config.max_tokens
    )
    answer = RagAnswer(
        answer="",
        sources=retrieval.chunks,
        model_used=resolved.model_id,
        warnings=[*retrieval.warnings, *chat_warnings],
    )
    try:
        answer.answer = generate_answer(resolved.model, question, retrieval.chunks)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        answer.errors.append(messages.classify_generation_failure(str(exc)))
    return answer
