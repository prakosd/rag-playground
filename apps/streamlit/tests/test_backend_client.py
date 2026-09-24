"""Tests for the optional HTTP backend client (BACKEND_MODE=http)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from rag_engine import RagConfig

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
            }
        ],
        "warnings": [],
        "errors": [{"code": "rag.no_context", "text": "none", "severity": "warning", "params": {}}],
    }
    client = _FakeClient(payload)

    result = backend_client.http_search("run", "q", RagConfig(top_k=3), client=client)

    assert result.chunks[0].source == "s.md"
    assert result.chunks[0].matched_queries == ("q1",)  # list rebuilt as a tuple
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
