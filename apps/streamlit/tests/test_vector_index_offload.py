"""Tests for the BACKEND_MODE=http index offload (mocked backend client, no network)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from vector_indexer import IndexingConfig

from app_support.vector_index import vector_index_jobs


def _call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_remote,
) -> tuple[list[dict], Path]:
    monkeypatch.setattr(vector_index_jobs, "run_remote_index", fake_remote)
    events: list[dict] = []
    output_base = tmp_path / "session_x" / "vector_01"
    vector_index_jobs._run_index_via_backend(
        events.append,
        config=IndexingConfig(),
        input_paths=[str(tmp_path / "session_x" / "crawl_01" / "final")],
        output_base=output_base,
        sessions_root=tmp_path,
        cancel_event=threading.Event(),
    )
    return events, output_base


def test_run_index_via_backend_relays_events_then_completed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_remote(config, input_paths, output_base, *, emit, cancel_event):
        captured["inputs"] = list(input_paths)
        captured["output_base"] = output_base
        emit({"event": "progress", "indexed_file_count": 1})
        return {
            "success": True,
            "output_dir_name": "2026-01-01",
            "indexed_file_count": 3,
            "indexed_chunk_count": 42,
            "skipped_file_count": 1,
            "warnings": [],
            "errors": [],
            "cancelled": False,
        }

    events, output_base = _call(monkeypatch, tmp_path, fake_remote)

    assert captured["inputs"] == ["session_x/crawl_01/final"]  # sent relative to the sessions root
    assert captured["output_base"] == "session_x/vector_01"
    assert events[0] == {"event": "progress", "indexed_file_count": 1}  # backend progress relayed
    terminal = events[-1]
    assert terminal["event"] == "completed"
    assert terminal["indexed_chunk_count"] == 42
    assert terminal["output_dir"] == str(output_base / "2026-01-01")  # frontend's own path


def test_run_index_via_backend_emits_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_remote(*args, emit, **kwargs):
        return {
            "success": False,
            "cancelled": True,
            "output_dir_name": "d",
            "indexed_file_count": 0,
            "indexed_chunk_count": 0,
            "skipped_file_count": 0,
            "warnings": [],
            "errors": [],
        }

    assert _call(monkeypatch, tmp_path, fake_remote)[0][-1]["event"] == "cancelled"


def test_run_index_via_backend_emits_failed_on_backend_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events, _ = _call(
        monkeypatch, tmp_path, lambda *a, emit, **k: {"error": "embeddings unavailable"}
    )

    assert events[-1]["event"] == "failed"
    assert events[-1]["errors"][0]["code"]  # a classified, localizable embedding failure


def test_run_index_via_backend_unsuccessful_result_is_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_remote(*args, emit, **kwargs):
        return {
            "success": False,
            "cancelled": False,
            "output_dir_name": "d",
            "indexed_file_count": 0,
            "indexed_chunk_count": 0,
            "skipped_file_count": 2,
            "warnings": [],
            "errors": [{"code": "vector.embedding_unavailable", "text": "x", "severity": "error"}],
        }

    events, _ = _call(monkeypatch, tmp_path, fake_remote)

    assert events[-1]["event"] == "failed"
    assert events[-1]["errors"] == [
        {"code": "vector.embedding_unavailable", "text": "x", "severity": "error"}
    ]  # the library's own errors pass through unchanged
