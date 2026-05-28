"""Progress-history JSONL writer for crawl progress integrations."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["PROGRESS_HISTORY_FILE", "ProgressHistoryRecorder"]

PROGRESS_HISTORY_FILE = "progress_history.jsonl"

_FORCED_EVENT_NAMES = frozenset({"crawl_started", "crawl_completed", "crawl_interrupted"})
_COUNTER_FIELDS = (
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


class ProgressHistoryRecorder:
    """Append chart-ready crawl progress samples to a JSONL file."""

    def __init__(self, *, output_dir: Path, session_id: str) -> None:
        self._path = output_dir / PROGRESS_HISTORY_FILE
        self._session_id = session_id
        self._start_monotonic = time.monotonic()
        self._current_round = 1
        self._latest_counters: dict[str, int] = {
            "page_limit": 1,
            "discovered_pages": 0,
            "successful_pages": 0,
            "failed_pages": 0,
            "processed_pages": 0,
        }
        self._last_written: dict[str, int] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def set_round(self, round_num: int) -> None:
        if round_num > 0:
            self._current_round = round_num

    def record(self, event: Mapping[str, object]) -> None:
        event_name = str(event.get("event", "")).strip()
        if not event_name:
            return

        counters = self._merge_counters(event)
        if not self._should_write(event_name, counters):
            self._latest_counters = counters
            return

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "elapsed_seconds": max(time.monotonic() - self._start_monotonic, 0.0),
            "event": event_name,
            "round": self._current_round,
            "session_id": self._session_id,
            "page_limit": counters["page_limit"],
            "discovered_pages": counters["discovered_pages"],
            "successful_pages": counters["successful_pages"],
            "failed_pages": counters["failed_pages"],
            "processed_pages": counters["processed_pages"],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
            handle.write("\n")

        self._latest_counters = counters
        self._last_written = counters

    def _merge_counters(self, event: Mapping[str, object]) -> dict[str, int]:
        previous = self._latest_counters
        return {
            "page_limit": max(
                1,
                _coerce_int(event.get("limit"), previous["page_limit"]),
            ),
            "discovered_pages": _coerce_int(
                event.get("queued_discovered_urls"),
                previous["discovered_pages"],
            ),
            "successful_pages": _coerce_int(
                event.get("successful_pages"),
                previous["successful_pages"],
            ),
            "failed_pages": _coerce_int(
                event.get("failed_pages"),
                previous["failed_pages"],
            ),
            "processed_pages": _coerce_int(
                event.get("processed_pages"),
                previous["processed_pages"],
            ),
        }

    def _should_write(self, event_name: str, counters: dict[str, int]) -> bool:
        if self._last_written is None:
            return True
        if event_name in _FORCED_EVENT_NAMES:
            return True
        return any(counters[field] != self._last_written[field] for field in _COUNTER_FIELDS)
