"""Tests for the backend crawl-job routes (mocked crawler — no browser or network)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from crawl4md import CrawlerConfig
from fastapi.testclient import TestClient

from app_backend import create_app, job_stream


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _ndjson(resp: object) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line]


def _config() -> dict:
    return CrawlerConfig(urls=["https://example.com"]).model_dump(mode="json")


def test_crawl_streams_job_id_events_then_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeCrawler:
        def __init__(
            self, config, page_config=None, *, output_base=None, progress_callback=None, **_
        ):
            self._progress = progress_callback
            self.output_dir = Path(output_base) / "2026-01-01_00-00-00"
            self.crawl_error = None

        def crawl(self):
            self._progress({"event": "progress", "processed_pages": 1})
            return [SimpleNamespace(success=True), SimpleNamespace(success=False)]

    monkeypatch.setattr("crawl4md.crawler.SiteCrawler", _FakeCrawler)

    resp = client.post(
        "/crawl",
        json={"output_base": "session_x/crawl_01", "crawler_config": _config(), "page_config": {}},
    )

    assert resp.status_code == 200
    frames = _ndjson(resp)
    assert "job_id" in frames[0]  # first frame carries the id used to cancel
    assert frames[1] == {"event": {"event": "progress", "processed_pages": 1}}  # relayed verbatim
    result = frames[-1]["result"]
    assert result["processed_pages"] == 2
    assert result["successful_pages"] == 1
    assert result["failed_pages"] == 1
    assert result["output_dir_name"] == "2026-01-01_00-00-00"  # frontend joins it to its own base
    assert result["crawl_error"] is None
    assert result["cancelled"] is False
    assert job_stream._CANCEL_EVENTS == {}  # the job's cancel entry is pruned when the stream ends


def test_crawl_rejects_path_traversal(client: TestClient) -> None:
    resp = client.post("/crawl", json={"output_base": "../../etc", "crawler_config": {}})
    assert resp.status_code == 400  # containment guard rejects escaping the artifacts root


def test_crawl_worker_error_becomes_result_frame(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _BoomCrawler:
        def __init__(self, *args, **kwargs) -> None: ...

        def crawl(self):
            raise RuntimeError("browser crashed")

    monkeypatch.setattr("crawl4md.crawler.SiteCrawler", _BoomCrawler)

    frames = _ndjson(
        client.post("/crawl", json={"output_base": "s/c", "crawler_config": _config()})
    )

    assert frames[-1]["result"]["error"] == "browser crashed"  # worker error, not a 500


def test_crawl_cancel_sets_the_event(client: TestClient) -> None:
    event = threading.Event()
    job_stream._CANCEL_EVENTS["job123"] = event
    try:
        assert client.post("/crawl/job123/cancel").json() == {"cancelled": True}
        assert event.is_set()  # cooperative cancel flag flipped for the running crawl
    finally:
        job_stream._CANCEL_EVENTS.pop("job123", None)


def test_crawl_cancel_unknown_job_is_false(client: TestClient) -> None:
    assert client.post("/crawl/nope/cancel").json() == {"cancelled": False}
