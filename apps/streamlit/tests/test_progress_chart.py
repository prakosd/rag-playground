from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawl4md_streamlit.progress_chart import (
    PROGRESS_CHART_TIME_UNIT_HOUR,
    PROGRESS_CHART_TIME_UNIT_MINUTE,
    PROGRESS_CHART_TIME_UNIT_SECOND,
    append_live_progress_sample,
    load_persisted_progress_history,
    prefer_persisted_history,
    prepare_cumulative_chart_display_rows,
    prepare_cumulative_chart_rows,
    progress_chart_time_unit_seconds,
    progress_history_file_name,
    select_progress_chart_time_unit,
)


def test_append_live_progress_sample_tracks_event_counters() -> None:
    started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=timezone.utc)
    now = started_at + timedelta(seconds=4)
    history: list[dict[str, object]] = []

    append_live_progress_sample(
        history,
        {"event": "crawl_started", "limit": 12},
        started_at=started_at,
        now=started_at,
    )
    append_live_progress_sample(
        history,
        {
            "event": "page_processed",
            "limit": 12,
            "queued_discovered_urls": 5,
            "successful_pages": 2,
            "failed_pages": 1,
            "processed_pages": 3,
        },
        started_at=started_at,
        now=now,
    )

    assert len(history) == 2
    assert history[-1]["event"] == "page_processed"
    assert history[-1]["page_limit"] == 12
    assert history[-1]["discovered_pages"] == 5
    assert history[-1]["successful_pages"] == 2
    assert history[-1]["failed_pages"] == 1
    assert history[-1]["processed_pages"] == 3
    assert history[-1]["elapsed_seconds"] == pytest.approx(4.0)


def test_append_live_progress_sample_carries_previous_values_for_sparse_events() -> None:
    started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=timezone.utc)
    history: list[dict[str, object]] = []

    append_live_progress_sample(
        history,
        {
            "event": "page_processed",
            "limit": 8,
            "queued_discovered_urls": 3,
            "successful_pages": 2,
            "failed_pages": 0,
            "processed_pages": 2,
        },
        started_at=started_at,
        now=started_at,
    )
    append_live_progress_sample(
        history,
        {
            "event": "urls_discovered",
            "queued_discovered_urls": 6,
            "limit": 8,
        },
        started_at=started_at,
        now=started_at + timedelta(seconds=2),
    )

    assert len(history) == 2
    assert history[-1]["discovered_pages"] == 6
    assert history[-1]["successful_pages"] == 2
    assert history[-1]["failed_pages"] == 0
    assert history[-1]["processed_pages"] == 2


def test_append_live_progress_sample_prefers_worker_elapsed_seconds() -> None:
    started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=timezone.utc)
    drain_time = started_at + timedelta(seconds=60)
    history: list[dict[str, object]] = []

    append_live_progress_sample(
        history,
        {
            "event": "page_processed",
            "elapsed_seconds": 2.5,
            "limit": 8,
            "queued_discovered_urls": 1,
            "successful_pages": 1,
            "failed_pages": 0,
            "processed_pages": 1,
        },
        started_at=started_at,
        now=drain_time,
    )

    assert history[-1]["elapsed_seconds"] == pytest.approx(2.5)


def test_append_live_progress_sample_keeps_burst_events_on_worker_time() -> None:
    started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=timezone.utc)
    drain_time = started_at + timedelta(seconds=90)
    history: list[dict[str, object]] = []

    for elapsed_seconds, successful_pages in [(4.0, 1), (6.0, 2)]:
        append_live_progress_sample(
            history,
            {
                "event": "page_processed",
                "elapsed_seconds": elapsed_seconds,
                "limit": 8,
                "queued_discovered_urls": successful_pages,
                "successful_pages": successful_pages,
                "failed_pages": 0,
                "processed_pages": successful_pages,
            },
            started_at=started_at,
            now=drain_time,
        )

    assert [row["elapsed_seconds"] for row in history] == pytest.approx([4.0, 6.0])


def test_load_persisted_progress_history_skips_partial_last_line(tmp_path: Path) -> None:
    history_file = tmp_path / progress_history_file_name()
    history_file.write_text(
        "\n".join(
            [
                '{"event":"crawl_started","elapsed_seconds":0,"page_limit":5,"discovered_pages":0,"successful_pages":0,"failed_pages":0,"processed_pages":0}',
                '{"event":"page_processed","elapsed_seconds":3,"page_limit":5,"discovered_pages":2,"successful_pages":1,"failed_pages":0,"processed_pages":1}',
                '{"event":"page_processed"',
            ]
        ),
        encoding="utf-8",
    )

    rows = load_persisted_progress_history(tmp_path)

    assert len(rows) == 2
    assert rows[0]["event"] == "crawl_started"
    assert rows[1]["event"] == "page_processed"


def test_load_persisted_progress_history_prefers_logs_subdir(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / progress_history_file_name()).write_text(
        '{"event":"crawl_started","elapsed_seconds":0,"page_limit":5,'
        '"discovered_pages":0,"successful_pages":0,"failed_pages":0,"processed_pages":0}',
        encoding="utf-8",
    )
    # A stale legacy file at the crawl root must be ignored in favor of logs/.
    (tmp_path / progress_history_file_name()).write_text(
        '{"event":"crawl_completed","elapsed_seconds":9,"page_limit":5,'
        '"discovered_pages":0,"successful_pages":0,"failed_pages":0,"processed_pages":0}',
        encoding="utf-8",
    )

    rows = load_persisted_progress_history(tmp_path)

    assert [row["event"] for row in rows] == ["crawl_started"]


def test_select_progress_chart_time_unit_uses_seconds_for_short_crawls() -> None:
    history = [{"elapsed_seconds": 60.0, "processed_pages": 2}]

    assert select_progress_chart_time_unit(history) == PROGRESS_CHART_TIME_UNIT_SECOND


def test_select_progress_chart_time_unit_uses_minutes_for_medium_crawls() -> None:
    history = [{"elapsed_seconds": 180.0, "processed_pages": 2}]

    assert select_progress_chart_time_unit(history) == PROGRESS_CHART_TIME_UNIT_MINUTE


def test_select_progress_chart_time_unit_uses_hours_for_long_crawls() -> None:
    history = [{"elapsed_seconds": 7200.0, "processed_pages": 2}]

    assert select_progress_chart_time_unit(history) == PROGRESS_CHART_TIME_UNIT_HOUR


def test_progress_chart_time_unit_seconds_returns_display_window_size() -> None:
    assert progress_chart_time_unit_seconds(PROGRESS_CHART_TIME_UNIT_SECOND) == pytest.approx(1.0)
    assert progress_chart_time_unit_seconds(PROGRESS_CHART_TIME_UNIT_MINUTE) == pytest.approx(60.0)
    assert progress_chart_time_unit_seconds(PROGRESS_CHART_TIME_UNIT_HOUR) == pytest.approx(3600.0)


def test_prefer_persisted_history_uses_persisted_when_available() -> None:
    live_history = [{"event": "live"}]
    persisted_history = [{"event": "persisted"}]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == persisted_history


def test_prefer_persisted_history_keeps_newer_live_samples() -> None:
    live_history = [
        {
            "elapsed_seconds": 8.0,
            "processed_pages": 4,
        }
    ]
    persisted_history = [
        {
            "elapsed_seconds": 6.0,
            "processed_pages": 3,
        }
    ]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == live_history


def test_prefer_persisted_history_prefers_higher_processed_even_when_elapsed_lower() -> None:
    live_history = [
        {
            "elapsed_seconds": 12.0,
            "processed_pages": 3,
            "discovered_pages": 3,
            "successful_pages": 3,
            "failed_pages": 0,
        }
    ]
    persisted_history = [
        {
            "elapsed_seconds": 11.0,
            "processed_pages": 4,
            "discovered_pages": 4,
            "successful_pages": 4,
            "failed_pages": 0,
        }
    ]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == persisted_history


def test_prefer_persisted_history_uses_terminal_persisted_sample_over_retry_attempts() -> None:
    live_history = [
        {
            "elapsed_seconds": 14.2,
            "event": "page_processed",
            "processed_pages": 183,
            "discovered_pages": 176,
            "successful_pages": 171,
            "failed_pages": 12,
        }
    ]
    persisted_history = [
        {
            "elapsed_seconds": 14.4,
            "event": "crawl_completed",
            "processed_pages": 177,
            "discovered_pages": 177,
            "successful_pages": 171,
            "failed_pages": 6,
        }
    ]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == persisted_history


def test_prefer_persisted_history_prefers_higher_discovered_when_processed_equal() -> None:
    live_history = [
        {
            "elapsed_seconds": 9.0,
            "processed_pages": 2,
            "discovered_pages": 3,
            "successful_pages": 2,
            "failed_pages": 0,
        }
    ]
    persisted_history = [
        {
            "elapsed_seconds": 8.0,
            "processed_pages": 2,
            "discovered_pages": 5,
            "successful_pages": 2,
            "failed_pages": 0,
        }
    ]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == persisted_history


def test_prefer_persisted_history_keeps_newer_live_elapsed_on_equal_counters() -> None:
    live_history = [
        {
            "elapsed_seconds": 10.0,
            "processed_pages": 2,
            "discovered_pages": 4,
            "successful_pages": 2,
            "failed_pages": 0,
        }
    ]
    persisted_history = [
        {
            "elapsed_seconds": 2.0,
            "processed_pages": 1,
            "discovered_pages": 2,
            "successful_pages": 1,
            "failed_pages": 0,
        },
        {
            "elapsed_seconds": 8.0,
            "processed_pages": 2,
            "discovered_pages": 4,
            "successful_pages": 2,
            "failed_pages": 0,
        },
    ]

    selected = prefer_persisted_history(live_history, persisted_history)

    assert selected == live_history


def test_prepare_cumulative_chart_rows_preserves_counter_fields() -> None:
    history = [
        {
            "elapsed_seconds": 1.5,
            "page_limit": 6,
            "discovered_pages": 4,
            "successful_pages": 3,
            "failed_pages": 1,
            "processed_pages": 4,
        }
    ]

    rows = prepare_cumulative_chart_rows(history)

    assert rows == [
        {
            "elapsed_seconds": 1.5,
            "page_limit": 6,
            "discovered_pages": 4,
            "successful_pages": 3,
            "failed_pages": 1,
            "processed_pages": 4,
        }
    ]


def test_prepare_cumulative_chart_display_rows_scales_time_and_combines_attempts() -> None:
    rows = [
        {
            "elapsed_seconds": 120.0,
            "page_limit": 10,
            "discovered_pages": 8,
            "successful_pages": 5,
            "failed_pages": 2,
        }
    ]

    display_rows = prepare_cumulative_chart_display_rows(rows, time_unit_seconds=60.0)

    assert display_rows == [
        {
            "elapsed_time": 2.0,
            "page_limit": 10,
            "discovered_pages": 8,
            "successful_pages": 5,
            "failed_pages": 2,
            "processed_pages": 7,
        }
    ]


def test_prepare_cumulative_chart_display_rows_sorts_elapsed_time() -> None:
    rows = [
        {
            "elapsed_seconds": 120.0,
            "page_limit": 10,
            "discovered_pages": 8,
            "successful_pages": 5,
            "failed_pages": 2,
        },
        {
            "elapsed_seconds": 0.0,
            "page_limit": 10,
            "discovered_pages": 1,
            "successful_pages": 0,
            "failed_pages": 0,
        },
        {
            "elapsed_seconds": 60.0,
            "page_limit": 10,
            "discovered_pages": 6,
            "successful_pages": 4,
            "failed_pages": 1,
        },
    ]

    display_rows = prepare_cumulative_chart_display_rows(rows, time_unit_seconds=60.0)

    assert [row["elapsed_time"] for row in display_rows] == pytest.approx([0.0, 1.0, 2.0])
    assert [row["processed_pages"] for row in display_rows] == [0, 5, 7]


def test_prepare_cumulative_chart_display_rows_keeps_latest_duplicate_time_sample() -> None:
    rows = [
        {
            "elapsed_seconds": 60.0,
            "page_limit": 10,
            "discovered_pages": 8,
            "successful_pages": 4,
            "failed_pages": 1,
        },
        {
            "elapsed_seconds": 60.0,
            "page_limit": 10,
            "discovered_pages": 7,
            "successful_pages": 5,
            "failed_pages": 1,
        },
    ]

    display_rows = prepare_cumulative_chart_display_rows(rows, time_unit_seconds=60.0)

    assert display_rows == [
        {
            "elapsed_time": 1.0,
            "page_limit": 10,
            "discovered_pages": 7,
            "successful_pages": 5,
            "failed_pages": 1,
            "processed_pages": 6,
        }
    ]
