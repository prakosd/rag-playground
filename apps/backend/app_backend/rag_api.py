"""HTTP routes for the RAG read APIs (semantic search + grounded answers).

Each handler resolves the request ``run_dir`` under the configured artifacts root
(rejecting path traversal), builds a ``RagConfig`` from the optional overrides, calls
the matching ``rag_engine`` function, and serializes the dataclass result — including
``LibraryMessage`` warnings/errors via ``as_dict()`` so any client can localize by
``code``. The library reports failures in ``.errors`` rather than raising, so those
become a normal 200 payload; only a bad request path is a 4xx.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rag_engine import (
    ChatTurn,
    ConversationalConfig,
    ConversationState,
    RagConfig,
    RetrievedChunk,
    answer_question,
    conversational_answer_stream,
    resolve_chat_model,
    retrieve,
    stream_prompt,
    thinking_disabled_system_directive,
)
from rag_engine import messages as rag_messages

from app_backend.config import resolve_within_artifacts

router = APIRouter(prefix="/rag", tags=["rag"])

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


class SearchRequest(BaseModel):
    run_dir: str
    query: str
    top_k: int | None = None
    score_threshold: float | None = None
    search_type: Literal["similarity", "mmr"] | None = None
    source_filter: list[str] = []


class AnswerRequest(BaseModel):
    run_dir: str
    question: str
    llm_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_k: int | None = None


class GenerateRequest(BaseModel):
    prompt: str
    llm_model: str | None = None


class ConversationalRequest(BaseModel):
    run_dir: str
    question: str
    state: dict[str, Any] = {}
    config: dict[str, Any] = {}
    history: list[dict[str, Any]] = []
    cached_chunks: list[dict[str, Any]] | None = None


def _config(**overrides: Any) -> RagConfig:
    return RagConfig(**{key: value for key, value in overrides.items() if value is not None})


def _chunk_dict(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "text": chunk.text,
        "source": chunk.source,
        "score": chunk.score,
        "metadata": chunk.metadata,
        "matched_queries": list(chunk.matched_queries),
        "retrieval_rank": chunk.retrieval_rank,
    }


def _messages(items: Any) -> list[dict[str, Any]]:
    return [message.as_dict() for message in items]


def _usage_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


# ── Conversational (Step 5) serialization ────────────────────────────────────


def _chunk_from(data: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        text=data["text"],
        source=data["source"],
        score=data["score"],
        metadata=data.get("metadata", {}),
        matched_queries=tuple(data.get("matched_queries", ())),
        retrieval_rank=int(data.get("retrieval_rank", 0)),
    )


def _state_from(data: dict[str, Any]) -> ConversationState:
    return ConversationState(
        summary=data.get("summary", ""),
        entities=dict(data.get("entities", {})),
        recent_resolved=tuple(data.get("recent_resolved", ())),
        open_threads=tuple(data.get("open_threads", ())),
        asked_questions=tuple(data.get("asked_questions", ())),
    )


def _state_dict(state: Any) -> dict[str, Any]:
    return {
        "summary": state.summary,
        "entities": dict(state.entities),
        "recent_resolved": list(state.recent_resolved),
        "open_threads": list(state.open_threads),
        "asked_questions": list(state.asked_questions),
    }


def _followup_dict(item: Any) -> dict[str, Any]:
    return {
        "question": item.question,
        "chunks": [_chunk_dict(chunk) for chunk in item.chunks],
        "score": item.score,
        "verdict": item.verdict,
        "checked_by_llm": item.checked_by_llm,
    }


def _plan_dict(plan: Any) -> dict[str, Any]:
    return {
        "sub_questions": list(plan.sub_questions),
        "degraded": plan.degraded,
        "proposed_count": plan.proposed_count,
        "warnings": _messages(plan.warnings),
    }


def _answer_dict(answer: Any) -> dict[str, Any]:
    return {
        "answer": answer.answer,
        "sources": [_chunk_dict(chunk) for chunk in answer.sources],
        "overflow_sources": [_chunk_dict(chunk) for chunk in answer.overflow_sources],
        "plan": _plan_dict(answer.plan),
        "follow_ups": [_followup_dict(item) for item in answer.follow_ups],
        "dropped_followups": [_followup_dict(item) for item in answer.dropped_followups],
        "evaluated_followups": [_followup_dict(item) for item in answer.evaluated_followups],
        "state": _state_dict(answer.state),
        "model_used": answer.model_used,
        "aux_model_used": answer.aux_model_used,
        "reranker_used": answer.reranker_used,
        "timings": dict(answer.timings),
        "token_usage": [
            {"process": u.process, "model_id": u.model_id, "usage": _usage_dict(u.usage)}
            for u in answer.token_usage
        ],
        "prompt_traces": [
            {"process": t.process, "prompt": t.prompt, "response": t.response}
            for t in answer.prompt_traces
        ],
        "warnings": _messages(answer.warnings),
        "errors": _messages(answer.errors),
    }


@router.post("/search")
def search(request: SearchRequest) -> dict[str, Any]:
    run_path = resolve_within_artifacts(request.run_dir)
    config = _config(
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        search_type=request.search_type,
        source_filter=tuple(request.source_filter) or None,
    )
    result = retrieve(run_path, request.query, config)
    return {
        "chunks": [_chunk_dict(chunk) for chunk in result.chunks],
        "warnings": _messages(result.warnings),
        "errors": _messages(result.errors),
    }


@router.post("/answer")
def answer(request: AnswerRequest) -> dict[str, Any]:
    run_path = resolve_within_artifacts(request.run_dir)
    config = _config(
        llm_model=request.llm_model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_k=request.top_k,
    )
    result = answer_question(run_path, request.question, config)
    return {
        "answer": result.answer,
        "model_used": result.model_used,
        "sources": [_chunk_dict(chunk) for chunk in result.sources],
        "warnings": _messages(result.warnings),
        "errors": _messages(result.errors),
    }


def _close_stream(stream: Iterator[str] | None) -> None:
    """Close a generation iterator on teardown (e.g. client disconnect) if it can.

    The streaming endpoints hand out a generator-backed iterator; closing it when the
    response generator is torn down stops the underlying model stream deterministically
    instead of leaving it for garbage collection.
    """
    close = getattr(stream, "close", None)
    if callable(close):
        close()


@router.post("/generate")
def generate(request: GenerateRequest) -> StreamingResponse:
    """Stream an answer for a raw prompt (Step 4 "send"), as newline-delimited JSON.

    Emits ``{"token": ...}`` frames while the model streams, then a final
    ``{"done": true, "usage": ..., "model_used": ..., "warnings": [...]}`` frame. A
    generation failure becomes a single ``{"error": {...}}`` frame. The model is
    resolved here (echo fallback plus its warning), so the client never needs
    credentials — it just renders what streams back.
    """
    resolved, warnings = resolve_chat_model(request.llm_model or "")
    directive = thinking_disabled_system_directive(resolved.model_id)
    generation = stream_prompt(resolved.model, request.prompt, system_directive=directive)

    def frames() -> Iterator[str]:
        stream: Iterator[str] | None = None
        try:
            stream = iter(generation)
            for piece in stream:
                yield json.dumps({"token": piece}) + "\n"
        except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
            error = rag_messages.classify_generation_failure(str(exc)).as_dict()
            yield json.dumps({"error": error}) + "\n"
            return
        finally:
            _close_stream(stream)  # stop the model stream if the client disconnected
        yield (
            json.dumps(
                {
                    "done": True,
                    "usage": _usage_dict(generation.usage),
                    "model_used": resolved.model_id,
                    "warnings": _messages(warnings),
                }
            )
            + "\n"
        )

    return StreamingResponse(frames(), media_type=_NDJSON_MEDIA_TYPE)


@router.post("/conversational")
def conversational(request: ConversationalRequest) -> StreamingResponse:
    """Stream a Step 5 conversational turn as newline-delimited JSON.

    Emits ``{"progress": ...}`` stage-label frames and ``{"token": ...}`` frames
    interleaved, then a final ``{"done": <answer>}`` frame carrying the full
    ``ConversationalAnswer``. A failure becomes a single ``{"error": {...}}`` frame.
    The prior state + config + history arrive as JSON and the models resolve here with
    the library defaults, so the client holds no credentials.
    """
    run_path = resolve_within_artifacts(request.run_dir)
    state = _state_from(request.state)
    config = ConversationalConfig.model_validate(request.config)
    history = [ChatTurn(role=item["role"], content=item["content"]) for item in request.history]
    cached = (
        [_chunk_from(chunk) for chunk in request.cached_chunks]
        if request.cached_chunks is not None
        else None
    )

    def frames() -> Iterator[str]:
        buffer: list[dict[str, Any]] = []
        generation = conversational_answer_stream(
            run_path,
            request.question,
            state,
            config,
            history=history,
            cached_chunks=cached,
            progress_callback=lambda message: buffer.append(message.as_dict()),
        )

        def flush() -> Iterator[str]:
            while buffer:
                yield json.dumps({"progress": buffer.pop(0)}) + "\n"

        yield from flush()  # plan/retrieve/re-rank progress fired while preparing
        stream: Iterator[str] | None = None
        try:
            stream = iter(generation)
            for piece in stream:
                yield from flush()  # answer/state progress fired during streaming
                yield json.dumps({"token": piece}) + "\n"
            yield from flush()
        except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
            error = rag_messages.classify_generation_failure(str(exc)).as_dict()
            yield json.dumps({"error": error}) + "\n"
            return
        finally:
            _close_stream(stream)  # stop the answer stream if the client disconnected
        payload = _answer_dict(generation.answer) if generation.answer is not None else {}
        yield json.dumps({"done": payload}) + "\n"

    return StreamingResponse(frames(), media_type=_NDJSON_MEDIA_TYPE)
