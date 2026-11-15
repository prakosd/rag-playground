"""Tests for the optional HTTP backend client (BACKEND_MODE=http)."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from crawl4md import CrawlerConfig, PageConfig
from rag_engine import ChatTurn, ConversationalConfig, ConversationState, RagConfig, RetrievedChunk
from vector_indexer import IndexingConfig

from app_support import backend_client


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, json: dict[str, Any], timeout: float) -> _FakeResponse:
        self.calls.append((url, json))
        return _FakeResponse(self._payload)


class _BoomClient:
    def post(self, url: str, json: dict[str, Any], timeout: float) -> Any:
        raise RuntimeError("connection refused")


def test_http_search_rebuilds_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    payload = {
        "chunks": [
            {
                "text": "t",
                "source": "s.md",
                "score": 0.5,
                "metadata": {"a": "b"},
                "matched_queries": ["q1"],
                "retrieval_rank": 4,
            }
        ],
        "warnings": [],
        "errors": [{"code": "rag.no_context", "text": "none", "severity": "warning", "params": {}}],
    }
    client = _FakeClient(payload)

    result = backend_client.http_search("run", "q", RagConfig(top_k=3), client=client)

    assert result.chunks[0].source == "s.md"
    assert result.chunks[0].matched_queries == ("q1",)  # list rebuilt as a tuple
    assert result.chunks[0].retrieval_rank == 4  # passage number threaded across the backend
    assert result.errors[0].code == "rag.no_context"  # LibraryMessage rebuilt by code
    assert client.calls[0][0] == "http://x/rag/search"
    assert client.calls[0][1]["top_k"] == 3  # RagConfig threaded into the request


def test_http_search_degrades_to_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )

    result = backend_client.http_search("run", "q", RagConfig(), client=_BoomClient())

    assert result.chunks == []
    assert result.errors[0].code == "rag.retrieval_failed"  # structured, not a crash


class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        return iter(self._lines)


class _FakeStreamCtx:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __enter__(self) -> _FakeStreamResponse:
        return _FakeStreamResponse(self._lines)

    def __exit__(self, *exc: object) -> bool:
        return False


class _FakeStreamClient:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def stream(self, method: str, url: str, json: dict[str, Any], timeout: float) -> _FakeStreamCtx:
        self.calls.append((method, url, json))
        return _FakeStreamCtx(self._lines)


def test_http_generate_streams_tokens_and_captures_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    lines = [
        json.dumps({"token": "Hel"}),
        json.dumps({"token": "lo"}),
        json.dumps(
            {
                "done": True,
                "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                "model_used": "echo",
                "warnings": [
                    {"code": "rag.model_fallback_echo", "text": "f", "severity": "warning"}
                ],
            }
        ),
    ]
    client = _FakeStreamClient(lines)

    generation = backend_client.http_generate("ask", "bedrock:x", client=client)
    tokens = list(generation)

    assert tokens == ["Hel", "lo"]  # streamed piece by piece for st.write_stream
    assert generation.text == "Hello"
    assert generation.model_used == "echo"  # the backend's resolved model
    assert generation.usage.total_tokens == 3
    assert generation.warnings[0].code == "rag.model_fallback_echo"
    assert generation.error is None
    assert client.calls[0][1] == "http://x/rag/generate"
    assert client.calls[0][2] == {"prompt": "ask", "llm_model": "bedrock:x"}


def test_http_generate_surfaces_backend_error_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    lines = [
        json.dumps({"token": "partial"}),
        json.dumps(
            {"error": {"code": "rag.generation_failed", "text": "boom", "severity": "error"}}
        ),
    ]

    generation = backend_client.http_generate("ask", "echo", client=_FakeStreamClient(lines))
    tokens = list(generation)

    assert tokens == ["partial"]  # whatever streamed before the failure is still shown
    assert generation.error.code == "rag.generation_failed"  # rebuilt by code, not text


def test_http_generate_degrades_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )

    class _BoomStreamClient:
        def stream(self, *args: object, **kwargs: object) -> Any:
            raise RuntimeError("connection refused")

    generation = backend_client.http_generate("ask", "echo", client=_BoomStreamClient())
    tokens = list(generation)

    assert tokens == []
    assert generation.error.code == "rag.generation_failed"  # structured, not a crash


def test_http_conversational_streams_progress_tokens_and_rebuilds_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    done = {
        "answer": "Hello world",
        "sources": [
            {"text": "t", "source": "s.md", "score": 0.5, "metadata": {}, "retrieval_rank": 1}
        ],
        "plan": {"sub_questions": ["q1"], "degraded": False, "proposed_count": 1, "warnings": []},
        "follow_ups": [
            {
                "question": "more?",
                "chunks": [],
                "score": 0.6,
                "verdict": "keep",
                "checked_by_llm": True,
            }
        ],
        "state": {"summary": "updated", "recent_resolved": ["q1"]},
        "model_used": "echo",
        "aux_model_used": "aux",
        "reranker_used": "llm",
        "timings": {"answer": 1.5},
        "overflow_sources": [
            {"text": "o", "source": "over.md", "score": 0.2, "metadata": {}, "retrieval_rank": 9}
        ],
        "dropped_followups": [
            {
                "question": "no?",
                "chunks": [],
                "score": 0.3,
                "verdict": "drop",
                "checked_by_llm": True,
            }
        ],
        "evaluated_followups": [
            {
                "question": "more?",
                "chunks": [],
                "score": 0.6,
                "verdict": "keep",
                "checked_by_llm": True,
            },
            {
                "question": "no?",
                "chunks": [],
                "score": 0.3,
                "verdict": "drop",
                "checked_by_llm": True,
            },
        ],
        "token_usage": [
            {
                "process": "answer",
                "model_id": "echo",
                "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            }
        ],
        "prompt_traces": [{"process": "answer", "prompt": "P", "response": "R"}],
    }
    lines = [
        json.dumps({"progress": {"code": "rag.progress.answer", "text": "…", "severity": "info"}}),
        json.dumps({"token": "Hello"}),
        json.dumps({"token": " world"}),
        json.dumps({"done": done}),
    ]
    client = _FakeStreamClient(lines)
    progress_seen: list[object] = []

    generation = backend_client.http_conversational(
        "idx",
        "what now?",
        ConversationState(summary="prior"),
        ConversationalConfig(),
        history=[ChatTurn(role="user", content="hi")],
        cached_chunks=[RetrievedChunk(text="c", source="cached.md", score=0.4, metadata={})],
        progress_callback=lambda message: progress_seen.append(message.code),
        client=client,
    )
    tokens = list(generation)

    assert tokens == ["Hello", " world"]  # only answer tokens reach st.write_stream
    assert progress_seen == ["rag.progress.answer"]  # progress fires the status, not yielded
    answer = generation.answer
    assert answer.answer == "Hello world"
    assert answer.sources[0].source == "s.md"  # nested RetrievedChunk rebuilt
    assert answer.plan.sub_questions == ["q1"]
    assert answer.follow_ups[0].question == "more?"
    assert answer.state.recent_resolved == ("q1",)  # list rebuilt as a tuple
    assert answer.token_usage[0].usage.total_tokens == 3
    assert answer.prompt_traces[0].prompt == "P"
    # the lower-traffic Inspect/Token fields a wrong serialization key would silently drop
    assert answer.overflow_sources[0].source == "over.md"
    assert answer.dropped_followups[0].verdict == "drop"
    assert [f.question for f in answer.evaluated_followups] == ["more?", "no?"]
    assert answer.aux_model_used == "aux"
    assert answer.reranker_used == "llm"
    assert answer.timings == {"answer": 1.5}
    # the request serialized the prior state + history + config + cached chunks
    _method, url, body = client.calls[0]
    assert url == "http://x/rag/conversational"
    assert body["state"]["summary"] == "prior"
    assert body["history"] == [{"role": "user", "content": "hi"}]
    assert isinstance(body["config"], dict)
    assert body["cached_chunks"][0]["source"] == "cached.md"  # follow-up-cache reuse path


def test_http_conversational_degrades_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )

    class _BoomStreamClient:
        def stream(self, *args: object, **kwargs: object) -> Any:
            raise RuntimeError("connection refused")

    generation = backend_client.http_conversational(
        "idx", "q", ConversationState(), ConversationalConfig(), client=_BoomStreamClient()
    )
    tokens = list(generation)

    assert tokens == []
    assert generation.answer.errors[0].code == "rag.generation_failed"  # structured reply


def _crawler_config() -> CrawlerConfig:
    return CrawlerConfig(urls=["https://example.com"])


def test_run_remote_crawl_relays_events_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    lines = [
        json.dumps({"job_id": "J"}),
        json.dumps({"event": {"event": "progress", "processed_pages": 2}}),
        json.dumps({"result": {"successful_pages": 2, "output_dir_name": "2026-01-01"}}),
    ]
    client = _FakeStreamClient(lines)
    events: list[object] = []

    result = backend_client.run_remote_crawl(
        _crawler_config(),
        PageConfig(),
        "session_x/crawl_01",
        emit=events.append,
        cancel_event=threading.Event(),
        client=client,
        cancel_poll_seconds=5.0,
    )

    assert events == [{"event": "progress", "processed_pages": 2}]  # relayed to the app callback
    assert result == {"successful_pages": 2, "output_dir_name": "2026-01-01"}
    _method, url, body = client.calls[0]
    assert url == "http://x/crawl"
    assert body["output_base"] == "session_x/crawl_01"
    assert body["crawler_config"]["urls"] == ["https://example.com"]  # config serialized


def test_run_remote_crawl_posts_cancel_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    cancel_event = threading.Event()
    cancel_posted = threading.Event()
    posted_urls: list[str] = []

    class _Resp:
        def raise_for_status(self) -> None: ...

        def iter_lines(self):
            yield json.dumps({"job_id": "J"})
            cancel_event.set()  # the user cancels mid-crawl
            assert cancel_posted.wait(timeout=3)  # block until the watcher posts cancel
            yield json.dumps({"result": {"cancelled": True}})

    class _Ctx:
        def __enter__(self) -> _Resp:
            return _Resp()

        def __exit__(self, *exc: object) -> bool:
            return False

    class _CancelClient:
        def stream(self, *args: object, **kwargs: object) -> _Ctx:
            return _Ctx()

        def post(self, url: str, timeout: float | None = None) -> Any:
            posted_urls.append(url)
            cancel_posted.set()
            return SimpleNamespace(raise_for_status=lambda: None)

    result = backend_client.run_remote_crawl(
        _crawler_config(),
        PageConfig(),
        "s/c",
        emit=lambda event: None,
        cancel_event=cancel_event,
        client=_CancelClient(),
        cancel_poll_seconds=0.01,
    )

    assert posted_urls == ["http://x/crawl/J/cancel"]  # cancel propagated to the backend job
    assert result == {"cancelled": True}


def test_run_remote_crawl_degrades_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )

    class _BoomClient:
        def stream(self, *args: object, **kwargs: object) -> Any:
            raise RuntimeError("refused")

    result = backend_client.run_remote_crawl(
        _crawler_config(),
        PageConfig(),
        "s/c",
        emit=lambda event: None,
        cancel_event=threading.Event(),
        client=_BoomClient(),
        cancel_poll_seconds=5.0,
    )

    assert "error" in result  # structured, not a crash


def test_run_remote_index_relays_events_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backend_client, "get_settings", lambda: SimpleNamespace(backend_url="http://x")
    )
    lines = [
        json.dumps({"job_id": "J"}),
        json.dumps({"event": {"event": "progress", "indexed_file_count": 1}}),
        json.dumps(
            {"result": {"success": True, "output_dir_name": "2026", "indexed_chunk_count": 5}}
        ),
    ]
    client = _FakeStreamClient(lines)
    events: list[object] = []

    result = backend_client.run_remote_index(
        IndexingConfig(),
        ["session_x/crawl_01/final"],
        "session_x/vector_01",
        emit=events.append,
        cancel_event=threading.Event(),
        client=client,
        cancel_poll_seconds=5.0,
    )

    assert events == [{"event": "progress", "indexed_file_count": 1}]  # relayed to the app callback
    assert result == {"success": True, "output_dir_name": "2026", "indexed_chunk_count": 5}
    _method, url, body = client.calls[0]
    assert url == "http://x/index"  # reuses the shared streaming/cancel helper on /index
    assert body["output_base"] == "session_x/vector_01"
    assert body["input_paths"] == ["session_x/crawl_01/final"]  # sent relative to the sessions root
    assert isinstance(body["config"], dict)
