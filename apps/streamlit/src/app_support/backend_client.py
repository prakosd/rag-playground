"""Optional HTTP client to the FastAPI backend, used when ``BACKEND_MODE=http``.

The Streamlit app runs the libraries in-process by default. When an operator opts in with
``BACKEND_MODE=http``, every step is offloaded to the backend: the crawl job (``/crawl``,
Step 1), the index job (``/index``, Step 2), retrieval (Step 3), the Basic RAG Q&A "send"
(``/rag/generate``, Step 4), and the conversational turn (``/rag/conversational``, Step 5)
all run there and stream back instead of running locally (the crawl/index jobs need
frontend+backend shared storage; see docs/CLOUD_DEPLOYMENT.md). A failed request degrades to
a structured error so the UI shows its natural error reply rather than crashing.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
from artifact_store import LibraryMessage
from rag_engine import (
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RagConfig,
    RetrievalResult,
    RetrievedChunk,
    StagePromptTrace,
    StageTokenUsage,
    ValidatedFollowup,
)
from rag_engine import messages as rag_messages
from rag_engine.models import TokenUsage

from app_support.settings import get_settings

__all__ = [
    "HttpConversationalGeneration",
    "HttpPromptGeneration",
    "http_conversational",
    "http_generate",
    "http_search",
    "run_remote_crawl",
    "run_remote_index",
]

_TIMEOUT_SECONDS = 60.0
# A generation stream can run longer than one search, so give the whole stream room.
_STREAM_TIMEOUT_SECONDS = 300.0
# How often the crawl-cancel watcher polls the cancel flag while a remote crawl streams.
_CANCEL_POLL_SECONDS = 0.2
# Header carrying the optional shared backend secret (mirrors app_backend.auth).
_BACKEND_TOKEN_HEADER = "X-Backend-Token"


def _auth_headers() -> dict[str, str]:
    """Return the backend auth header when a shared token is configured, else empty.

    Mirrors the backend's optional ``X-Backend-Token`` guard: when ``BACKEND_AUTH_TOKEN`` is
    set, the frontend attaches it so an authenticated backend accepts the request; empty
    (default) sends nothing, matching the backend's open default.
    """
    token = get_settings().backend_auth_token
    return {_BACKEND_TOKEN_HEADER: token} if token else {}


def http_search(
    run_dir: Path | str, query: str, config: RagConfig, *, client: Any | None = None
) -> RetrievalResult:
    """Call the backend ``POST /rag/search`` and rebuild a ``RetrievalResult``."""
    base_url = get_settings().backend_url.rstrip("/")
    payload = {
        "run_dir": str(run_dir),
        "query": query,
        "top_k": config.top_k,
        "score_threshold": config.score_threshold,
        "search_type": config.search_type,
        "source_filter": list(config.source_filter),
    }
    poster = client or httpx
    try:
        response = poster.post(
            f"{base_url}/rag/search",
            json=payload,
            headers=_auth_headers(),
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return RetrievalResult(
            chunks=[_chunk(item) for item in data.get("chunks", [])],
            warnings=[_message(item) for item in data.get("warnings", [])],
            errors=[_message(item) for item in data.get("errors", [])],
        )
    except Exception as exc:  # network / HTTP / parse failure → a structured, localizable error
        detail = f"backend request failed: {exc}"
        return RetrievalResult(errors=[rag_messages.retrieval_failed(detail)])


def _chunk(data: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        text=data["text"],
        source=data["source"],
        score=data["score"],
        metadata=data.get("metadata", {}),
        matched_queries=tuple(data.get("matched_queries", ())),
        retrieval_rank=int(data.get("retrieval_rank", 0)),
    )


def _message(data: dict[str, Any]) -> LibraryMessage:
    # The backend serializes via LibraryMessage.as_dict(), whose text key is "text".
    return LibraryMessage(
        code=data["code"],
        default_text=data.get("text", ""),
        params=data.get("params", {}),
        severity=data.get("severity", "info"),
    )


def _usage(data: dict[str, Any] | None) -> TokenUsage | None:
    if not data:
        return None
    return TokenUsage(
        input_tokens=data.get("input_tokens"),
        output_tokens=data.get("output_tokens"),
        total_tokens=data.get("total_tokens"),
    )


class HttpPromptGeneration:
    """Client-side mirror of ``rag_engine.PromptGeneration`` backed by the backend stream.

    Iterate it (e.g. via ``st.write_stream``) to receive answer-text pieces from the backend
    ``POST /rag/generate`` NDJSON stream. When iteration finishes, ``text`` holds the full
    answer, ``usage`` the token counts, ``model_used`` the model the backend resolved, and
    ``warnings`` its fallback notices. A network/backend failure lands in ``error`` (a
    structured, localizable message) instead of raising, so the page renders its normal
    error reply rather than crashing.
    """

    def __init__(self, prompt: str, model: str, *, client: Any | None = None) -> None:
        self._prompt = prompt
        self._model = model
        self._client = client
        self.text = ""
        self.usage: TokenUsage | None = None
        self.model_used = (model or "").strip()
        self.warnings: list[LibraryMessage] = []
        self.error: LibraryMessage | None = None

    def __iter__(self) -> Iterator[str]:
        base_url = get_settings().backend_url.rstrip("/")
        payload = {"prompt": self._prompt, "llm_model": self._model}
        poster = self._client or httpx
        parts: list[str] = []
        try:
            with poster.stream(
                "POST",
                f"{base_url}/rag/generate",
                json=payload,
                headers=_auth_headers(),
                timeout=_STREAM_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    frame = json.loads(line)
                    token = frame.get("token")
                    if token is not None:
                        parts.append(token)
                        yield token
                    elif frame.get("error") is not None:
                        self.error = _message(frame["error"])
                    elif frame.get("done"):
                        self.usage = _usage(frame.get("usage"))
                        self.model_used = frame.get("model_used") or self.model_used
                        self.warnings = [_message(item) for item in frame.get("warnings", [])]
        except Exception as exc:  # network / HTTP / parse failure → structured generation error
            self.error = rag_messages.classify_generation_failure(f"backend request failed: {exc}")
        self.text = "".join(parts)


def http_generate(prompt: str, model: str, *, client: Any | None = None) -> HttpPromptGeneration:
    """Stream a raw-prompt answer from the backend ``POST /rag/generate`` (Step 4 send)."""
    return HttpPromptGeneration(prompt, model, client=client)


# ── Conversational (Step 5) round-trip ───────────────────────────────────────


def _state_to_dict(state: Any) -> dict[str, Any]:
    return {
        "summary": state.summary,
        "entities": dict(state.entities),
        "recent_resolved": list(state.recent_resolved),
        "open_threads": list(state.open_threads),
        "asked_questions": list(state.asked_questions),
    }


def _chunk_to_dict(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "text": chunk.text,
        "source": chunk.source,
        "score": chunk.score,
        "metadata": chunk.metadata,
        "matched_queries": list(chunk.matched_queries),
        "retrieval_rank": chunk.retrieval_rank,
    }


def _state(data: dict[str, Any]) -> ConversationState:
    return ConversationState(
        summary=data.get("summary", ""),
        entities=dict(data.get("entities", {})),
        recent_resolved=tuple(data.get("recent_resolved", ())),
        open_threads=tuple(data.get("open_threads", ())),
        asked_questions=tuple(data.get("asked_questions", ())),
    )


def _followup(data: dict[str, Any]) -> ValidatedFollowup:
    return ValidatedFollowup(
        question=data["question"],
        chunks=[_chunk(item) for item in data.get("chunks", [])],
        score=data.get("score", 0.0),
        verdict=data.get("verdict", "keep"),
        checked_by_llm=data.get("checked_by_llm", False),
    )


def _plan(data: dict[str, Any]) -> QueryPlan:
    return QueryPlan(
        sub_questions=list(data.get("sub_questions", [])),
        degraded=data.get("degraded", False),
        proposed_count=data.get("proposed_count", 0),
        warnings=[_message(item) for item in data.get("warnings", [])],
    )


def _answer(data: dict[str, Any]) -> ConversationalAnswer:
    return ConversationalAnswer(
        answer=data.get("answer", ""),
        sources=[_chunk(item) for item in data.get("sources", [])],
        overflow_sources=[_chunk(item) for item in data.get("overflow_sources", [])],
        plan=_plan(data.get("plan", {})),
        follow_ups=[_followup(item) for item in data.get("follow_ups", [])],
        dropped_followups=[_followup(item) for item in data.get("dropped_followups", [])],
        evaluated_followups=[_followup(item) for item in data.get("evaluated_followups", [])],
        state=_state(data.get("state", {})),
        model_used=data.get("model_used"),
        aux_model_used=data.get("aux_model_used"),
        reranker_used=data.get("reranker_used"),
        timings=dict(data.get("timings", {})),
        token_usage=[
            StageTokenUsage(
                process=item["process"],
                model_id=item["model_id"],
                usage=_usage(item.get("usage")) or TokenUsage(),
            )
            for item in data.get("token_usage", [])
        ],
        prompt_traces=[
            StagePromptTrace(
                process=item["process"], prompt=item["prompt"], response=item["response"]
            )
            for item in data.get("prompt_traces", [])
        ],
        warnings=[_message(item) for item in data.get("warnings", [])],
        errors=[_message(item) for item in data.get("errors", [])],
    )


class HttpConversationalGeneration:
    """Client-side mirror of ``rag_engine.ConversationalGeneration`` over the backend stream.

    Iterate it (via ``st.write_stream``) to receive the grounded answer's tokens; the
    backend's ``{"progress": ...}`` frames fire ``progress_callback`` (the live status
    narration) and are not yielded. When iteration drains, ``answer`` holds the full
    ``ConversationalAnswer``. A network/backend failure lands a structured error in
    ``answer.errors`` instead of raising, so the page shows its normal error reply.
    """

    def __init__(
        self,
        run_dir: Path | str,
        question: str,
        state: Any,
        config: Any,
        *,
        history: Any = (),
        cached_chunks: Any | None = None,
        progress_callback: Callable[[LibraryMessage], None] | None = None,
        client: Any | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._question = question
        self._state = state
        self._config = config
        self._history = history
        self._cached_chunks = cached_chunks
        self._progress = progress_callback
        self._client = client
        self.answer: ConversationalAnswer | None = None

    def __iter__(self) -> Iterator[str]:
        base_url = get_settings().backend_url.rstrip("/")
        payload = {
            "run_dir": str(self._run_dir),
            "question": self._question,
            "state": _state_to_dict(self._state),
            "config": self._config.model_dump(mode="json"),
            "history": [{"role": turn.role, "content": turn.content} for turn in self._history],
            "cached_chunks": (
                [_chunk_to_dict(chunk) for chunk in self._cached_chunks]
                if self._cached_chunks is not None
                else None
            ),
        }
        poster = self._client or httpx
        try:
            with poster.stream(
                "POST",
                f"{base_url}/rag/conversational",
                json=payload,
                headers=_auth_headers(),
                timeout=_STREAM_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    frame = json.loads(line)
                    if "token" in frame:
                        yield frame["token"]
                    elif "progress" in frame and self._progress is not None:
                        self._progress(_message(frame["progress"]))
                    elif "error" in frame:
                        self.answer = ConversationalAnswer(
                            answer="", state=self._state, errors=[_message(frame["error"])]
                        )
                    elif "done" in frame:
                        self.answer = _answer(frame["done"])
        except Exception as exc:  # network / HTTP / parse failure → structured error reply
            self.answer = ConversationalAnswer(
                answer="",
                state=self._state,
                errors=[rag_messages.classify_generation_failure(f"backend request failed: {exc}")],
            )


def http_conversational(
    run_dir: Path | str,
    question: str,
    state: Any,
    config: Any,
    *,
    history: Any = (),
    cached_chunks: Any | None = None,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
    client: Any | None = None,
) -> HttpConversationalGeneration:
    """Stream a Step 5 turn from the backend ``POST /rag/conversational``."""
    return HttpConversationalGeneration(
        run_dir,
        question,
        state,
        config,
        history=history,
        cached_chunks=cached_chunks,
        progress_callback=progress_callback,
        client=client,
    )


# ── Crawl (Step 1) remote job ────────────────────────────────────────────────


def _stream_job_to_emit(
    endpoint: str,
    payload: dict[str, Any],
    *,
    emit: Callable[[Any], None],
    cancel_event: threading.Event,
    client: Any | None,
    cancel_poll_seconds: float,
) -> dict[str, Any]:
    """Drive a backend streaming job (crawl/index): relay ``event`` frames to *emit*, post
    ``/{endpoint}/{job_id}/cancel`` when *cancel_event* fires (never touching it, so the
    caller still decides completed-vs-cancelled), and return the final ``result`` dict. A
    network failure returns ``{"error": ...}``.
    """
    base_url = get_settings().backend_url.rstrip("/")
    poster = client or httpx
    result: dict[str, Any] = {}
    job_id: dict[str, str] = {}
    done = threading.Event()

    def watch_cancel() -> None:
        while not done.wait(cancel_poll_seconds):
            if cancel_event.is_set() and job_id.get("id"):
                # best-effort cancel: a failed POST must never crash the job worker.
                with contextlib.suppress(Exception):
                    poster.post(
                        f"{base_url}/{endpoint}/{job_id['id']}/cancel",
                        headers=_auth_headers(),
                        timeout=_TIMEOUT_SECONDS,
                    )
                return

    watcher = threading.Thread(target=watch_cancel, name=f"{endpoint}-cancel-watch", daemon=True)
    watcher.start()
    try:
        with poster.stream(
            "POST",
            f"{base_url}/{endpoint}",
            json=payload,
            headers=_auth_headers(),
            timeout=_STREAM_TIMEOUT_SECONDS,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                frame = json.loads(line)
                if "event" in frame:
                    emit(frame["event"])
                elif "job_id" in frame:
                    job_id["id"] = frame["job_id"]
                elif "result" in frame:
                    result = frame["result"]
    except Exception as exc:  # noqa: BLE001 - network/HTTP/parse failure → structured result
        result = {"error": f"backend request failed: {exc}"}
    finally:
        done.set()
    return result


def run_remote_crawl(
    crawler_config: Any,
    page_config: Any,
    output_base: Path | str,
    *,
    emit: Callable[[Any], None],
    cancel_event: threading.Event,
    activity_log_size: int = 10,
    client: Any | None = None,
    cancel_poll_seconds: float = _CANCEL_POLL_SECONDS,
) -> dict[str, Any]:
    """Drive a crawl on the backend ``POST /crawl``, relaying its events to *emit*.

    Returns the final ``result`` dict (page counts + output-dir name + any crawl error) so
    the caller builds its own terminal event with its own paths.
    """
    payload = {
        "output_base": str(output_base),
        "crawler_config": crawler_config.model_dump(mode="json"),
        "page_config": page_config.model_dump(mode="json"),
        "activity_log_size": activity_log_size,
    }
    return _stream_job_to_emit(
        "crawl",
        payload,
        emit=emit,
        cancel_event=cancel_event,
        client=client,
        cancel_poll_seconds=cancel_poll_seconds,
    )


def run_remote_index(
    config: Any,
    input_paths: Any,
    output_base: Path | str,
    *,
    emit: Callable[[Any], None],
    cancel_event: threading.Event,
    client: Any | None = None,
    cancel_poll_seconds: float = _CANCEL_POLL_SECONDS,
) -> dict[str, Any]:
    """Drive an index run on the backend ``POST /index``, relaying its events to *emit*.

    Sends the input paths + output base relative to the shared storage root; returns the
    final ``result`` dict (counts + output-dir name + success + warnings/errors) so the
    caller builds its own terminal event with its own paths.
    """
    payload = {
        "output_base": str(output_base),
        "input_paths": [str(path) for path in input_paths],
        "config": config.model_dump(mode="json"),
    }
    return _stream_job_to_emit(
        "index",
        payload,
        emit=emit,
        cancel_event=cancel_event,
        client=client,
        cancel_poll_seconds=cancel_poll_seconds,
    )
