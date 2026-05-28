"""Helpers for live and persisted crawl progress chart datasets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

_PROGRESS_HISTORY_FILE = "progress_history.jsonl"
PROGRESS_CHART_TIME_UNIT_SECOND = "second"
PROGRESS_CHART_TIME_UNIT_MINUTE = "minute"
PROGRESS_CHART_TIME_UNIT_HOUR = "hour"
_SECONDS_PER_SECOND = 1.0
_SECONDS_PER_MINUTE = 60.0
_MINUTES_PER_HOUR = 60.0
_SECONDS_PER_HOUR = _SECONDS_PER_MINUTE * _MINUTES_PER_HOUR
_PROGRESS_CHART_MINUTE_THRESHOLD_SECONDS = _SECONDS_PER_MINUTE
_PROGRESS_CHART_HOUR_THRESHOLD_SECONDS = _SECONDS_PER_HOUR
_COUNTER_KEYS = (
    "page_limit",
    "discovered_pages",
    "successful_pages",
    "failed_pages",
    "processed_pages",
)


def _coerce_int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _is_same_sample(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(left.get(key) == right.get(key) for key in _COUNTER_KEYS) and (
        left.get("elapsed_seconds") == right.get("elapsed_seconds")
    )


def append_live_progress_sample(
    history: list[dict[str, object]],
    event: Mapping[str, object],
    *,
    started_at: datetime | None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Append one live progress sample derived from a worker event."""
    event_name = str(event.get("event", "")).strip()
    if not event_name:
        return history

    previous = history[-1] if history else {}
    has_counter = any(
        key in event
        for key in (
            "limit",
            "queued_discovered_urls",
            "successful_pages",
            "failed_pages",
            "processed_pages",
        )
    )
    if not has_counter and not history:
        return history

    resolved_now = now or datetime.now(timezone.utc)
    elapsed_seconds = _coerce_float(previous.get("elapsed_seconds"), 0.0)
    if started_at is not None:
        elapsed_seconds = max((resolved_now - started_at).total_seconds(), elapsed_seconds)

    sample = {
        "timestamp": resolved_now.isoformat(timespec="seconds"),
        "event": event_name,
        "round": _coerce_int(event.get("round"), _coerce_int(previous.get("round"), 1)),
        "elapsed_seconds": elapsed_seconds,
        "page_limit": max(
            1,
            _coerce_int(event.get("limit"), _coerce_int(previous.get("page_limit"), 1)),
        ),
        "discovered_pages": _coerce_int(
            event.get("queued_discovered_urls"),
            _coerce_int(previous.get("discovered_pages"), 0),
        ),
        "successful_pages": _coerce_int(
            event.get("successful_pages"),
            _coerce_int(previous.get("successful_pages"), 0),
        ),
        "failed_pages": _coerce_int(
            event.get("failed_pages"),
            _coerce_int(previous.get("failed_pages"), 0),
        ),
        "processed_pages": _coerce_int(
            event.get("processed_pages"),
            _coerce_int(previous.get("processed_pages"), 0),
        ),
    }
    if history and _is_same_sample(history[-1], sample):
        return history
    history.append(sample)
    return history


def load_persisted_progress_history(crawl_root: Path | None) -> list[dict[str, object]]:
    """Load progress_history.jsonl rows when present, skipping malformed lines."""
    if crawl_root is None:
        return []
    history_path = crawl_root / _PROGRESS_HISTORY_FILE
    if not history_path.exists() or not history_path.is_file():
        return []

    rows: list[dict[str, object]] = []
    previous: dict[str, object] = {}
    for raw_line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Allow partial last-line writes while a crawl is still running.
            continue
        if not isinstance(payload, dict):
            continue
        sample = {
            "timestamp": str(payload.get("timestamp", "")),
            "event": str(payload.get("event", "")),
            "round": _coerce_int(payload.get("round"), _coerce_int(previous.get("round"), 1)),
            "elapsed_seconds": _coerce_float(
                payload.get("elapsed_seconds"),
                _coerce_float(previous.get("elapsed_seconds"), 0.0),
            ),
            "page_limit": max(
                1,
                _coerce_int(
                    payload.get("page_limit"),
                    _coerce_int(payload.get("limit"), _coerce_int(previous.get("page_limit"), 1)),
                ),
            ),
            "discovered_pages": _coerce_int(
                payload.get("discovered_pages"),
                _coerce_int(
                    payload.get("queued_discovered_urls"),
                    _coerce_int(previous.get("discovered_pages"), 0),
                ),
            ),
            "successful_pages": _coerce_int(
                payload.get("successful_pages"),
                _coerce_int(previous.get("successful_pages"), 0),
            ),
            "failed_pages": _coerce_int(
                payload.get("failed_pages"),
                _coerce_int(previous.get("failed_pages"), 0),
            ),
            "processed_pages": _coerce_int(
                payload.get("processed_pages"),
                _coerce_int(previous.get("processed_pages"), 0),
            ),
        }
        if rows and _is_same_sample(rows[-1], sample):
            previous = sample
            continue
        rows.append(sample)
        previous = sample
    return rows


def prepare_cumulative_chart_rows(history: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """Build cumulative-series chart rows from merged progress history."""
    rows: list[dict[str, object]] = []
    for sample in history:
        rows.append(
            {
                "elapsed_seconds": _coerce_float(sample.get("elapsed_seconds"), 0.0),
                "page_limit": _coerce_int(sample.get("page_limit"), 1),
                "discovered_pages": _coerce_int(sample.get("discovered_pages"), 0),
                "successful_pages": _coerce_int(sample.get("successful_pages"), 0),
                "failed_pages": _coerce_int(sample.get("failed_pages"), 0),
                "processed_pages": _coerce_int(sample.get("processed_pages"), 0),
            }
        )
    return rows


def select_progress_chart_time_unit(history: list[Mapping[str, object]]) -> str:
    """Return the elapsed-time unit for a progress chart history duration."""
    cumulative = prepare_cumulative_chart_rows(history)
    if not cumulative:
        return PROGRESS_CHART_TIME_UNIT_SECOND

    max_elapsed_seconds = max(
        _coerce_float(sample.get("elapsed_seconds"), 0.0) for sample in cumulative
    )
    if max_elapsed_seconds > _PROGRESS_CHART_HOUR_THRESHOLD_SECONDS:
        return PROGRESS_CHART_TIME_UNIT_HOUR
    if max_elapsed_seconds > _PROGRESS_CHART_MINUTE_THRESHOLD_SECONDS:
        return PROGRESS_CHART_TIME_UNIT_MINUTE
    return PROGRESS_CHART_TIME_UNIT_SECOND


def progress_chart_time_unit_seconds(time_unit: str) -> float:
    """Return the number of elapsed seconds represented by one display unit."""
    if time_unit == PROGRESS_CHART_TIME_UNIT_HOUR:
        return _SECONDS_PER_HOUR
    if time_unit == PROGRESS_CHART_TIME_UNIT_MINUTE:
        return _SECONDS_PER_MINUTE
    return _SECONDS_PER_SECOND


def _window_index(elapsed_seconds: float, window_seconds: float) -> int:
    if elapsed_seconds <= 0:
        return 0
    return max(1, ceil(elapsed_seconds / window_seconds))


def _add_attempts_to_windows(
    window_attempts: dict[int, float],
    *,
    start_seconds: float,
    end_seconds: float,
    attempt_count: int,
    window_seconds: float,
) -> None:
    if attempt_count <= 0:
        return

    bounded_start = max(0.0, start_seconds)
    bounded_end = max(bounded_start, end_seconds)
    if bounded_end <= bounded_start:
        window_index = max(1, _window_index(bounded_end, window_seconds))
        window_attempts[window_index] = window_attempts.get(window_index, 0.0) + attempt_count
        return

    attempts_per_second = attempt_count / (bounded_end - bounded_start)
    start_window_index = max(1, _window_index(bounded_start, window_seconds))
    end_window_index = max(1, _window_index(bounded_end, window_seconds))
    for window_index in range(start_window_index, end_window_index + 1):
        window_start = (window_index - 1) * window_seconds
        window_end = window_index * window_seconds
        overlap_seconds = min(bounded_end, window_end) - max(bounded_start, window_start)
        if overlap_seconds <= 0:
            continue
        window_attempts[window_index] = window_attempts.get(window_index, 0.0) + (
            attempts_per_second * overlap_seconds
        )


def prepare_pace_chart_rows(
    history: list[Mapping[str, object]],
    *,
    window_seconds: float | None = None,
) -> list[dict[str, float | None]]:
    """Build window-averaged seconds-per-page-attempt rows."""
    cumulative = prepare_cumulative_chart_rows(history)
    if not cumulative:
        return []

    resolved_window_seconds = window_seconds or progress_chart_time_unit_seconds(
        select_progress_chart_time_unit(cumulative)
    )
    max_elapsed_seconds = max(
        _coerce_float(sample.get("elapsed_seconds"), 0.0) for sample in cumulative
    )
    max_window_index = _window_index(max_elapsed_seconds, resolved_window_seconds)

    window_attempts: dict[int, float] = {}
    last_processed_elapsed = 0.0
    last_processed_pages = 0
    for sample in cumulative:
        current_elapsed = _coerce_float(sample.get("elapsed_seconds"), 0.0)
        current_processed_pages = _coerce_int(sample.get("processed_pages"), 0)
        processed_delta = current_processed_pages - last_processed_pages
        if processed_delta > 0:
            _add_attempts_to_windows(
                window_attempts,
                start_seconds=last_processed_elapsed,
                end_seconds=current_elapsed,
                attempt_count=processed_delta,
                window_seconds=resolved_window_seconds,
            )
            last_processed_elapsed = current_elapsed
            last_processed_pages = current_processed_pages
        elif processed_delta < 0:
            last_processed_elapsed = current_elapsed
            last_processed_pages = current_processed_pages

    pace_rows: list[dict[str, float | None]] = [
        {
            "elapsed_seconds": 0.0,
            "seconds_per_page_attempt": None,
        }
    ]
    for window_index in range(1, max_window_index + 1):
        attempts = window_attempts.get(window_index, 0.0)
        window_start = (window_index - 1) * resolved_window_seconds
        window_elapsed_seconds = min(window_index * resolved_window_seconds, max_elapsed_seconds)
        observed_window_seconds = max(0.0, window_elapsed_seconds - window_start)
        pace_rows.append(
            {
                "elapsed_seconds": window_elapsed_seconds,
                "seconds_per_page_attempt": observed_window_seconds / attempts
                if attempts > 0 and observed_window_seconds > 0
                else None,
            }
        )
    return pace_rows


def prepare_cumulative_chart_display_rows(
    rows: list[Mapping[str, object]],
    *,
    time_unit_seconds: float,
) -> list[dict[str, float]]:
    """Build cumulative chart rows with scaled elapsed-time values."""
    display_rows: list[dict[str, float]] = []
    for row in rows:
        successful_pages = _coerce_int(row.get("successful_pages"), 0)
        failed_pages = _coerce_int(row.get("failed_pages"), 0)
        display_rows.append(
            {
                "elapsed_time": _coerce_float(row.get("elapsed_seconds"), 0.0) / time_unit_seconds,
                "page_limit": _coerce_int(row.get("page_limit"), 1),
                "discovered_pages": _coerce_int(row.get("discovered_pages"), 0),
                "successful_pages": successful_pages,
                "failed_pages": failed_pages,
                "processed_pages": successful_pages + failed_pages,
            }
        )
    return display_rows


def prefer_persisted_history(
    live_history: list[dict[str, object]],
    persisted_history: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Prefer the freshest history source between persisted and live samples."""
    if not persisted_history:
        return live_history
    if not live_history:
        return persisted_history

    persisted_last = persisted_history[-1]
    live_last = live_history[-1]
    persisted_key = (
        _coerce_int(persisted_last.get("processed_pages"), 0),
        _coerce_int(persisted_last.get("discovered_pages"), 0),
        _coerce_int(persisted_last.get("successful_pages"), 0),
        _coerce_int(persisted_last.get("failed_pages"), 0),
    )
    live_key = (
        _coerce_int(live_last.get("processed_pages"), 0),
        _coerce_int(live_last.get("discovered_pages"), 0),
        _coerce_int(live_last.get("successful_pages"), 0),
        _coerce_int(live_last.get("failed_pages"), 0),
    )
    if persisted_key >= live_key:
        return persisted_history
    return live_history


def progress_history_file_name() -> str:
    """Return the persisted crawl progress-history filename."""
    return _PROGRESS_HISTORY_FILE
