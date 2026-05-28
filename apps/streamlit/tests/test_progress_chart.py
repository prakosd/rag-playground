from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crawl4md_streamlit.progress_chart import (
    append_live_progress_sample,
    load_persisted_progress_history,
    prefer_persisted_history,
    prepare_cumulative_chart_rows,
    prepare_speed_chart_rows,
    progress_history_file_name,
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


def test_prepare_speed_chart_rows_uses_processed_delta_per_second() -> None:
    history = [
        {
            "elapsed_seconds": 0.0,
            "page_limit": 10,
            "discovered_pages": 0,
            "successful_pages": 0,
            "failed_pages": 0,
            "processed_pages": 0,
        },
        {
            "elapsed_seconds": 2.0,
            "page_limit": 10,
            "discovered_pages": 2,
            "successful_pages": 2,
            "failed_pages": 0,
            "processed_pages": 2,
        },
        {
            "elapsed_seconds": 5.0,
            "page_limit": 10,
            "discovered_pages": 4,
            "successful_pages": 3,
            "failed_pages": 1,
            "processed_pages": 4,
        },
    ]

    speed_rows = prepare_speed_chart_rows(history)

    assert len(speed_rows) == 3
    assert speed_rows[0]["pages_per_second"] == pytest.approx(0.0)
    assert speed_rows[1]["pages_per_second"] == pytest.approx(1.0)
    assert speed_rows[2]["pages_per_second"] == pytest.approx(2.0 / 3.0)


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


def test_prefer_persisted_history_keeps_persisted_on_equal_counters() -> None:
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

    assert selected == persisted_history


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
