"""Tests for the backend index-job routes (mocked indexer — no model downloads)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from vector_indexer import IndexingConfig

from app_backend import create_app, job_stream


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _ndjson(resp: object) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line]


def _config() -> dict:
    return IndexingConfig().model_dump(mode="json")


def test_index_streams_job_id_progress_then_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _FakeIndexer:
        def __init__(self, *args, **kwargs) -> None: ...

        def run(self, config, inputs, output_base, *, progress_callback=None, should_cancel=None):
            captured["inputs"] = list(inputs)
            progress_callback({"indexed_file_count": 1})
            return SimpleNamespace(
                success=True,
                output_dir=Path(output_base) / "2026-01-01_00-00-00",
                indexed_file_count=3,
                indexed_chunk_count=42,
                skipped_file_count=1,
                warnings=[],
                errors=[],
            )

    monkeypatch.setattr("vector_indexer.VectorIndexer", _FakeIndexer)

    resp = client.post(
        "/index",
        json={
            "output_base": "session_x/vector_01",
            "input_paths": ["session_x/crawl_01/final"],
            "config": _config(),
        },
    )

    assert resp.status_code == 200
    frames = _ndjson(resp)
    assert "job_id" in frames[0]
    assert frames[1] == {"event": {"event": "progress", "indexed_file_count": 1}}  # relayed
    result = frames[-1]["result"]
    assert result["success"] is True
    assert result["output_dir_name"] == "2026-01-01_00-00-00"  # frontend joins it to its base
    assert result["indexed_file_count"] == 3
    assert result["indexed_chunk_count"] == 42
    assert result["skipped_file_count"] == 1
    assert result["cancelled"] is False
    # input paths were resolved under the artifacts root (absolute, ending with the relative)
    assert captured["inputs"][0].endswith("session_x/crawl_01/final")
    assert job_stream._CANCEL_EVENTS == {}  # cancel entry pruned when the stream ends


def test_index_rejects_path_traversal_in_inputs(client: TestClient) -> None:
    resp = client.post(
        "/index",
        json={"output_base": "s/v", "input_paths": ["../../etc/passwd"], "config": {}},
    )
    assert resp.status_code == 400  # each input path is containment-checked


def test_index_rejects_path_traversal_in_output_base(client: TestClient) -> None:
    resp = client.post("/index", json={"output_base": "../../etc", "input_paths": [], "config": {}})
    assert resp.status_code == 400  # the output base is containment-checked too


def test_index_worker_error_becomes_result_frame(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _BoomIndexer:
        def __init__(self, *args, **kwargs) -> None: ...

        def run(self, *args, **kwargs):
            raise RuntimeError("embedding provider unavailable")

    monkeypatch.setattr("vector_indexer.VectorIndexer", _BoomIndexer)

    frames = _ndjson(
        client.post("/index", json={"output_base": "s/v", "input_paths": [], "config": _config()})
    )

    assert "embedding provider unavailable" in frames[-1]["result"]["error"]  # not a 500


def test_index_cancel_unknown_job_is_false(client: TestClient) -> None:
    assert client.post("/index/nope/cancel").json() == {"cancelled": False}
