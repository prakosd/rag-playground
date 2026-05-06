from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from threading import Event, Thread

import pytest
from pydantic import ValidationError

from crawl4md_streamlit.support import (
    CrawlJob,
    build_configs,
    cleanup_old_sessions,
    cleanup_old_sessions_with_lock,
    crawl_output_base,
    drain_events,
    estimate_progress,
    generate_crawl_id,
    generate_safe_id,
    list_generated_files,
    prepare_crawl_output_base,
    prepare_session_dir,
    read_recent_lines,
    request_cancel,
    session_dir,
    start_crawl_job,
    start_resume_job,
    validate_safe_id,
)


def test_generate_safe_id_uses_path_safe_characters() -> None:
    safe_id = generate_safe_id()

    assert safe_id
    assert validate_safe_id(safe_id) == safe_id


def test_session_and_crawl_dirs_are_prefixed(tmp_path: Path) -> None:
    session_path = session_dir(tmp_path, "abc123")
    crawl_path = crawl_output_base(tmp_path, "abc123", "run_123")

    assert session_path == tmp_path / "session_abc123"
    assert crawl_path == tmp_path / "session_abc123" / "crawl_run_123"


def test_validate_safe_id_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        validate_safe_id("../secret")


def test_prepare_crawl_output_base_creates_unique_folder(tmp_path: Path) -> None:
    path = prepare_crawl_output_base(tmp_path, "abc123", "run_123")

    assert path.is_dir()
    with pytest.raises(FileExistsError):
        prepare_crawl_output_base(tmp_path, "abc123", "run_123")


def test_estimate_progress_uses_limit_and_completion() -> None:
    estimate = estimate_progress(3, 10)
    complete = estimate_progress(3, 10, is_finished=True)

    assert estimate.fraction == 0.3
    assert estimate.percent == 30
    assert "Estimated" in estimate.label
    assert complete.fraction == 1.0
    assert complete.percent == 100


def test_list_generated_files_stays_inside_session_root(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    output_path = prepare_crawl_output_base(tmp_path, "abc123", "run_123")
    generated = output_path / "final" / "sorted_success_content_001.md"
    generated.parent.mkdir()
    generated.write_text("hello", encoding="utf-8")
    hidden = output_path / ".cleanup.lock"
    hidden.write_text("lock", encoding="utf-8")

    files = list_generated_files(session_path, output_path, download_limit_bytes=10)

    assert [file.relative_path for file in files] == [
        "crawl_run_123/final/sorted_success_content_001.md"
    ]
    assert files[0].download_allowed is True


def test_list_generated_files_accepts_relative_session_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    sessions_root = Path("outputs") / "streamlit_sessions"
    session_path = prepare_session_dir(sessions_root, "abc123")
    output_path = prepare_crawl_output_base(sessions_root, "abc123", "run_123")
    generated = output_path / "session.jsonl"
    generated.write_text("{}\n", encoding="utf-8")

    files = list_generated_files(session_path, output_path)

    assert [file.relative_path for file in files] == ["crawl_run_123/session.jsonl"]


def test_list_generated_files_rejects_sibling_session(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    sibling_path = prepare_session_dir(tmp_path, "def456")

    with pytest.raises(ValueError):
        list_generated_files(session_path, sibling_path)


def test_read_recent_lines_returns_tail(tmp_path: Path) -> None:
    log_path = tmp_path / "activity.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_recent_lines(log_path, max_lines=2) == ["two", "three"]


def test_read_recent_lines_returns_all_when_unlimited(tmp_path: Path) -> None:
    log_path = tmp_path / "activity.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_recent_lines(log_path, max_lines=None) == ["one", "two", "three"]


def test_cleanup_old_sessions_removes_only_expired_safe_sessions(tmp_path: Path) -> None:
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    old_session = prepare_session_dir(tmp_path, "old123")
    active_session = prepare_session_dir(tmp_path, "active123")
    fresh_session = prepare_session_dir(tmp_path, "fresh123")
    unsafe_session = tmp_path / "session_bad!"
    unsafe_session.mkdir()
    old_time = (now - timedelta(days=8)).timestamp()
    fresh_time = (now - timedelta(days=1)).timestamp()
    os.utime(old_session, (old_time, old_time))
    os.utime(active_session, (old_time, old_time))
    os.utime(fresh_session, (fresh_time, fresh_time))

    removed = cleanup_old_sessions(
        tmp_path,
        active_session_ids=["active123"],
        retention_days=7,
        now=now,
    )

    assert removed == [old_session]
    assert not old_session.exists()
    assert active_session.exists()
    assert fresh_session.exists()
    assert unsafe_session.exists()


def test_cleanup_old_sessions_with_lock_skips_existing_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / ".cleanup.lock"
    lock_path.write_text("locked", encoding="utf-8")

    assert cleanup_old_sessions_with_lock(tmp_path) == []


def test_generate_crawl_id_includes_timestamp() -> None:
    now = datetime(2026, 5, 4, 12, 30, 45, tzinfo=timezone.utc)

    assert generate_crawl_id(now).startswith("20260504_123045_")


def test_start_crawl_job_reports_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeCrawler:
        def __init__(
            self,
            *args: object,
            output_base: Path,
            progress_callback: Callable[[Mapping[str, object]], None],
            **kwargs: object,
        ) -> None:
            self.output_dir = output_base / "2026-05-04_12-30-45"
            self._progress_callback = progress_callback

        def crawl(self) -> list[object]:
            self.output_dir.mkdir(parents=True)
            self._progress_callback(
                {
                    "event": "page_processed",
                    "processed_pages": 1,
                    "successful_pages": 1,
                    "failed_pages": 0,
                    "queued_discovered_urls": 1,
                    "current_url": "https://example.com",
                    "limit": 1,
                }
            )
            return [type("Result", (), {"success": True})()]

    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(
        {
            "urls": "https://example.com",
            "limit": 1,
            "max_depth": 1,
            "flush_interval": 1,
            "delay": 0,
            "max_retries": 2,
            "exclude_tags": "nav",
            "include_only_tags": "",
            "wait_for": 0,
            "timeout": 30,
            "max_file_size_mb": 1,
            "extract_main_content": True,
            "output_extension": ".md",
            "activity_log_size": 10,
        }
    )

    job = start_crawl_job(
        session_id="abc123",
        crawl_id="run123",
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=tmp_path,
    )
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "page_processed", "completed"]


def test_start_crawl_job_reports_missing_playwright_browser_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeCrawler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.output_dir = tmp_path / "unused"

        def crawl(self) -> list[object]:
            raise RuntimeError(
                "BrowserType.launch: Executable doesn't exist at "
                "C:/Users/test/AppData/Local/ms-playwright/chromium-1217/chrome-win64/chrome.exe\n"
                "Looks like Playwright was just installed or updated.\n"
                "Please run the following command to download new browsers:\n"
                "playwright install"
            )

    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(
        {
            "urls": "https://example.com",
            "limit": 1,
            "max_depth": 1,
            "flush_interval": 1,
            "delay": 0,
            "max_retries": 2,
            "exclude_tags": "nav",
            "include_only_tags": "",
            "wait_for": 0,
            "timeout": 30,
            "max_file_size_mb": 1,
            "extract_main_content": True,
            "output_extension": ".md",
            "activity_log_size": 10,
        }
    )

    job = start_crawl_job(
        session_id="abc123",
        crawl_id="run123",
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=tmp_path,
    )
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "failed"]
    assert "python -m playwright install chromium" in str(events[-1]["error"])


def test_start_resume_job_reports_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeCrawler:
        @classmethod
        def resume(cls, output_base: Path, session: Path, **kwargs: object) -> list[object]:
            captured["output_base"] = output_base
            captured["session"] = session
            captured["kwargs"] = kwargs
            progress_callback = kwargs["progress_callback"]
            assert callable(progress_callback)
            progress_callback(
                {
                    "event": "page_processed",
                    "processed_pages": 2,
                    "successful_pages": 1,
                    "failed_pages": 1,
                    "limit": 5,
                }
            )
            return [
                type("Result", (), {"success": True})(),
                type("Result", (), {"success": False})(),
            ]

    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)
    output_base = tmp_path / "crawl_run123"
    session_path = output_base / "2026-05-06_12-00-00"
    session_path.mkdir(parents=True)

    job = start_resume_job(
        session_id="abc123",
        crawl_id="run123",
        output_base=output_base,
        session_dir=session_path,
        activity_log_size=7,
        extra_urls=["https://example.com/new"],
        limit=5,
        max_depth=2,
        max_retries=3,
        delay=1.5,
        flush_interval=2,
        wait_for=2.5,
        timeout=45,
        max_file_size_mb=2,
    )
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "page_processed", "completed"]
    assert events[-1]["processed_pages"] == 2
    assert events[-1]["successful_pages"] == 1
    assert events[-1]["failed_pages"] == 1
    assert captured["output_base"] == output_base
    assert captured["session"] == session_path
    captured_kwargs = captured["kwargs"]
    assert isinstance(captured_kwargs, dict)
    assert captured_kwargs == {
        "extra_urls": ["https://example.com/new"],
        "limit": 5,
        "max_depth": 2,
        "max_retries": 3,
        "delay": 1.5,
        "flush_interval": 2,
        "wait_for": 2.5,
        "timeout": 45,
        "max_file_size_mb": 2,
        "activity_log_size": 7,
        "progress_callback": captured_kwargs["progress_callback"],
        "should_cancel": captured_kwargs["should_cancel"],
    }


def test_start_resume_job_reports_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeCrawler:
        @classmethod
        def resume(cls, *args: object, **kwargs: object) -> list[object]:
            raise RuntimeError("resume failed")

    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)
    output_base = tmp_path / "crawl_run123"
    session_path = output_base / "2026-05-06_12-00-00"
    session_path.mkdir(parents=True)

    job = start_resume_job(
        session_id="abc123",
        crawl_id="run123",
        output_base=output_base,
        session_dir=session_path,
        activity_log_size=10,
    )
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "failed"]
    assert "RuntimeError: resume failed" in str(events[-1]["error"])


def test_start_resume_job_resolves_relative_paths_before_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Path] = {}

    class FakeCrawler:
        @classmethod
        def resume(cls, output_base: Path, session: Path, **kwargs: object) -> list[object]:
            captured["output_base"] = output_base
            captured["session"] = session
            return []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)

    output_base = Path("outputs") / "streamlit_sessions" / "session_abc123" / "crawl_run123"
    session_path = output_base / "2026-05-06_12-00-00"
    session_path.mkdir(parents=True)

    job = start_resume_job(
        session_id="abc123",
        crawl_id="run123",
        output_base=output_base,
        session_dir=session_path,
        activity_log_size=10,
    )
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "completed"]
    assert captured["output_base"].is_absolute()
    assert captured["session"].is_absolute()
    assert captured["output_base"] == output_base.resolve()
    assert captured["session"] == session_path.resolve()


def test_start_resume_job_reports_cancelled_after_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entered_resume = Event()
    release_resume = Event()

    class FakeCrawler:
        @classmethod
        def resume(cls, *args: object, **kwargs: object) -> list[object]:
            entered_resume.set()
            assert release_resume.wait(timeout=5)
            should_cancel = kwargs["should_cancel"]
            assert callable(should_cancel)
            assert should_cancel()
            return [type("Result", (), {"success": True})()]

    monkeypatch.setattr("crawl4md_streamlit.support.SiteCrawler", FakeCrawler)
    output_base = tmp_path / "crawl_run123"
    session_path = output_base / "2026-05-06_12-00-00"
    session_path.mkdir(parents=True)

    job = start_resume_job(
        session_id="abc123",
        crawl_id="run123",
        output_base=output_base,
        session_dir=session_path,
        activity_log_size=10,
    )
    assert entered_resume.wait(timeout=5)
    request_cancel(job)
    release_resume.set()
    job.thread.join(timeout=5)

    events = drain_events(job)

    assert [event["event"] for event in events] == ["started", "cancel_requested", "cancelled"]


def test_request_cancel_sets_event(tmp_path: Path) -> None:
    thread = Thread(target=lambda: None)
    job = CrawlJob(
        session_id="abc123",
        crawl_id="run123",
        output_base=tmp_path,
        events=Queue(),
        cancel_event=Event(),
        thread=thread,
    )

    request_cancel(job)

    assert job.cancel_event.is_set()
    assert drain_events(job)[0]["event"] == "cancel_requested"


def test_build_configs_surfaces_validation_errors() -> None:
    with pytest.raises(ValidationError):
        build_configs(
            {
                "urls": "not-a-url",
                "limit": 1,
                "max_depth": 1,
                "flush_interval": 1,
                "delay": 0,
                "max_retries": 2,
                "exclude_tags": "nav",
                "include_only_tags": "main",
                "wait_for": 0,
                "timeout": 30,
                "max_file_size_mb": 1,
                "extract_main_content": True,
                "output_extension": ".md",
                "activity_log_size": 10,
            }
        )
