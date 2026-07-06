from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from crawl4md.messages import CODE_BROWSER_MISSING, CODE_CRAWL_FAILED
from pydantic import ValidationError

from crawl4md_streamlit import session_manager
from crawl4md_streamlit.support import (
    CrawlJob,
    JobSnapshot,
    SessionRecord,
    active_registry_session_ids,
    activity_log_path,
    bootstrap_gate_state,
    build_configs,
    cleanup_old_sessions,
    cleanup_old_sessions_with_lock,
    count_crawl_dirs,
    crawl_output_base,
    create_session_record,
    drain_events,
    elapsed_time_display,
    estimate_progress,
    find_latest_crawl_dir,
    format_eta_seconds,
    format_status_row,
    format_status_url_preview,
    generate_crawl_id,
    generate_safe_id,
    get_active_job_snapshot,
    is_text_previewable,
    job_state_from_event,
    latest_session_id,
    list_generated_files,
    next_crawl_sequence,
    normalize_event_urls,
    normalize_session_records,
    prepare_crawl_output_base,
    prepare_session_dir,
    preview_created_timestamp,
    read_recent_lines,
    read_text_preview,
    request_cancel,
    serialize_session_records,
    session_dir,
    session_exists,
    session_time_remaining,
    should_show_portfolio_modal,
    start_crawl_job,
    touch_session,
    validate_safe_id,
)


def _form_values(*, urls: str = "https://example.com", limit: int = 1) -> dict[str, object]:
    return {
        "urls": urls,
        "limit": limit,
        "max_depth": 1,
        "max_concurrent": 1,
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


def test_generate_safe_id_uses_path_safe_characters() -> None:
    safe_id = generate_safe_id()

    assert safe_id
    assert validate_safe_id(safe_id) == safe_id


def test_generate_safe_id_uses_readable_format_when_toggle_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "_USE_READABLE_IDS", True)
    monkeypatch.setattr(session_manager, "_READABLE_SESSION_WORD_COUNT", 2)
    monkeypatch.setattr(session_manager, "_READABLE_ID_DIGITS", 0)
    monkeypatch.setattr(session_manager, "_readable_word_pool", lambda: ("winter",))

    chosen_words = iter(("winter", "apple"))
    monkeypatch.setattr(session_manager.secrets, "choice", lambda _words: next(chosen_words))

    assert generate_safe_id() == "winter_apple"


def test_generate_readable_session_id_includes_digits_when_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "_READABLE_SESSION_WORD_COUNT", 2)
    monkeypatch.setattr(session_manager, "_READABLE_ID_DIGITS", 2)
    monkeypatch.setattr(session_manager, "_READABLE_ID_LIMIT", 100)
    monkeypatch.setattr(session_manager, "_readable_word_pool", lambda: ("boulder",))

    chosen_words = iter(("boulder", "river"))
    monkeypatch.setattr(session_manager.secrets, "choice", lambda _words: next(chosen_words))
    monkeypatch.setattr(session_manager.secrets, "randbelow", lambda _limit: 7)

    assert session_manager._generate_readable_session_id() == "boulder_river_07"


def test_generate_readable_session_id_words_only_when_digits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "_READABLE_SESSION_WORD_COUNT", 1)
    monkeypatch.setattr(session_manager, "_READABLE_ID_DIGITS", 0)
    monkeypatch.setattr(session_manager, "_readable_word_pool", lambda: ("cedar",))
    monkeypatch.setattr(session_manager.secrets, "choice", lambda _words: "cedar")

    assert session_manager._generate_readable_session_id() == "cedar"


def test_generate_safe_id_uses_legacy_token_when_toggle_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "_USE_READABLE_IDS", False)

    def _fake_token_urlsafe(size: int) -> str:
        assert size == 9
        return "AbC+/="

    monkeypatch.setattr(session_manager.secrets, "token_urlsafe", _fake_token_urlsafe)

    assert generate_safe_id() == "abc___"


def test_readable_word_pool_loads_expected_safe_eff_words() -> None:
    session_manager._readable_word_pool.cache_clear()
    words = session_manager._readable_word_pool()

    assert len(words) == 7776
    assert "abacus" in words
    assert "yo-yo" in words
    assert all(word == word.lower() for word in words)
    assert all(all(char in session_manager._SAFE_WORD_CHARS for char in word) for word in words)


def test_session_and_crawl_dirs_are_prefixed(tmp_path: Path) -> None:
    session_path = session_dir(tmp_path, "abc123")
    crawl_path = crawl_output_base(tmp_path, "abc123", "run_123")

    assert session_path == tmp_path / "session_abc123"
    assert crawl_path == tmp_path / "session_abc123" / "crawl_run_123"


def test_validate_safe_id_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        validate_safe_id("../secret")


def test_session_exists_returns_true_when_directory_exists(tmp_path: Path) -> None:
    (tmp_path / "session_myid").mkdir()
    assert session_exists(tmp_path, "myid") is True


def test_session_exists_returns_false_when_directory_missing(tmp_path: Path) -> None:
    assert session_exists(tmp_path, "myid") is False


def test_session_exists_returns_false_for_invalid_id(tmp_path: Path) -> None:
    assert session_exists(tmp_path, "../escape") is False


def test_session_exists_returns_false_for_empty_id(tmp_path: Path) -> None:
    assert session_exists(tmp_path, "") is False


def test_touch_session_updates_directory_mtime(tmp_path: Path) -> None:
    sdir = tmp_path / "session_myid"
    sdir.mkdir()
    old_time = 0.0
    os.utime(sdir, (old_time, old_time))
    before = sdir.stat().st_mtime

    touch_session(tmp_path, "myid")

    assert sdir.stat().st_mtime > before


def test_touch_session_raises_for_invalid_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        touch_session(tmp_path, "../escape")


# ── session_time_remaining ────────────────────────────────────────────────────


_NOW = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_session_time_remaining_no_dir_returns_full_retention(tmp_path: Path) -> None:
    days, hours = session_time_remaining(tmp_path, "newid", now=_NOW)
    assert days == 7
    assert hours == 0


def test_session_time_remaining_fresh_dir_returns_full_retention(tmp_path: Path) -> None:
    sdir = tmp_path / "session_fresh"
    sdir.mkdir()
    os.utime(sdir, (_NOW.timestamp(), _NOW.timestamp()))

    days, hours = session_time_remaining(tmp_path, "fresh", now=_NOW)
    assert days == 7
    assert hours == 0


def test_session_time_remaining_3_days_old_returns_4_days(tmp_path: Path) -> None:
    sdir = tmp_path / "session_aged"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=3)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "aged", now=_NOW)
    assert days == 4
    assert hours == 0


def test_session_time_remaining_3d_5h_old_returns_remainder_hours(tmp_path: Path) -> None:
    sdir = tmp_path / "session_partial"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=3, hours=5)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "partial", now=_NOW)
    assert days == 3
    assert hours == 19  # 7d - 3d5h = 3d19h


def test_session_time_remaining_sub_24h_returns_hours(tmp_path: Path) -> None:
    sdir = tmp_path / "session_sub24"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=6, hours=2)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "sub24", now=_NOW)
    assert days == 0
    assert hours == 22  # floor of (7d - 6d2h) = 22h


def test_session_time_remaining_1_hour_left(tmp_path: Path) -> None:
    sdir = tmp_path / "session_1h"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=6, hours=23)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "1h", now=_NOW)
    assert days == 0
    assert hours == 1


def test_session_time_remaining_sub_1h_returns_0_hours(tmp_path: Path) -> None:
    sdir = tmp_path / "session_sub1h"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=6, hours=23, minutes=30)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "sub1h", now=_NOW)
    assert days == 0
    assert hours == 0


def test_session_time_remaining_overdue_returns_0_hours(tmp_path: Path) -> None:
    sdir = tmp_path / "session_overdue"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=9)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "overdue", now=_NOW)
    assert days == 0
    assert hours == 0


def test_session_time_remaining_exactly_at_boundary_returns_0_hours(tmp_path: Path) -> None:
    sdir = tmp_path / "session_exact"
    sdir.mkdir()
    mtime = (_NOW - timedelta(days=7)).timestamp()
    os.utime(sdir, (mtime, mtime))

    days, hours = session_time_remaining(tmp_path, "exact", now=_NOW)
    assert days == 0
    assert hours == 0


def test_create_session_record_uses_safe_id_and_utc_time() -> None:
    now = datetime(2026, 5, 13, 17, 30, tzinfo=timezone(timedelta(hours=7)))

    record = create_session_record("abc123", now=now)

    assert record == SessionRecord(
        session_id="abc123",
        created_at=datetime(2026, 5, 13, 10, 30, tzinfo=timezone.utc),
    )


def test_bootstrap_gate_state_waits_for_hydration_first() -> None:
    state = bootstrap_gate_state(
        browser_sessions_hydrated=False,
        pending_bootstrap_session_id="",
        session_storage_write_failed=False,
    )

    assert state == "hydrating"


def test_bootstrap_gate_state_waits_for_storage_roundtrip() -> None:
    state = bootstrap_gate_state(
        browser_sessions_hydrated=True,
        pending_bootstrap_session_id="session123",
        session_storage_write_failed=False,
    )

    assert state == "storing"


def test_bootstrap_gate_state_surfaces_storage_failure() -> None:
    state = bootstrap_gate_state(
        browser_sessions_hydrated=True,
        pending_bootstrap_session_id="session123",
        session_storage_write_failed=True,
    )

    assert state == "storage_error"


def test_bootstrap_gate_state_is_ready_when_bootstrap_is_complete() -> None:
    state = bootstrap_gate_state(
        browser_sessions_hydrated=True,
        pending_bootstrap_session_id="",
        session_storage_write_failed=True,
    )

    assert state == "ready"


def test_portfolio_modal_waits_for_browser_storage_hydration() -> None:
    assert not should_show_portfolio_modal(
        browser_sessions_hydrated=False,
        last_dismissed_at=None,
        repeat_after_hours=168,
        now=_NOW,
    )


def test_portfolio_modal_shows_when_no_previous_timestamp_exists() -> None:
    assert should_show_portfolio_modal(
        browser_sessions_hydrated=True,
        last_dismissed_at=None,
        repeat_after_hours=168,
        now=_NOW,
    )


def test_portfolio_modal_stays_hidden_after_recent_dismissal() -> None:
    assert not should_show_portfolio_modal(
        browser_sessions_hydrated=True,
        last_dismissed_at="2026-05-20T12:00:00Z",
        repeat_after_hours=168,
        now=_NOW,
    )


def test_portfolio_modal_shows_after_repeat_interval() -> None:
    assert should_show_portfolio_modal(
        browser_sessions_hydrated=True,
        last_dismissed_at="2026-05-17T11:59:59Z",
        repeat_after_hours=168,
        now=_NOW,
    )


def test_portfolio_modal_ignores_invalid_timestamps() -> None:
    assert should_show_portfolio_modal(
        browser_sessions_hydrated=True,
        last_dismissed_at="",
        repeat_after_hours=168,
        now=_NOW,
    )


def test_serialize_session_records_formats_utc_iso_strings() -> None:
    records = [
        SessionRecord("older", datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)),
        SessionRecord("newer", datetime(2026, 5, 13, 11, 0, tzinfo=timezone.utc)),
    ]

    serialized = serialize_session_records(records)

    assert serialized == [
        {"session_id": "newer", "created_at": "2026-05-13T11:00:00Z", "language": "EN"},
        {"session_id": "older", "created_at": "2026-05-13T10:00:00Z", "language": "EN"},
    ]


def test_normalize_session_records_sorts_newest_and_deduplicates() -> None:
    payload = {
        "sessions": [
            {"session_id": "same", "created_at": "2026-05-13T10:00:00Z"},
            {"session_id": "other", "created_at": "2026-05-13T11:00:00Z"},
            {"session_id": "same", "created_at": "2026-05-13T12:00:00Z"},
        ]
    }

    records = normalize_session_records(payload)

    assert [(record.session_id, record.created_at.hour) for record in records] == [
        ("same", 12),
        ("other", 11),
    ]


def test_normalize_session_records_ignores_malformed_and_unsafe_values() -> None:
    payload = [
        {"session_id": "../secret", "created_at": "2026-05-13T10:00:00Z"},
        {"session_id": "bad!", "created_at": "2026-05-13T10:00:00Z"},
        {"session_id": "missing_time"},
        {"session_id": "bad_time", "created_at": "not-a-date"},
        {"session_id": "valid_1", "created_at": "2026-05-13T10:00:00Z"},
    ]

    records = normalize_session_records(payload)

    assert [record.session_id for record in records] == ["valid_1"]


def test_latest_session_id_returns_newest_or_empty() -> None:
    records = normalize_session_records(
        [
            {"session_id": "older", "created_at": "2026-05-13T10:00:00Z"},
            {"session_id": "newer", "created_at": "2026-05-13T10:01:00Z"},
        ]
    )

    assert latest_session_id(records) == "newer"
    assert latest_session_id([]) == ""


def test_session_record_defaults_language_to_en() -> None:
    record = SessionRecord("abc123", datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc))

    assert record.language == "EN"


def test_create_session_record_stores_given_language() -> None:
    record = create_session_record("abc123", language="ID")

    assert record.language == "ID"


def test_create_session_record_defaults_language_to_en() -> None:
    record = create_session_record("abc123")

    assert record.language == "EN"


def test_create_session_record_rejects_invalid_language() -> None:
    record = create_session_record("abc123", language="FR")

    assert record.language == "EN"


def test_serialize_session_records_includes_language() -> None:
    records = [SessionRecord("abc", datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc), "ID")]

    serialized = serialize_session_records(records)

    assert serialized[0]["language"] == "ID"


def test_normalize_session_records_reads_language_from_payload() -> None:
    payload = [{"session_id": "abc", "created_at": "2026-05-13T10:00:00Z", "language": "ID"}]

    records = normalize_session_records(payload)

    assert records[0].language == "ID"


def test_normalize_session_records_defaults_language_to_en_when_missing() -> None:
    payload = [{"session_id": "abc", "created_at": "2026-05-13T10:00:00Z"}]

    records = normalize_session_records(payload)

    assert records[0].language == "EN"


def test_normalize_session_records_defaults_language_to_en_for_invalid() -> None:
    payload = [{"session_id": "abc", "created_at": "2026-05-13T10:00:00Z", "language": "FR"}]

    records = normalize_session_records(payload)

    assert records[0].language == "EN"


def test_normalize_session_records_last_record_wins_for_equal_timestamp() -> None:
    payload = [
        {"session_id": "abc", "created_at": "2026-05-13T10:00:00Z", "language": "EN"},
        {"session_id": "abc", "created_at": "2026-05-13T10:00:00Z", "language": "ID"},
    ]

    records = normalize_session_records(payload)

    assert len(records) == 1
    assert records[0].language == "ID"


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


def test_estimate_progress_handles_unknown_limit_and_clamps() -> None:
    unknown = estimate_progress(4, 0)
    clamped = estimate_progress(5, 2)

    assert unknown.fraction == 0.0
    assert unknown.percent == 0
    assert unknown.label == "Estimating"
    assert clamped.fraction == 1.0
    assert clamped.percent == 100


def test_elapsed_time_display_shows_duration_for_running_state() -> None:
    started_at = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 13, 10, 0, 5, tzinfo=timezone.utc)

    elapsed = elapsed_time_display(started_at=started_at, job_state="running", now=now)

    assert elapsed == "0:00:05"


def test_elapsed_time_display_hides_when_crawl_is_not_active() -> None:
    started_at = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 13, 10, 0, 5, tzinfo=timezone.utc)

    elapsed = elapsed_time_display(started_at=started_at, job_state="stopped", now=now)

    assert elapsed == ""


def test_elapsed_time_display_hides_when_started_at_missing() -> None:
    now = datetime(2026, 5, 13, 10, 0, 5, tzinfo=timezone.utc)

    elapsed = elapsed_time_display(started_at=None, job_state="running", now=now)

    assert elapsed == ""


def test_elapsed_time_display_restarts_from_zero_for_new_crawl() -> None:
    now = datetime(2026, 5, 13, 10, 0, 10, tzinfo=timezone.utc)
    previous_start = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
    restarted_start = datetime(2026, 5, 13, 10, 0, 10, tzinfo=timezone.utc)

    previous_elapsed = elapsed_time_display(
        started_at=previous_start,
        job_state="running",
        now=now,
    )
    restarted_elapsed = elapsed_time_display(
        started_at=restarted_start,
        job_state="running",
        now=now,
    )

    assert previous_elapsed == "0:00:10"
    assert restarted_elapsed == "0:00:00"


def test_elapsed_time_display_shows_duration_when_cancel_requested() -> None:
    started_at = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 13, 10, 0, 7, tzinfo=timezone.utc)

    elapsed = elapsed_time_display(
        started_at=started_at,
        job_state="cancel_requested",
        now=now,
    )

    assert elapsed == "0:00:07"


def test_elapsed_time_display_shows_frozen_value_when_stopped() -> None:
    started_at = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 13, 10, 0, 7, tzinfo=timezone.utc)

    elapsed = elapsed_time_display(
        started_at=started_at,
        job_state="stopped",
        frozen_elapsed="0:00:07",
        now=now,
    )

    assert elapsed == "0:00:07"


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


def test_list_generated_files_respects_download_size_limit(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    output_path = prepare_crawl_output_base(tmp_path, "abc123", "run_123")
    generated = output_path / "final" / "large_file.md"
    generated.parent.mkdir()
    generated.write_text("x" * 20, encoding="utf-8")

    files = list_generated_files(session_path, output_path, download_limit_bytes=10)

    assert len(files) == 1
    assert files[0].download_allowed is False


def test_list_generated_files_reflects_file_changes(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    output_path = prepare_crawl_output_base(tmp_path, "abc123", "run_123")
    generated = output_path / "final" / "content.md"
    generated.parent.mkdir()
    generated.write_text("old", encoding="utf-8")

    first = list_generated_files(session_path, output_path, download_limit_bytes=5)
    generated.write_text("new content", encoding="utf-8")
    second = list_generated_files(session_path, output_path, download_limit_bytes=5)

    assert first[0].size_bytes == 3
    assert first[0].download_allowed is True
    assert second[0].size_bytes == 11
    assert second[0].download_allowed is False


def test_list_generated_files_accepts_relative_session_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    sessions_root = Path("outputs") / "streamlit_sessions"
    session_path = prepare_session_dir(sessions_root, "abc123")
    output_path = prepare_crawl_output_base(sessions_root, "abc123", "run_123")
    generated = output_path / "final" / "success_urls.txt"
    generated.parent.mkdir()
    generated.write_text("https://example.com\n", encoding="utf-8")

    files = list_generated_files(session_path, output_path)

    assert [file.relative_path for file in files] == ["crawl_run_123/final/success_urls.txt"]


def test_list_generated_files_rejects_sibling_session(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    sibling_path = prepare_session_dir(tmp_path, "def456")

    with pytest.raises(ValueError):
        list_generated_files(session_path, sibling_path)


def test_list_generated_files_skips_symlink_escape(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("secret", encoding="utf-8")
    link_path = session_path / "outside.txt"
    try:
        link_path.symlink_to(outside_file)
    except (NotImplementedError, OSError):
        # Symlinks unavailable (e.g. Windows without elevated privilege).
        # Simulate the escape by placing a regular file and patching
        # Path.resolve so ensure_within_root sees it as outside the root.
        link_path.write_text("placeholder", encoding="utf-8")
        resolved_outside = outside_file.resolve()
        _original_resolve = Path.resolve

        def _mock_resolve(self: Path, *, strict: bool = False) -> Path:
            if self == link_path:
                return resolved_outside
            return _original_resolve(self, strict=strict)

        with patch.object(Path, "resolve", _mock_resolve):
            files = list_generated_files(session_path)

        assert files == []
        return

    files = list_generated_files(session_path)

    assert files == []


def test_is_text_previewable_accepts_common_text_extensions() -> None:
    assert is_text_previewable("results.md")
    assert is_text_previewable("report.json")
    assert is_text_previewable("index.html")
    assert is_text_previewable("activity.log")
    assert is_text_previewable("notes.TXT")


def test_is_text_previewable_rejects_binary_extensions() -> None:
    assert not is_text_previewable("image.png")
    assert not is_text_previewable("archive.zip")
    assert not is_text_previewable("capture.pdf")


def test_preview_created_timestamp_prefers_birthtime_when_available() -> None:
    stat_result = SimpleNamespace(st_birthtime=10.0, st_ctime=20.0)

    created_timestamp = preview_created_timestamp(stat_result, platform_name="posix")

    assert created_timestamp == 10.0


def test_preview_created_timestamp_uses_ctime_on_windows_without_birthtime() -> None:
    stat_result = SimpleNamespace(st_ctime=20.0)

    created_timestamp = preview_created_timestamp(stat_result, platform_name="nt")

    assert created_timestamp == 20.0


def test_preview_created_timestamp_skips_ctime_on_non_windows_without_birthtime() -> None:
    stat_result = SimpleNamespace(st_ctime=20.0)

    created_timestamp = preview_created_timestamp(stat_result, platform_name="posix")

    assert created_timestamp is None


def test_preview_created_timestamp_rejects_non_numeric_values() -> None:
    stat_result = SimpleNamespace(st_birthtime="invalid", st_ctime="invalid")

    created_timestamp = preview_created_timestamp(stat_result, platform_name="nt")

    assert created_timestamp is None


def test_read_text_preview_returns_text_and_not_truncated(tmp_path: Path) -> None:
    file_path = tmp_path / "content.txt"
    file_path.write_text("hello world", encoding="utf-8")

    preview = read_text_preview(file_path, max_bytes=100)

    assert preview.text == "hello world"
    assert preview.truncated is False


def test_read_text_preview_marks_truncated_when_limit_exceeded(tmp_path: Path) -> None:
    file_path = tmp_path / "content.txt"
    file_path.write_text("0123456789", encoding="utf-8")

    preview = read_text_preview(file_path, max_bytes=5)

    assert preview.text == "01234"
    assert preview.truncated is True


def test_read_text_preview_replaces_invalid_utf8_bytes(tmp_path: Path) -> None:
    file_path = tmp_path / "content.txt"
    file_path.write_bytes(b"first\n\xff\xfe\nlast")

    preview = read_text_preview(file_path, max_bytes=100)

    assert "\ufffd" in preview.text
    assert preview.truncated is False


def test_read_text_preview_handles_missing_file(tmp_path: Path) -> None:
    preview = read_text_preview(tmp_path / "missing.txt", max_bytes=100)

    assert preview.text == ""
    assert preview.truncated is False


def test_read_text_preview_rejects_non_positive_limit(tmp_path: Path) -> None:
    file_path = tmp_path / "content.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError):
        read_text_preview(file_path, max_bytes=0)


def test_read_recent_lines_returns_tail(tmp_path: Path) -> None:
    log_path = tmp_path / "activity.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_recent_lines(log_path, max_lines=2) == ["two", "three"]


def test_read_recent_lines_returns_all_when_unlimited(tmp_path: Path) -> None:
    log_path = tmp_path / "activity.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert read_recent_lines(log_path, max_lines=None) == ["one", "two", "three"]


def test_read_recent_lines_handles_missing_file_and_non_positive_limit(tmp_path: Path) -> None:
    missing = tmp_path / "missing.log"
    log_path = tmp_path / "activity.log"
    log_path.write_text("one\ntwo\n", encoding="utf-8")

    assert read_recent_lines(missing, max_lines=5) == []
    assert read_recent_lines(log_path, max_lines=0) == []


def test_cleanup_old_sessions_removes_only_expired_safe_sessions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
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

    # The app configures logging with propagate=False, so attach the capture
    # handler directly to the target logger rather than relying on root propagation.
    caplog.set_level(logging.INFO, logger="crawl4md_streamlit")
    target_logger = logging.getLogger("crawl4md_streamlit")
    target_logger.addHandler(caplog.handler)
    try:
        removed = cleanup_old_sessions(
            tmp_path,
            active_session_ids=["active123"],
            retention_days=7,
            now=now,
        )
    finally:
        target_logger.removeHandler(caplog.handler)

    assert removed == [old_session]
    assert not old_session.exists()
    assert active_session.exists()
    assert fresh_session.exists()
    assert unsafe_session.exists()
    assert any("Session cleanup removed" in record.getMessage() for record in caplog.records)


def test_cleanup_old_sessions_with_lock_skips_existing_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / ".cleanup.lock"
    lock_path.write_text("locked", encoding="utf-8")

    assert cleanup_old_sessions_with_lock(tmp_path) == []


def test_cleanup_old_sessions_returns_empty_when_root_is_missing(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    assert cleanup_old_sessions(missing_root) == []
    assert not missing_root.exists()


def test_cleanup_old_sessions_with_lock_returns_empty_when_root_is_missing(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"

    assert cleanup_old_sessions_with_lock(missing_root) == []
    assert not missing_root.exists()


def test_cleanup_old_sessions_with_lock_replaces_stale_lock(tmp_path: Path) -> None:
    old_session = prepare_session_dir(tmp_path, "old123")
    lock_path = tmp_path / ".cleanup.lock"
    lock_path.write_text("stale", encoding="utf-8")

    stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(lock_path, (stale_time, stale_time))
    os.utime(old_session, (stale_time, stale_time))

    removed = cleanup_old_sessions_with_lock(tmp_path, retention_days=0)

    assert removed == [old_session]
    assert not lock_path.exists()


def test_generate_crawl_id_uses_seq_prefix_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "_USE_READABLE_IDS", True)
    monkeypatch.setattr(session_manager, "_readable_word_pool", lambda: ("boulder",))
    monkeypatch.setattr(session_manager.secrets, "choice", lambda words: words[0])

    assert generate_crawl_id(seq=1) == "01_boulder"
    assert generate_crawl_id(seq=42) == "42_boulder"


def test_count_crawl_dirs_returns_zero_when_session_dir_missing(tmp_path: Path) -> None:
    assert count_crawl_dirs(tmp_path, "abc123") == 0


def test_count_crawl_dirs_counts_only_crawl_prefixed_subdirs(tmp_path: Path) -> None:
    sdir = prepare_session_dir(tmp_path, "abc123")
    (sdir / "crawl_1_boulder").mkdir()
    (sdir / "crawl_2_river").mkdir()
    (sdir / "other_dir").mkdir()
    (sdir / "not_a_dir.txt").write_text("x", encoding="utf-8")

    assert count_crawl_dirs(tmp_path, "abc123") == 2


def test_next_crawl_sequence_returns_one_when_session_dir_missing(tmp_path: Path) -> None:
    assert next_crawl_sequence(tmp_path, "abc123") == 1


def test_next_crawl_sequence_uses_highest_existing_number(tmp_path: Path) -> None:
    session_path = prepare_session_dir(tmp_path, "abc123")
    (session_path / "crawl_01_boulder").mkdir()
    (session_path / "crawl_9_river").mkdir()
    (session_path / "crawl_10_cedar").mkdir()
    (session_path / "crawl_20260504_123045_legacy").mkdir()
    (session_path / "other_dir").mkdir()

    assert next_crawl_sequence(tmp_path, "abc123") == 11


def test_generate_crawl_id_includes_timestamp() -> None:
    now = datetime(2026, 5, 4, 12, 30, 45, tzinfo=timezone.utc)

    assert generate_crawl_id(now).startswith("20260504_123045_")


def test_generate_crawl_id_uses_single_word_suffix_when_toggle_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 4, 12, 30, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(session_manager, "_USE_READABLE_IDS", True)
    monkeypatch.setattr(session_manager, "_readable_word_pool", lambda: ("boulder",))
    monkeypatch.setattr(session_manager.secrets, "choice", lambda words: words[0])

    assert generate_crawl_id(now) == "20260504_123045_boulder"


def test_generate_crawl_id_uses_legacy_suffix_when_toggle_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 4, 12, 30, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(session_manager, "_USE_READABLE_IDS", False)

    def _fake_token_urlsafe(size: int) -> str:
        assert size == 9
        return "Token123"

    monkeypatch.setattr(session_manager.secrets, "token_urlsafe", _fake_token_urlsafe)

    assert generate_crawl_id(now) == "20260504_123045_token123"


def test_find_latest_crawl_dir_and_activity_log_path(tmp_path: Path) -> None:
    crawl_a = prepare_crawl_output_base(tmp_path, "abc123", "run123")
    crawl_b = prepare_crawl_output_base(tmp_path, "abc123", "run124")

    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
    new_time = datetime.now(timezone.utc).timestamp()
    os.utime(crawl_a, (old_time, old_time))
    os.utime(crawl_b, (new_time, new_time))

    assert find_latest_crawl_dir(crawl_b.parent) == crawl_b
    assert find_latest_crawl_dir(tmp_path / "missing") is None
    assert activity_log_path(None) is None
    assert activity_log_path(crawl_b) is None

    log_path = crawl_b / "activity_log.txt"
    log_path.write_text("entry", encoding="utf-8")
    assert activity_log_path(crawl_b) == log_path


def test_start_crawl_job_reports_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeCrawler:
        crawl_error = None
        seen_session_id = ""

        def __init__(
            self,
            *args: object,
            output_base: Path,
            session_id: str,
            progress_callback: Callable[[Mapping[str, object]], None],
            **kwargs: object,
        ) -> None:
            self.output_dir = output_base / "2026-05-04_12-30-45"
            FakeCrawler.seen_session_id = session_id
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

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values())

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
    assert all(float(event["elapsed_seconds"]) >= 0.0 for event in events)
    assert [event["elapsed_seconds"] for event in events] == sorted(
        event["elapsed_seconds"] for event in events
    )
    assert FakeCrawler.seen_session_id == "session_abc123"


def test_start_crawl_job_reports_success_and_failure_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeCrawler:
        def __init__(
            self,
            *args: object,
            output_base: Path,
            **kwargs: object,
        ) -> None:
            self.output_dir = output_base / "2026-05-04_12-30-45"
            self.crawl_error = None

        def crawl(self) -> list[object]:
            self.output_dir.mkdir(parents=True)
            return [
                type("Result", (), {"success": True})(),
                type("Result", (), {"success": False})(),
            ]

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values(limit=2))

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
    completed = events[-1]

    assert completed["event"] == "completed"
    assert completed["processed_pages"] == 2
    assert completed["successful_pages"] == 1
    assert completed["failed_pages"] == 1
    assert completed["current_url"] == ""
    assert completed["next_url"] == ""
    assert completed["eta_remaining_seconds"] is None
    assert completed["active_url_count"] == 0
    assert completed["active_urls"] == []
    assert completed["next_url_count"] == 0
    assert completed["next_urls"] == []
    assert completed["max_concurrent"] == crawler_config.max_concurrent


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

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values())

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
    assert events[-1]["error_code"] == CODE_BROWSER_MISSING
    assert "playwright install" in str(events[-1]["error"]).lower()


def test_start_crawl_job_reports_generic_error_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeCrawler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.output_dir = tmp_path / "unused"

        def crawl(self) -> list[object]:
            raise ValueError("boom")

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values())

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
    assert events[-1]["error_code"] == CODE_CRAWL_FAILED
    assert "boom" in str(events[-1]["error"])
    assert events[-1]["current_url"] == ""
    assert events[-1]["next_url"] == ""
    assert events[-1]["eta_remaining_seconds"] is None
    assert events[-1]["active_url_count"] == 0
    assert events[-1]["active_urls"] == []
    assert events[-1]["next_url_count"] == 0
    assert events[-1]["next_urls"] == []
    assert events[-1]["max_concurrent"] == crawler_config.max_concurrent


def test_start_crawl_job_reports_error_with_finalized_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A crawl that errors mid-run but finalizes reports 'failed' with its output."""

    class FakeCrawler:
        def __init__(self, *args: object, output_base: Path, **kwargs: object) -> None:
            self.output_dir = output_base / "2026-05-07_09-00-00"
            self.crawl_error = None

        def crawl(self) -> list[object]:
            self.output_dir.mkdir(parents=True)
            self.crawl_error = "browser pool crashed"
            return [type("Result", (), {"success": True})()]

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values())

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
    failed = events[-1]

    assert failed["event"] == "failed"
    assert failed["error_code"] == CODE_CRAWL_FAILED
    assert "browser pool crashed" in str(failed["error"])
    assert str(failed["output_dir"]).endswith("2026-05-07_09-00-00")
    assert failed["processed_pages"] == 1
    assert failed["successful_pages"] == 1
    assert failed["failed_pages"] == 0


def test_start_crawl_job_reports_cancelled_after_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entered_crawl = Event()
    release_crawl = Event()

    class FakeCrawler:
        def __init__(
            self,
            *args: object,
            output_base: Path,
            should_cancel: Callable[[], bool],
            **kwargs: object,
        ) -> None:
            self.output_dir = output_base / "2026-05-06_12-00-00"
            self._should_cancel = should_cancel
            self.crawl_error = None

        def crawl(self) -> list[object]:
            self.output_dir.mkdir(parents=True)
            entered_crawl.set()
            assert release_crawl.wait(timeout=5)
            should_cancel = self._should_cancel
            assert callable(should_cancel)
            assert should_cancel()
            return [type("Result", (), {"success": True})()]

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    crawler_config, page_config, activity_log_size = build_configs(_form_values())

    job = start_crawl_job(
        session_id="abc123",
        crawl_id="run123",
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=tmp_path,
    )
    assert entered_crawl.wait(timeout=5)
    request_cancel(job)
    release_crawl.set()
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


def test_job_state_from_event_maps_expected_and_unknown_values() -> None:
    assert job_state_from_event("started") == "running"
    assert job_state_from_event("completed") == "completed"
    assert job_state_from_event("failed") == "failed"
    assert job_state_from_event("cancel_requested") == "cancel_requested"
    assert job_state_from_event("cancelled") == "cancelled"
    assert job_state_from_event("something_else") == "running"


def test_build_configs_surfaces_validation_errors() -> None:
    with pytest.raises(ValidationError):
        build_configs(
            {
                **_form_values(urls="not-a-url"),
                "include_only_tags": "main",
            }
        )


def test_build_configs_passes_max_concurrent_to_crawler_config() -> None:
    crawler_config, _, _ = build_configs(
        {
            **_form_values(),
            "max_concurrent": 3,
        }
    )

    assert crawler_config.max_concurrent == 3


def test_build_configs_rejects_non_positive_activity_log_size() -> None:
    with pytest.raises(ValueError, match="Activity log size must be at least 1"):
        build_configs(
            {
                **_form_values(),
                "activity_log_size": 0,
            }
        )


# ---------------------------------------------------------------------------
# format_eta_seconds
# ---------------------------------------------------------------------------


def _en_strings() -> Mapping[str, object]:
    from crawl4md_streamlit.i18n import STRINGS_EN

    return STRINGS_EN


def _id_strings() -> Mapping[str, object]:
    from crawl4md_streamlit.i18n import STRINGS_ID

    return STRINGS_ID


def test_format_eta_seconds_none_returns_estimating_en() -> None:
    result = format_eta_seconds(None, _en_strings())
    assert result == "Estimating..."


def test_format_eta_seconds_none_returns_estimating_id() -> None:
    result = format_eta_seconds(None, _id_strings())
    assert result == "Mengestimasi..."


def test_format_eta_seconds_less_than_60_returns_less_than_minute_en() -> None:
    result = format_eta_seconds(45.0, _en_strings())
    assert result == "Less than a minute left"


def test_format_eta_seconds_less_than_60_returns_less_than_minute_id() -> None:
    result = format_eta_seconds(30.0, _id_strings())
    assert result == "Kurang dari satu menit lagi"


def test_format_eta_seconds_zero_returns_less_than_minute() -> None:
    result = format_eta_seconds(0.0, _en_strings())
    assert result == "Less than a minute left"


def test_format_eta_seconds_minutes_en() -> None:
    result = format_eta_seconds(180.0, _en_strings())  # 3 minutes
    assert "3" in result
    assert "minute" in result.lower()


def test_format_eta_seconds_minutes_id() -> None:
    result = format_eta_seconds(120.0, _id_strings())  # 2 minutes
    assert "2" in result
    assert "menit" in result


def test_format_eta_seconds_hours_minutes_en() -> None:
    result = format_eta_seconds(3700.0, _en_strings())  # 1h 1m 40s → 1h 1m
    assert "1" in result
    assert "h" in result


def test_format_eta_seconds_hours_minutes_id() -> None:
    result = format_eta_seconds(7260.0, _id_strings())  # 2h 1m
    assert "2" in result
    assert "j" in result


def test_format_eta_seconds_exactly_60_is_one_minute() -> None:
    result = format_eta_seconds(60.0, _en_strings())
    assert "1" in result
    assert "minute" in result.lower()


def test_format_eta_seconds_does_not_compute_from_processed_elapsed() -> None:
    """format_eta_seconds only formats provided seconds — it has no internal crawl state."""
    # Called with same seconds, different strings → only wording differs
    result_en = format_eta_seconds(120.0, _en_strings())
    result_id = format_eta_seconds(120.0, _id_strings())
    assert "2" in result_en and "2" in result_id
    assert result_en != result_id  # different languages produce different text


# Risk: status rows render crawler-provided URL text as HTML. Type: unit.
def test_format_status_row_builds_link_and_right_text() -> None:
    markup = format_status_row(
        url="https://example.com/path",
        url_template="Next: {url_html}",
        right_text="About 2 minute(s) left",
        style="display:flex",
    )

    assert 'href="https://example.com/path"' in markup
    assert "Next:" in markup
    assert "\u00bb" in markup  # visual marker before the URL
    assert "About 2 minute(s) left" in markup


# Risk: malicious URL or status text must not break out of status-row HTML. Type: unit.
def test_format_status_row_escapes_url_and_right_text() -> None:
    markup = format_status_row(
        url='https://example.com/" onmouseover="alert(1)',
        url_template="Crawling: {url_html}",
        right_text='<script>alert("x")</script>',
        style="display:flex",
    )

    assert '" onmouseover="' not in markup
    assert "&quot; onmouseover=&quot;" in markup
    assert "<script>" not in markup
    assert "&lt;script&gt;alert(&quot;" in markup


def test_normalize_event_urls_accepts_strings_and_iterables() -> None:
    assert normalize_event_urls("https://example.com/a") == ["https://example.com/a"]
    assert normalize_event_urls(["https://example.com/a", "", 123]) == ["https://example.com/a"]
    assert normalize_event_urls({"url": "https://example.com/a"}) == []


# Risk: active/next URL previews render crawler-provided values as HTML. Type: unit.
def test_format_status_url_preview_escapes_links_and_overflow() -> None:
    markup = format_status_url_preview(
        label="Active fetches (2 of 5 configured)",
        urls=[
            "https://example.com/a",
            'https://example.com/" onclick="alert(1)',
        ],
        total_count=4,
        right_text='<script>alert("x")</script>',
        style="display:flex",
        overflow_template="+{count} more",
    )

    assert 'href="https://example.com/a"' in markup
    assert "\u00bb" in markup  # visual marker before each URL
    assert 'onclick="alert' not in markup
    assert "&quot; onclick=&quot;alert" in markup
    assert "+2 more" in markup
    assert "<script>" not in markup
    assert "&lt;script&gt;alert(&quot;" in markup


# ---------------------------------------------------------------------------
# Process-local job registry
# ---------------------------------------------------------------------------


def _make_dead_job(session_id: str = "sess_dead", tmp_path: Path | None = None) -> CrawlJob:
    """Return a CrawlJob whose thread has already finished."""
    base = (tmp_path or Path("/tmp")) / session_id
    t = Thread(target=lambda: None)
    t.start()
    t.join()
    return CrawlJob(
        session_id=session_id,
        crawl_id="cr_dead",
        output_base=base,
        events=Queue(),
        cancel_event=Event(),
        thread=t,
    )


def _make_alive_job(
    session_id: str = "sess_alive", *, tmp_path: Path | None = None
) -> tuple[CrawlJob, Event]:
    """Return a CrawlJob whose thread blocks until the returned event is set."""
    base = (tmp_path or Path("/tmp")) / session_id
    gate = Event()
    t = Thread(target=gate.wait)
    t.daemon = True
    t.start()
    job = CrawlJob(
        session_id=session_id,
        crawl_id="cr_alive",
        output_base=base,
        events=Queue(),
        cancel_event=Event(),
        thread=t,
    )
    return job, gate


def _alive_snapshot(
    session_id: str = "sess_alive",
    *,
    tmp_path: Path | None = None,
    job_state: str = "running",
) -> tuple[JobSnapshot, Event]:
    job, gate = _make_alive_job(session_id, tmp_path=tmp_path)
    snap = JobSnapshot(
        job=job,
        crawl_id=job.crawl_id,
        started_at=datetime.now(timezone.utc),
        activity_log_size=50,
        job_state=job_state,
    )
    return snap, gate


def test_get_active_job_snapshot_returns_none_when_no_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs._JOB_REGISTRY", {})
    assert get_active_job_snapshot("no_such_session") is None


def test_get_active_job_snapshot_returns_snapshot_for_alive_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap, gate = _alive_snapshot()
    try:
        monkeypatch.setattr(
            "crawl4md_streamlit.crawl_jobs._JOB_REGISTRY",
            {snap.job.session_id: snap},
        )
        result = get_active_job_snapshot(snap.job.session_id)
        assert result is snap
    finally:
        gate.set()


def test_get_active_job_snapshot_returns_none_for_dead_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dead_job = _make_dead_job()
    snap = JobSnapshot(
        job=dead_job,
        crawl_id=dead_job.crawl_id,
        started_at=datetime.now(timezone.utc),
        activity_log_size=50,
        job_state="running",
    )
    monkeypatch.setattr(
        "crawl4md_streamlit.crawl_jobs._JOB_REGISTRY",
        {dead_job.session_id: snap},
    )
    assert get_active_job_snapshot(dead_job.session_id) is None


def test_active_registry_session_ids_returns_only_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap_alive, gate = _alive_snapshot("sess_a")
    snap_dead = JobSnapshot(
        job=_make_dead_job("sess_d"),
        crawl_id="cr_d",
        started_at=datetime.now(timezone.utc),
        activity_log_size=50,
        job_state="running",
    )
    try:
        monkeypatch.setattr(
            "crawl4md_streamlit.crawl_jobs._JOB_REGISTRY",
            {"sess_a": snap_alive, "sess_d": snap_dead},
        )
        ids = active_registry_session_ids()
        assert "sess_a" in ids
        assert "sess_d" not in ids
    finally:
        gate.set()


def test_request_cancel_updates_registry_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap, gate = _alive_snapshot("sess_cancel")
    try:
        monkeypatch.setattr(
            "crawl4md_streamlit.crawl_jobs._JOB_REGISTRY",
            {"sess_cancel": snap},
        )
        request_cancel(snap.job)
        assert snap.job_state == "cancel_requested"
        assert snap.job.cancel_event.is_set()
    finally:
        gate.set()


def test_start_crawl_job_registers_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """start_crawl_job must add a snapshot to the registry before the thread starts."""

    class FakeCrawler:
        def __init__(self, *args: object, output_base: Path, **kwargs: object) -> None:
            self.output_dir = output_base / "fake_out"
            self.crawl_error = None

        def crawl(self) -> list[object]:
            return []

    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs.SiteCrawler", FakeCrawler)
    registry: dict = {}
    monkeypatch.setattr("crawl4md_streamlit.crawl_jobs._JOB_REGISTRY", registry)

    crawler_config, page_config, activity_log_size = build_configs(_form_values())
    job = start_crawl_job(
        session_id="sess_reg",
        crawl_id="cr_reg",
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=tmp_path,
    )
    job.thread.join(timeout=5)

    assert "sess_reg" in registry
    assert registry["sess_reg"].job is job
