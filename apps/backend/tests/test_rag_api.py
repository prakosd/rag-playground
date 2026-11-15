"""Tests for the FastAPI backend RAG routes (mocked library calls, no network)."""

from __future__ import annotations

import asyncio
import gc
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from rag_engine import (
    ConversationalAnswer,
    ConversationalConfig,
    ConversationState,
    QueryPlan,
    RagAnswer,
    RetrievalResult,
    RetrievedChunk,
    StagePromptTrace,
    StageTokenUsage,
    ValidatedFollowup,
)
from rag_engine import messages as rag_messages
from rag_engine.models import TokenUsage

from app_backend import create_app, rag_api


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        text="body", source="doc.md", score=0.87, metadata={"k": "v"}, retrieval_rank=2
    )


def test_health_ok(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_search_returns_chunks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_retrieve(run_dir: object, query: str, config: object, **_: object) -> RetrievalResult:
        assert query == "hello"
        assert config.top_k == 3  # the request override is threaded into RagConfig
        return RetrievalResult(chunks=[_chunk()])

    monkeypatch.setattr(rag_api, "retrieve", fake_retrieve)

    resp = client.post("/rag/search", json={"run_dir": "vec/idx", "query": "hello", "top_k": 3})

    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks"][0]["source"] == "doc.md"
    assert body["chunks"][0]["matched_queries"] == []
    assert body["chunks"][0]["retrieval_rank"] == 2
    assert body["errors"] == []


def test_search_surfaces_library_errors_as_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_retrieve(run_dir: object, query: str, config: object, **_: object) -> RetrievalResult:
        return RetrievalResult(errors=[rag_messages.index_not_found("x")])

    monkeypatch.setattr(rag_api, "retrieve", fake_retrieve)

    body = client.post("/rag/search", json={"run_dir": "a", "query": "q"}).json()

    assert body["errors"][0]["code"] == "rag.index_not_found"  # localizable by code, not text


def test_answer_returns_answer_and_sources(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_answer(run_dir: object, question: str, config: object, **_: object) -> RagAnswer:
        return RagAnswer(answer="42", sources=[_chunk()], model_used="echo")

    monkeypatch.setattr(rag_api, "answer_question", fake_answer)

    body = client.post("/rag/answer", json={"run_dir": "a", "question": "q?"}).json()

    assert body["answer"] == "42"
    assert body["model_used"] == "echo"
    assert body["sources"][0]["source"] == "doc.md"


def test_search_rejects_path_traversal(client: TestClient) -> None:
    resp = client.post("/rag/search", json={"run_dir": "../../etc", "query": "q"})
    assert resp.status_code == 400  # containment guard rejects escaping the artifacts root


def _ndjson(resp: object) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line]


def test_generate_streams_tokens_then_done_frame(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _FakeGen:
        usage = TokenUsage(input_tokens=3, output_tokens=5, total_tokens=8)

        def __iter__(self):
            yield "Hello"
            yield " world"

    def fake_resolve(model_id: str, **_: object):
        captured["model_id"] = model_id
        warning = rag_messages.model_fallback_echo(requested_model=model_id, detail="no creds")
        return SimpleNamespace(model=object(), model_id="echo"), [warning]

    def fake_stream(model: object, prompt: str, *, system_directive: str = "") -> _FakeGen:
        captured["prompt"] = prompt
        captured["directive"] = system_directive
        return _FakeGen()

    monkeypatch.setattr(rag_api, "resolve_chat_model", fake_resolve)
    monkeypatch.setattr(rag_api, "thinking_disabled_system_directive", lambda model_id: "/no_think")
    monkeypatch.setattr(rag_api, "stream_prompt", fake_stream)

    resp = client.post("/rag/generate", json={"prompt": "ask me", "llm_model": "bedrock:x"})

    assert resp.status_code == 200
    frames = _ndjson(resp)
    assert [f["token"] for f in frames if "token" in f] == ["Hello", " world"]
    done = frames[-1]
    assert done["done"] is True
    assert done["model_used"] == "echo"  # the backend resolved it (echo fallback)
    assert done["usage"] == {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}
    assert done["warnings"][0]["code"]  # the echo-fallback warning, localizable by code
    # the raw prompt + resolved directive are threaded into stream_prompt
    assert captured == {"model_id": "bedrock:x", "prompt": "ask me", "directive": "/no_think"}


def test_generate_emits_error_frame_on_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _BoomGen:
        usage = None

        def __iter__(self):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(
        rag_api,
        "resolve_chat_model",
        lambda m, **_: (SimpleNamespace(model=object(), model_id="echo"), []),
    )
    monkeypatch.setattr(rag_api, "thinking_disabled_system_directive", lambda m: "")
    monkeypatch.setattr(rag_api, "stream_prompt", lambda *a, **k: _BoomGen())

    frames = _ndjson(client.post("/rag/generate", json={"prompt": "x", "llm_model": "echo"}))

    assert "error" in frames[-1]
    assert frames[-1]["error"]["code"]  # a structured, localizable generation error


def test_generate_closes_model_stream_on_client_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = threading.Event()

    class _Gen:
        usage = None

        def __iter__(self):
            try:
                yield "Hello"
                yield " world"
            finally:
                closed.set()  # the underlying model stream was torn down

    monkeypatch.setattr(
        rag_api,
        "resolve_chat_model",
        lambda m, **_: (SimpleNamespace(model=object(), model_id="echo"), []),
    )
    monkeypatch.setattr(rag_api, "thinking_disabled_system_directive", lambda m: "")
    monkeypatch.setattr(rag_api, "stream_prompt", lambda *a, **k: _Gen())

    response = rag_api.generate(rag_api.GenerateRequest(prompt="x", llm_model="echo"))

    async def drive() -> None:
        body = response.body_iterator
        await body.__anext__()  # first token frame, mid-stream
        await body.aclose()  # the client goes away before the stream finishes

    asyncio.run(drive())
    gc.collect()

    assert closed.is_set()  # the finally ran → no lingering model stream on disconnect


def test_conversational_streams_progress_tokens_then_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_stream(run_dir, question, state, config, *, history, cached_chunks, progress_callback):
        captured["question"] = question
        captured["state_summary"] = state.summary
        captured["history"] = [(t.role, t.content) for t in history]
        captured["cached"] = (
            [chunk.source for chunk in cached_chunks] if cached_chunks is not None else None
        )
        progress_callback(rag_messages.progress_answer())  # prepare-time stage label

        kept = ValidatedFollowup(
            question="more?", chunks=[_chunk()], score=0.6, verdict="keep", checked_by_llm=True
        )
        dropped = ValidatedFollowup(question="no?", score=0.3, verdict="drop", checked_by_llm=True)
        answer = ConversationalAnswer(
            answer="Hello world",
            sources=[_chunk()],
            overflow_sources=[_chunk()],
            plan=QueryPlan(sub_questions=["q1", "q2"], degraded=False, proposed_count=2),
            follow_ups=[kept],
            dropped_followups=[dropped],
            evaluated_followups=[kept, dropped],
            state=ConversationState(summary="updated", recent_resolved=("q1",)),
            model_used="echo",
            aux_model_used="aux",
            reranker_used="llm",
            timings={"answer": 1.5},
            token_usage=[
                StageTokenUsage(process="answer", model_id="echo", usage=TokenUsage(1, 2, 3))
            ],
            prompt_traces=[StagePromptTrace(process="answer", prompt="P", response="R")],
        )

        class _Gen:
            def __init__(self) -> None:
                self.answer = answer

            def __iter__(self):
                progress_callback(rag_messages.progress_answer())  # answer-time stage label
                yield "Hello"
                yield " world"
                progress_callback(rag_messages.progress_answer())  # state stage, after last token

        return _Gen()

    monkeypatch.setattr(rag_api, "conversational_answer_stream", fake_stream)

    resp = client.post(
        "/rag/conversational",
        json={
            "run_dir": "idx",
            "question": "what now?",
            "state": {"summary": "prior"},
            "config": ConversationalConfig().model_dump(mode="json"),
            "history": [{"role": "user", "content": "hi"}],
            "cached_chunks": [
                {
                    "text": "c",
                    "source": "cached.md",
                    "score": 0.4,
                    "metadata": {},
                    "retrieval_rank": 0,
                }
            ],
        },
    )

    assert resp.status_code == 200
    frames = _ndjson(resp)
    # Frame order locks the buffer+flush interleaving: progress before tokens, a progress
    # after the last token (state stage), and the full answer strictly last.
    assert [next(iter(frame)) for frame in frames] == [
        "progress",
        "progress",
        "token",
        "token",
        "progress",
        "done",
    ]
    done = frames[-1]["done"]
    assert done["answer"] == "Hello world"
    assert done["sources"][0]["source"] == "doc.md"
    assert done["overflow_sources"][0]["source"] == "doc.md"  # display-only pool survives
    assert done["plan"]["sub_questions"] == ["q1", "q2"]
    assert done["follow_ups"][0]["question"] == "more?"
    assert done["follow_ups"][0]["chunks"][0]["source"] == "doc.md"  # nested chunks survive
    assert done["dropped_followups"][0]["verdict"] == "drop"
    assert [f["question"] for f in done["evaluated_followups"]] == ["more?", "no?"]
    assert done["state"]["summary"] == "updated"
    assert done["state"]["recent_resolved"] == ["q1"]  # tuple serialized as a list
    assert done["aux_model_used"] == "aux"
    assert done["reranker_used"] == "llm"
    assert done["timings"] == {"answer": 1.5}
    assert done["token_usage"][0]["usage"]["total_tokens"] == 3
    assert done["prompt_traces"][0] == {"process": "answer", "prompt": "P", "response": "R"}
    # the backend reconstructed the inputs the library saw (state + history + cached round-tripped)
    assert captured == {
        "question": "what now?",
        "state_summary": "prior",
        "history": [("user", "hi")],
        "cached": ["cached.md"],
    }


def test_conversational_emits_error_frame_on_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_stream(run_dir, question, state, config, *, history, cached_chunks, progress_callback):
        class _BoomGen:
            answer = None

            def __iter__(self):
                raise RuntimeError("stream died")

        return _BoomGen()

    monkeypatch.setattr(rag_api, "conversational_answer_stream", fake_stream)

    frames = _ndjson(
        client.post(
            "/rag/conversational",
            json={
                "run_dir": "idx",
                "question": "q",
                "config": ConversationalConfig().model_dump(mode="json"),
            },
        )
    )

    assert "error" in frames[-1]
    assert frames[-1]["error"]["code"]
