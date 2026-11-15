"""Tests for the BACKEND_MODE=http crawl offload (mocked backend client, no network)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from crawl4md import CrawlerConfig, PageConfig

from app_support.crawl import crawl_jobs


def _config() -> CrawlerConfig:
    return CrawlerConfig(urls=["https://example.com"])


def _call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_remote,
    *,
    output_base: Path | None = None,
) -> list[dict]:
    monkeypatch.setattr(crawl_jobs, "run_remote_crawl", fake_remote)
    events: list[dict] = []
    crawl_jobs._run_crawl_via_backend(
        events.append,
        session_id="x",
        crawl_id="01",
        crawler_config=_config(),
        page_config=PageConfig(),
        output_base=output_base or (tmp_path / "s" / "c"),
        sessions_root=tmp_path,
        cancel_event=threading.Event(),
        activity_log_size=10,
    )
    return events


def test_run_crawl_via_backend_relays_events_then_completed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_remote(
        crawler_config, page_config, output_base, *, emit, cancel_event, activity_log_size
    ):
        captured["output_base"] = output_base
        emit({"event": "progress", "processed_pages": 1})
        return {
            "processed_pages": 3,
            "successful_pages": 2,
            "failed_pages": 1,
            "output_dir_name": "2026-01-01_00-00-00",
            "crawl_error": None,
            "cancelled": False,
        }

    output_base = tmp_path / "session_x" / "crawl_01"
    events = _call(monkeypatch, tmp_path, fake_remote, output_base=output_base)

    assert captured["output_base"] == "session_x/crawl_01"  # sent relative to the sessions root
    assert events[0] == {"event": "progress", "processed_pages": 1}  # backend progress relayed
    terminal = events[-1]
    assert terminal["event"] == "completed"
    assert terminal["successful_pages"] == 2
    assert terminal["output_dir"] == str(output_base / "2026-01-01_00-00-00")  # frontend's own path


def test_run_crawl_via_backend_emits_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_remote(*args, emit, **kwargs):
        return {
            "processed_pages": 1,
            "successful_pages": 1,
            "failed_pages": 0,
            "output_dir_name": "d",
            "crawl_error": None,
            "cancelled": True,
        }

    assert _call(monkeypatch, tmp_path, fake_remote)[-1]["event"] == "cancelled"


def test_run_crawl_via_backend_emits_failed_on_backend_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = _call(monkeypatch, tmp_path, lambda *a, emit, **k: {"error": "backend unreachable"})

    assert events[-1]["event"] == "failed"
    assert events[-1]["error_code"]  # a classified, localizable error (not a raw string)


def test_run_crawl_via_backend_failed_crawl_error_keeps_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A mid-run crawl_error from the backend reports failure but keeps the partial output dir.
    def fake_remote(*args, emit, **kwargs):
        return {
            "processed_pages": 2,
            "successful_pages": 1,
            "failed_pages": 1,
            "output_dir_name": "d",
            "crawl_error": "WAF blocked",
            "cancelled": False,
        }

    output_base = tmp_path / "s" / "c"
    terminal = _call(monkeypatch, tmp_path, fake_remote, output_base=output_base)[-1]

    assert terminal["event"] == "failed"
    assert terminal["output_dir"] == str(output_base / "d")  # partial output preserved


def test_emit_crawl_terminal_completed_shape() -> None:
    # The shared helper both paths use: a clean run emits a "completed" event with counts,
    # the output dir, the limit, and the cleared concurrent-progress fields.
    events: list[dict] = []
    crawl_jobs._emit_crawl_terminal(
        events.append,
        session_id="s",
        crawl_id="c",
        crawler_config=_config(),
        output_dir="/out/dir",
        processed_pages=5,
        successful_pages=4,
        failed_pages=1,
        crawl_error=None,
        cancelled=False,
    )
    event = events[0]
    assert event["event"] == "completed"
    assert event["output_dir"] == "/out/dir"
    assert (event["processed_pages"], event["successful_pages"], event["failed_pages"]) == (5, 4, 1)
    assert event["limit"] == _config().limit
    assert event["current_url"] == ""  # cleared concurrent-progress fields are present


def test_emit_crawl_terminal_crawl_error_is_failed_with_output() -> None:
    events: list[dict] = []
    crawl_jobs._emit_crawl_terminal(
        events.append,
        session_id="s",
        crawl_id="c",
        crawler_config=_config(),
        output_dir="/out",
        processed_pages=2,
        successful_pages=1,
        failed_pages=1,
        crawl_error="boom",
        cancelled=False,
    )
    event = events[0]
    assert event["event"] == "failed"
    assert event["output_dir"] == "/out"  # a mid-run error keeps the partial output
    assert event["error_code"]


def test_emit_crawl_failed_is_minimal() -> None:
    events: list[dict] = []
    crawl_jobs._emit_crawl_failed(
        events.append, session_id="s", crawl_id="c", crawler_config=_config(), error="kaboom"
    )
    event = events[0]
    assert event["event"] == "failed"
    assert "output_dir" not in event  # an unexpected failure has no partial-output fields
    assert event["error_code"]
    assert event["limit"] == _config().limit
