"""Helpers for live and persisted crawl progress chart datasets."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
_TERMINAL_EVENT_NAMES = frozenset({"crawl_completed", "crawl_interrupted"})


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: Any, fallback: float) -> float:
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
    if "elapsed_seconds" in event:
        elapsed_seconds = max(_coerce_float(event.get("elapsed_seconds"), elapsed_seconds), 0.0)
        elapsed_seconds = max(elapsed_seconds, _coerce_float(previous.get("elapsed_seconds"), 0.0))
    elif started_at is not None:
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


def prepare_cumulative_chart_rows(
    history: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
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


def select_progress_chart_time_unit(history: Sequence[Mapping[str, object]]) -> str:
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


def prepare_cumulative_chart_display_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    time_unit_seconds: float,
) -> list[dict[str, float]]:
    """Build cumulative chart rows with scaled elapsed-time values."""
    display_rows: list[dict[str, float]] = []
    sorted_rows = sorted(rows, key=lambda row: _coerce_float(row.get("elapsed_seconds"), 0.0))
    for row in sorted_rows:
        successful_pages = _coerce_int(row.get("successful_pages"), 0)
        failed_pages = _coerce_int(row.get("failed_pages"), 0)
        display_row = {
            "elapsed_time": max(_coerce_float(row.get("elapsed_seconds"), 0.0), 0.0)
            / time_unit_seconds,
            "page_limit": _coerce_int(row.get("page_limit"), 1),
            "discovered_pages": _coerce_int(row.get("discovered_pages"), 0),
            "successful_pages": successful_pages,
            "failed_pages": failed_pages,
            "processed_pages": successful_pages + failed_pages,
        }
        if display_rows and display_rows[-1]["elapsed_time"] == display_row["elapsed_time"]:
            display_rows[-1] = display_row
        else:
            display_rows.append(display_row)
    return display_rows


def prefer_persisted_history(
    live_history: Sequence[Mapping[str, object]],
    persisted_history: Sequence[Mapping[str, object]],
) -> Sequence[Mapping[str, object]]:
    """Prefer the freshest history source between persisted and live samples."""
    if not persisted_history:
        return live_history
    if not live_history:
        return persisted_history

    persisted_last = persisted_history[-1]
    if str(persisted_last.get("event", "")) in _TERMINAL_EVENT_NAMES:
        return persisted_history

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
    if persisted_key > live_key:
        return persisted_history
    if live_key > persisted_key:
        return live_history

    persisted_elapsed = _coerce_float(persisted_last.get("elapsed_seconds"), 0.0)
    live_elapsed = _coerce_float(live_last.get("elapsed_seconds"), 0.0)
    if live_elapsed > persisted_elapsed:
        return live_history
    return persisted_history


def progress_history_file_name() -> str:
    """Return the persisted crawl progress-history filename."""
    return _PROGRESS_HISTORY_FILE
