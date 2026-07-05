"""Conversational, history-aware retrieval-augmented generation (Step 5).

A follow-up question is first rewritten into a standalone search query using the
recent conversation (``condense_question``), context is retrieved for that query,
and the answer is generated with the recent history in the prompt. The pure
helpers take an already-resolved chat model so a UI can stream and tests run
offline with the echo model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage, get_logger
from rag_engine import messages
from rag_engine.catalog import ECHO_MODEL
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel, resolve_chat_model
from rag_engine.models import ChatTurn, RagAnswer, RetrievedChunk
from rag_engine.prompts import CONDENSE_SYSTEM_PROMPT, QA_SYSTEM_PROMPT, format_context
from rag_engine.retrieval import RetrievalResult, retrieve

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "chat_answer",
    "condense_question",
    "generate_chat_answer",
    "stream_chat_answer",
]

_logger = get_logger(__name__)


def _history_messages(history: Sequence[ChatTurn]) -> list[tuple[str, str]]:
    return [("ai" if turn.role == "assistant" else "human", turn.content) for turn in history]


def condense_question(chat_model: BaseChatModel, history: Sequence[ChatTurn], question: str) -> str:
    """Rewrite a follow-up *question* into a standalone search query."""
    question = question.strip()
    if not history:
        return question
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", CONDENSE_SYSTEM_PROMPT), *_history_messages(history), ("human", "{question}")]
    )
    chain = prompt | chat_model | StrOutputParser()
    rewritten = chain.invoke({"question": question}).strip()
    return rewritten or question


def _chat_chain(
    chat_model: BaseChatModel,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
) -> tuple[Any, dict]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", QA_SYSTEM_PROMPT), *_history_messages(history), ("human", "{question}")]
    )
    return prompt | chat_model | StrOutputParser(), {"context": format_context(chunks)}


def generate_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
) -> str:
    """Generate a conversational answer string."""
    chain, base = _chat_chain(chat_model, chunks, history)
    return chain.invoke({**base, "question": question})


def stream_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
) -> Iterator[str]:
    """Yield conversational answer tokens as they are generated."""
    chain, base = _chat_chain(chat_model, chunks, history)
    yield from chain.stream({**base, "question": question})


def chat_answer(
    run_dir: Path | str,
    question: str,
    history: Sequence[ChatTurn],
    config: RagConfig,
    *,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
) -> RagAnswer:
    """Answer a follow-up *question* using conversation *history* and the index."""
    question = question.strip()
    if not question:
        return RagAnswer(answer="", errors=[messages.empty_question()])

    resolved, chat_warnings = chat_resolver(
        config.llm_model, temperature=config.temperature, max_tokens=config.max_tokens
    )
    _logger.info(
        "Conversational RAG over %s: model=%s, %d turn(s) of history",
        Path(run_dir).name,
        resolved.model_id,
        len(history),
    )
    # Echo cannot rewrite a query, so only condense with a real model.
    if history and resolved.model_id != ECHO_MODEL:
        try:
            search_query = condense_question(resolved.model, history, question)
        except Exception:  # noqa: BLE001 - condensation is best-effort
            search_query = question
    else:
        search_query = question

    retrieval = retriever(run_dir, search_query, config)
    if retrieval.errors:
        return RagAnswer(
            answer="",
            sources=retrieval.chunks,
            model_used=resolved.model_id,
            warnings=[*chat_warnings, *retrieval.warnings],
            errors=retrieval.errors,
        )

    answer = RagAnswer(
        answer="",
        sources=retrieval.chunks,
        model_used=resolved.model_id,
        warnings=[*chat_warnings, *retrieval.warnings],
    )
    try:
        answer.answer = generate_chat_answer(resolved.model, question, retrieval.chunks, history)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("Conversational RAG generation failed: %s", exc)
        answer.errors.append(messages.classify_generation_failure(str(exc)))
    return answer
