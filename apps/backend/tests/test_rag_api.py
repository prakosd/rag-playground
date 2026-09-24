"""Tests for the FastAPI backend RAG routes (mocked library calls, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rag_engine import RagAnswer, RetrievalResult, RetrievedChunk
from rag_engine import messages as rag_messages

from app_backend import create_app, rag_api


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(text="body", source="doc.md", score=0.87, metadata={"k": "v"})


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
