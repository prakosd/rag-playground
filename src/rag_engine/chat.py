"""Conversational, history-aware retrieval-augmented generation (Step 5).

A follow-up question is first rewritten into a standalone search query using the
recent conversation (``condense_question``), context is retrieved for that query,
and the answer is generated with the recent history in the prompt. The pure
helpers take an already-resolved chat model so a UI can stream and tests run
offline with the echo model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage
from log4py import get_logger
from rag_engine import messages
from rag_engine.catalog import ECHO_MODEL
from rag_engine.config import ConversationalConfig, RagConfig
from rag_engine.decompose import plan_queries, update_state
from rag_engine.followups import suggest_followups, validate_followups
from rag_engine.llm import (
    ResolvedChatModel,
    resolve_auxiliary_model,
    resolve_chat_model,
    thinking_disabled_system_directive,
)
from rag_engine.models import (
    ChatTurn,
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RagAnswer,
    RetrievedChunk,
    StagePromptTrace,
    StageTokenUsage,
    TokenUsage,
    ValidatedFollowup,
)
from rag_engine.prompts import (
    _DEFAULT_TONE,
    CONDENSE_SYSTEM_PROMPT,
    DEFAULT_ANSWER_LANGUAGE,
    QA_SYSTEM_PROMPT,
    extract_token_usage,
    format_context,
    message_text,
    template_has_fields,
)
from rag_engine.rerank import rerank_chunks
from rag_engine.retrieval import RetrievalResult, retrieve, retrieve_multi

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "ChatAnswerStream",
    "ConversationalGeneration",
    "chat_answer",
    "condense_question",
    "conversational_answer",
    "conversational_answer_stream",
    "generate_chat_answer",
    "generate_chat_answer_with_usage",
    "stream_chat_answer",
    "stream_chat_answer_with_usage",
]

_logger = get_logger(__name__)


def _report(callback: Callable[[LibraryMessage], None] | None, message: LibraryMessage) -> None:
    """Send a pipeline-progress message to *callback* when one is provided."""
    if callback is not None:
        callback(message)


def _history_messages(history: Sequence[ChatTurn]) -> list[tuple[str, str]]:
    return [("ai" if turn.role == "assistant" else "human", turn.content) for turn in history]


class _UsageLedger:
    """Collects per-stage token usage across one conversational turn.

    ``record`` is passed to each stage as a callback; the stage tags its usage
    with a stable process key. ``stage_usages`` assembles the entries into
    :class:`StageTokenUsage` once the turn's models are known (the answer model
    for the ``answer`` stage, the auxiliary model for the rest).
    """

    def __init__(self) -> None:
        self.entries: list[tuple[str, TokenUsage]] = []

    def record(self, process: str, usage: TokenUsage | None) -> None:
        if usage is not None:
            self.entries.append((process, usage))

    def stage_usages(self, main_model_id: str, aux_model_id: str) -> list[StageTokenUsage]:
        return [
            StageTokenUsage(
                process=process,
                model_id=main_model_id if process == "answer" else aux_model_id,
                usage=usage,
            )
            for process, usage in self.entries
        ]


class _PromptLedger:
    """Collects each aux stage's rendered prompt and raw reply across one turn.

    Mirrors :class:`_UsageLedger`: ``record`` is passed to a stage as a callback and
    ``stage_traces`` returns the ordered :class:`StagePromptTrace` list for the answer.
    """

    def __init__(self) -> None:
        self.entries: list[StagePromptTrace] = []

    def record(self, process: str, prompt: str, response: str) -> None:
        self.entries.append(StagePromptTrace(process=process, prompt=prompt, response=response))

    def stage_traces(self) -> list[StagePromptTrace]:
        return list(self.entries)


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


def _chat_prompt(
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str,
    language: str,
    system_prompt: str | None,
    system_directive: str = "",
) -> tuple[Any, dict]:
    from langchain_core.prompts import ChatPromptTemplate

    # A custom system prompt is used only when it keeps the {context}/{tone}/
    # {language} slots; anything else falls back so a bad override never breaks
    # answer generation.
    system = (
        system_prompt
        if system_prompt and template_has_fields(system_prompt, ("context", "tone", "language"))
        else QA_SYSTEM_PROMPT
    )
    # A best-effort per-model directive (e.g. Nemotron's /no_think) rides in the
    # system message; Bedrock's chat template reads it and strips the token.
    if system_directive:
        system = f"{system} {system_directive}"
    prompt = ChatPromptTemplate.from_messages(
        [("system", system), *_history_messages(history), ("human", "{question}")]
    )
    return prompt, {"context": format_context(chunks), "tone": tone, "language": language}


def generate_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
    language: str = DEFAULT_ANSWER_LANGUAGE,
    system_prompt: str | None = None,
    system_directive: str = "",
) -> str:
    """Generate a conversational answer string."""
    text, _ = generate_chat_answer_with_usage(
        chat_model,
        question,
        chunks,
        history,
        tone=tone,
        language=language,
        system_prompt=system_prompt,
        system_directive=system_directive,
    )
    return text


def generate_chat_answer_with_usage(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
    language: str = DEFAULT_ANSWER_LANGUAGE,
    system_prompt: str | None = None,
    system_directive: str = "",
) -> tuple[str, TokenUsage | None]:
    """Generate a conversational answer with the token usage it reported."""
    from langchain_core.output_parsers import StrOutputParser

    prompt, values = _chat_prompt(
        chunks,
        history,
        tone=tone,
        language=language,
        system_prompt=system_prompt,
        system_directive=system_directive,
    )
    message = (prompt | chat_model).invoke({**values, "question": question})
    return StrOutputParser().invoke(message), extract_token_usage(message)


def stream_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
    language: str = DEFAULT_ANSWER_LANGUAGE,
    system_prompt: str | None = None,
    system_directive: str = "",
) -> Iterator[str]:
    """Yield conversational answer tokens as they are generated."""
    from langchain_core.output_parsers import StrOutputParser

    prompt, values = _chat_prompt(
        chunks,
        history,
        tone=tone,
        language=language,
        system_prompt=system_prompt,
        system_directive=system_directive,
    )
    yield from (prompt | chat_model | StrOutputParser()).stream({**values, "question": question})


class ChatAnswerStream:
    """Streams a conversational answer's tokens and captures the full text + usage.

    Mirrors :class:`rag_engine.qa.PromptGeneration` for the chat prompt (system +
    history + question): iterate it to receive answer-text chunks; when iteration
    finishes ``text`` holds the complete answer and ``usage`` the token counts the
    model reported (``None`` when the provider reports none, e.g. the echo model).
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        question: str,
        chunks: Sequence[RetrievedChunk],
        history: Sequence[ChatTurn],
        *,
        tone: str,
        language: str,
        system_prompt: str | None,
        system_directive: str = "",
    ) -> None:
        self._chat_model = chat_model
        self._question = question
        self._prompt, self._values = _chat_prompt(
            chunks,
            history,
            tone=tone,
            language=language,
            system_prompt=system_prompt,
            system_directive=system_directive,
        )
        self.text = ""
        self.usage: TokenUsage | None = None

    def __iter__(self) -> Iterator[str]:
        aggregate: Any = None
        parts: list[str] = []
        for chunk in (self._prompt | self._chat_model).stream(
            {**self._values, "question": self._question}
        ):
            if aggregate is None:
                aggregate = chunk
            else:
                try:
                    aggregate = aggregate + chunk
                except TypeError:  # a chunk type that does not support merging
                    aggregate = chunk
            piece = message_text(chunk)
            if piece:
                parts.append(piece)
                yield piece
        self.text = "".join(parts)
        self.usage = extract_token_usage(aggregate) if aggregate is not None else None


def stream_chat_answer_with_usage(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
    language: str = DEFAULT_ANSWER_LANGUAGE,
    system_prompt: str | None = None,
    system_directive: str = "",
) -> ChatAnswerStream:
    """Return a :class:`ChatAnswerStream` that streams the answer and captures usage."""
    return ChatAnswerStream(
        chat_model,
        question,
        chunks,
        history,
        tone=tone,
        language=language,
        system_prompt=system_prompt,
        system_directive=system_directive,
    )


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


@dataclass
class _PreparedTurn:
    """Resolved models + retrieved context for a turn, ready to answer.

    Produced by :func:`_prepare_turn` (the plan → retrieve → re-rank pipeline) and
    consumed by both the blocking (:func:`_compose_turn`) and streaming
    (:class:`ConversationalGeneration`) answer paths so they share one pipeline.
    """

    raw_question: str
    resolved: ResolvedChatModel
    aux: ResolvedChatModel
    chunks: list[RetrievedChunk]
    plan: QueryPlan
    recent: list[ChatTurn]
    reranker_used: str | None
    warnings: list[LibraryMessage]
    timings: dict[str, float]
    turn_index: int
    ledger: _UsageLedger
    prompt_ledger: _PromptLedger


def _prepare_turn(
    run_dir: Path | str,
    raw_question: str,
    state: ConversationState,
    config: ConversationalConfig,
    *,
    history: Sequence[ChatTurn],
    cached_chunks: Sequence[RetrievedChunk] | None,
    retriever: Callable[..., RetrievalResult],
    chat_resolver: Callable[..., tuple[ResolvedChatModel, list[LibraryMessage]]],
    aux_resolver: Callable[..., tuple[ResolvedChatModel, list[LibraryMessage]]],
    progress_callback: Callable[[LibraryMessage], None] | None,
) -> _PreparedTurn | ConversationalAnswer:
    """Resolve models and gather context (plan → retrieve → re-rank) for a turn.

    Returns a ``_PreparedTurn`` ready to answer, or a terminal
    ``ConversationalAnswer`` when the turn cannot proceed (empty question or a
    retrieval error). A ``cached_chunks`` hit skips planning, retrieval, and
    re-ranking.
    """
    raw_question = raw_question.strip()
    if not raw_question:
        return ConversationalAnswer(answer="", state=state, errors=[messages.empty_question()])

    timings: dict[str, float] = {}
    warnings: list[LibraryMessage] = []
    ledger = _UsageLedger()
    prompt_ledger = _PromptLedger()

    resolved, chat_warnings = chat_resolver(
        config.rag.llm_model,
        temperature=config.rag.temperature,
        max_tokens=config.rag.max_tokens,
    )
    warnings.extend(chat_warnings)
    aux_resolved, aux_warnings = aux_resolver(config)
    warnings.extend(aux_warnings)
    recent = list(history)[-2 * config.answer_recent_turns :] if config.answer_recent_turns else []
    turn_index = len(history) // 2

    if cached_chunks is not None:
        _logger.info("Conversational RAG over %s: cache hit", Path(run_dir).name)
        return _PreparedTurn(
            raw_question=raw_question,
            resolved=resolved,
            aux=aux_resolved,
            chunks=list(cached_chunks),
            plan=QueryPlan(sub_questions=[raw_question]),
            recent=recent,
            reranker_used=None,
            warnings=warnings,
            timings=timings,
            turn_index=turn_index,
            ledger=ledger,
            prompt_ledger=prompt_ledger,
        )

    _logger.info(
        "Conversational RAG over %s: model=%s, aux=%s",
        Path(run_dir).name,
        resolved.model_id,
        aux_resolved.model_id,
    )

    _report(progress_callback, messages.progress_plan())
    start = perf_counter()
    plan = plan_queries(
        aux_resolved.model,
        state,
        raw_question,
        config,
        model_id=aux_resolved.model_id,
        record_usage=ledger.record,
        record_prompt=prompt_ledger.record,
    )
    timings["plan"] = perf_counter() - start
    warnings.extend(plan.warnings)
    sub_questions = plan.sub_questions or [raw_question]

    _report(progress_callback, messages.progress_retrieve())
    start = perf_counter()
    retrieval = retrieve_multi(
        run_dir,
        sub_questions,
        config.rag,
        retriever=retriever,
        max_workers=config.max_workers,
    )
    timings["retrieve"] = perf_counter() - start
    warnings.extend(retrieval.warnings)
    if retrieval.errors:
        return ConversationalAnswer(
            answer="",
            sources=retrieval.chunks,
            plan=plan,
            state=state,
            model_used=resolved.model_id,
            aux_model_used=aux_resolved.model_id,
            timings=timings,
            token_usage=ledger.stage_usages(resolved.model_id, aux_resolved.model_id),
            prompt_traces=prompt_ledger.stage_traces(),
            warnings=warnings,
            errors=retrieval.errors,
        )

    _report(progress_callback, messages.progress_rerank())
    start = perf_counter()
    reranked, rerank_warnings = rerank_chunks(
        sub_questions,
        retrieval.chunks,
        config.rerank_top_n,
        config,
        chat_model=aux_resolved.model if aux_resolved.model_id != ECHO_MODEL else None,
        record_usage=ledger.record,
        record_prompt=prompt_ledger.record,
        system_directive=thinking_disabled_system_directive(aux_resolved.model_id),
    )
    timings["rerank"] = perf_counter() - start
    warnings.extend(rerank_warnings)

    return _PreparedTurn(
        raw_question=raw_question,
        resolved=resolved,
        aux=aux_resolved,
        chunks=reranked,
        plan=plan,
        recent=recent,
        reranker_used=config.reranker,
        warnings=warnings,
        timings=timings,
        turn_index=turn_index,
        ledger=ledger,
        prompt_ledger=prompt_ledger,
    )


def conversational_answer(
    run_dir: Path | str,
    raw_question: str,
    state: ConversationState,
    config: ConversationalConfig,
    *,
    history: Sequence[ChatTurn] = (),
    cached_chunks: Sequence[RetrievedChunk] | None = None,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
    aux_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_auxiliary_model,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
) -> ConversationalAnswer:
    """Answer a turn with the advanced conversational RAG pipeline (Step 5).

    Resolves the answer model and a small auxiliary model, then runs the full
    pipeline: plan (decompose) → multi-query retrieval → re-ranking → grounded
    answer → validated follow-ups → conversation-state update, returning a
    ``ConversationalAnswer`` with per-stage timings. A ``cached_chunks`` hit skips
    planning, retrieval, and re-ranking and answers straight from the carried
    passages (still generating follow-ups and updating state).
    """
    prepared = _prepare_turn(
        run_dir,
        raw_question,
        state,
        config,
        history=history,
        cached_chunks=cached_chunks,
        retriever=retriever,
        chat_resolver=chat_resolver,
        aux_resolver=aux_resolver,
        progress_callback=progress_callback,
    )
    if isinstance(prepared, ConversationalAnswer):
        return prepared
    return _compose_turn(
        run_dir,
        prepared.raw_question,
        prepared.chunks,
        prepared.recent,
        prepared.plan,
        state,
        prepared.resolved,
        prepared.aux,
        config,
        retriever=retriever,
        warnings=prepared.warnings,
        timings=prepared.timings,
        turn_index=prepared.turn_index,
        reranker_used=prepared.reranker_used,
        ledger=prepared.ledger,
        prompt_ledger=prepared.prompt_ledger,
        progress_callback=progress_callback,
    )


def conversational_answer_stream(
    run_dir: Path | str,
    raw_question: str,
    state: ConversationState,
    config: ConversationalConfig,
    *,
    history: Sequence[ChatTurn] = (),
    cached_chunks: Sequence[RetrievedChunk] | None = None,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
    aux_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_auxiliary_model,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
) -> ConversationalGeneration:
    """Stream the Step 5 conversational answer (see :func:`conversational_answer`).

    Runs the same pre-answer pipeline (plan → retrieve → re-rank) synchronously,
    firing progress, then returns a :class:`ConversationalGeneration` whose
    iteration streams the grounded answer's tokens (follow-ups run concurrently);
    once drained, ``answer`` holds the full ``ConversationalAnswer``.
    """
    prepared = _prepare_turn(
        run_dir,
        raw_question,
        state,
        config,
        history=history,
        cached_chunks=cached_chunks,
        retriever=retriever,
        chat_resolver=chat_resolver,
        aux_resolver=aux_resolver,
        progress_callback=progress_callback,
    )
    if isinstance(prepared, ConversationalAnswer):
        return ConversationalGeneration(
            run_dir,
            state,
            config,
            None,
            retriever=retriever,
            progress_callback=progress_callback,
            answer=prepared,
        )
    return ConversationalGeneration(
        run_dir,
        state,
        config,
        prepared,
        retriever=retriever,
        progress_callback=progress_callback,
    )


def _answer_stage(
    resolved: ResolvedChatModel,
    raw_question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    tone: str,
    language: str,
    system_prompt: str | None = None,
    record_usage: Callable[[str, TokenUsage | None], None] | None = None,
) -> tuple[str, list[LibraryMessage], float]:
    """Generate the grounded answer, returning (text, errors, elapsed seconds)."""
    errors: list[LibraryMessage] = []
    start = perf_counter()
    answer_text = ""
    try:
        answer_text, usage = generate_chat_answer_with_usage(
            resolved.model,
            raw_question,
            chunks,
            history,
            tone=tone,
            language=language,
            system_prompt=system_prompt,
            system_directive=thinking_disabled_system_directive(resolved.model_id),
        )
        if record_usage is not None:
            record_usage("answer", usage)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("Conversational RAG generation failed: %s", exc)
        errors.append(messages.classify_generation_failure(str(exc)))
    return answer_text, errors, perf_counter() - start


def _followups_stage(
    run_dir: Path | str,
    aux: ResolvedChatModel,
    chunks: Sequence[RetrievedChunk],
    plan: QueryPlan,
    config: ConversationalConfig,
    retriever: Callable[..., RetrievalResult],
    record_usage: Callable[[str, TokenUsage | None], None] | None = None,
    record_prompt: Callable[[str, str, str], None] | None = None,
    asked_questions: Sequence[str] = (),
) -> tuple[list[ValidatedFollowup], list[LibraryMessage], float]:
    """Suggest and validate follow-ups, returning (follow_ups, warnings, elapsed seconds)."""
    warnings: list[LibraryMessage] = []
    follow_ups: list[ValidatedFollowup] = []
    start = perf_counter()
    directive = thinking_disabled_system_directive(aux.model_id)
    try:
        candidates = suggest_followups(
            aux.model,
            chunks,
            plan,
            config,
            asked_questions=asked_questions,
            record_usage=record_usage,
            record_prompt=record_prompt,
            system_directive=directive,
        )
        follow_ups = validate_followups(
            run_dir,
            candidates,
            config,
            model=aux.model,
            retriever=retriever,
            asked_questions=asked_questions,
            record_usage=record_usage,
            record_prompt=record_prompt,
            system_directive=directive,
        )
        if candidates and not follow_ups:
            warnings.append(messages.followups_none_valid())
    except Exception as exc:  # noqa: BLE001 - follow-ups are optional
        _logger.warning("Follow-up generation failed: %s", exc)
        warnings.append(messages.followups_generation_failed(str(exc)))
    return follow_ups, warnings, perf_counter() - start


def _submit_followups(
    executor: ThreadPoolExecutor,
    run_dir: Path | str,
    aux: ResolvedChatModel,
    chunks: Sequence[RetrievedChunk],
    plan: QueryPlan,
    config: ConversationalConfig,
    retriever: Callable[..., RetrievalResult],
    record_usage: Callable[[str, TokenUsage | None], None],
    record_prompt: Callable[[str, str, str], None],
    *,
    asked_questions: Sequence[str],
) -> Future | None:
    """Submit the follow-up stage to *executor*, or None when it is off/offline."""
    if not (config.followups_enabled and aux.model_id != ECHO_MODEL):
        return None
    return executor.submit(
        _followups_stage,
        run_dir,
        aux,
        chunks,
        plan,
        config,
        retriever,
        record_usage,
        record_prompt,
        asked_questions=asked_questions,
    )


def _finalize_turn(
    raw_question: str,
    chunks: list[RetrievedChunk],
    plan: QueryPlan,
    state: ConversationState,
    resolved: ResolvedChatModel,
    aux: ResolvedChatModel,
    config: ConversationalConfig,
    *,
    answer_text: str,
    follow_ups: list[ValidatedFollowup],
    warnings: list[LibraryMessage],
    errors: list[LibraryMessage],
    timings: dict[str, float],
    turn_index: int,
    reranker_used: str | None,
    ledger: _UsageLedger,
    prompt_ledger: _PromptLedger,
    progress_callback: Callable[[LibraryMessage], None] | None,
) -> ConversationalAnswer:
    """Roll conversation state forward and assemble the ``ConversationalAnswer``.

    Shared tail of the blocking and streaming answer paths: ``update_state`` runs
    here because it needs the finished answer text.
    """
    resolved_question = "; ".join(plan.sub_questions) or raw_question
    _report(progress_callback, messages.progress_state())
    start = perf_counter()
    next_state = update_state(
        aux.model,
        state,
        resolved_question,
        answer_text,
        config,
        model_id=aux.model_id,
        turn_index=turn_index,
        asked_this_turn=plan.sub_questions,
        record_usage=ledger.record,
        record_prompt=prompt_ledger.record,
    )
    timings["state"] = perf_counter() - start

    return ConversationalAnswer(
        answer=answer_text,
        sources=chunks,
        plan=plan,
        follow_ups=follow_ups,
        state=next_state,
        model_used=resolved.model_id,
        aux_model_used=aux.model_id,
        reranker_used=reranker_used,
        timings=timings,
        token_usage=ledger.stage_usages(resolved.model_id, aux.model_id),
        prompt_traces=prompt_ledger.stage_traces(),
        warnings=warnings,
        errors=errors,
    )


def _compose_turn(
    run_dir: Path | str,
    raw_question: str,
    chunks: list[RetrievedChunk],
    history: Sequence[ChatTurn],
    plan: QueryPlan,
    state: ConversationState,
    resolved: ResolvedChatModel,
    aux: ResolvedChatModel,
    config: ConversationalConfig,
    *,
    retriever: Callable[..., RetrievalResult],
    warnings: list[LibraryMessage],
    timings: dict[str, float],
    turn_index: int,
    reranker_used: str | None,
    ledger: _UsageLedger,
    prompt_ledger: _PromptLedger,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
) -> ConversationalAnswer:
    """Generate the answer and follow-ups concurrently, then roll state forward.

    The answer (main model) and follow-ups (auxiliary model) are independent given
    the retrieved chunks, so they run on a small thread pool to overlap their model
    calls; ``update_state`` follows because it needs the finished answer.
    """
    _report(progress_callback, messages.progress_answer())
    follow_ups: list[ValidatedFollowup] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        answer_future = executor.submit(
            _answer_stage,
            resolved,
            raw_question,
            chunks,
            history,
            config.tone,
            config.language,
            config.prompts.answer,
            ledger.record,
        )
        followups_future = _submit_followups(
            executor,
            run_dir,
            aux,
            chunks,
            plan,
            config,
            retriever,
            ledger.record,
            prompt_ledger.record,
            asked_questions=state.asked_questions,
        )
        answer_text, errors, timings["answer"] = answer_future.result()
        if followups_future is not None:
            follow_ups, followups_warnings, timings["followups"] = followups_future.result()
            warnings.extend(followups_warnings)

    return _finalize_turn(
        raw_question,
        chunks,
        plan,
        state,
        resolved,
        aux,
        config,
        answer_text=answer_text,
        follow_ups=follow_ups,
        warnings=warnings,
        errors=errors,
        timings=timings,
        turn_index=turn_index,
        reranker_used=reranker_used,
        ledger=ledger,
        prompt_ledger=prompt_ledger,
        progress_callback=progress_callback,
    )


class ConversationalGeneration:
    """Streams a Step 5 turn's answer tokens, then exposes the full answer.

    Iterate it (e.g. via ``st.write_stream``) to receive the grounded answer's
    tokens as they arrive; follow-ups run concurrently on a worker thread. When the
    stream drains, conversation state is rolled forward and ``answer`` holds the
    complete ``ConversationalAnswer``. A terminal turn (empty question or a
    retrieval error) yields no tokens and ``answer`` is set from the start.
    """

    def __init__(
        self,
        run_dir: Path | str,
        state: ConversationState,
        config: ConversationalConfig,
        prepared: _PreparedTurn | None,
        *,
        retriever: Callable[..., RetrievalResult],
        progress_callback: Callable[[LibraryMessage], None] | None = None,
        answer: ConversationalAnswer | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._state = state
        self._config = config
        self._prepared = prepared
        self._retriever = retriever
        self._progress = progress_callback
        self.answer: ConversationalAnswer | None = answer

    def __iter__(self) -> Iterator[str]:
        prepared = self._prepared
        if prepared is None:  # terminal turn: nothing to stream
            return
        config = self._config
        errors: list[LibraryMessage] = []
        follow_ups: list[ValidatedFollowup] = []

        _report(self._progress, messages.progress_answer())
        with ThreadPoolExecutor(max_workers=2) as executor:
            followups_future = _submit_followups(
                executor,
                self._run_dir,
                prepared.aux,
                prepared.chunks,
                prepared.plan,
                config,
                self._retriever,
                prepared.ledger.record,
                prepared.prompt_ledger.record,
                asked_questions=self._state.asked_questions,
            )
            start = perf_counter()
            parts: list[str] = []
            try:
                answer_stream = stream_chat_answer_with_usage(
                    prepared.resolved.model,
                    prepared.raw_question,
                    prepared.chunks,
                    prepared.recent,
                    tone=config.tone,
                    language=config.language,
                    system_prompt=config.prompts.answer,
                    system_directive=thinking_disabled_system_directive(prepared.resolved.model_id),
                )
                for piece in answer_stream:
                    parts.append(piece)
                    yield piece
                prepared.ledger.record("answer", answer_stream.usage)
            except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
                _logger.warning("Conversational RAG generation failed: %s", exc)
                errors.append(messages.classify_generation_failure(str(exc)))
            answer_text = "".join(parts)
            prepared.timings["answer"] = perf_counter() - start
            if followups_future is not None:
                follow_ups, followups_warnings, prepared.timings["followups"] = (
                    followups_future.result()
                )
                prepared.warnings.extend(followups_warnings)

        self.answer = _finalize_turn(
            prepared.raw_question,
            prepared.chunks,
            prepared.plan,
            self._state,
            prepared.resolved,
            prepared.aux,
            config,
            answer_text=answer_text,
            follow_ups=follow_ups,
            warnings=prepared.warnings,
            errors=errors,
            timings=prepared.timings,
            turn_index=prepared.turn_index,
            reranker_used=prepared.reranker_used,
            ledger=prepared.ledger,
            prompt_ledger=prepared.prompt_ledger,
            progress_callback=self._progress,
        )
