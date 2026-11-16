"""Tests for the bounded job-event queue helper (PERF-M4)."""

from __future__ import annotations

import queue

from app_support.event_queue import put_drop_oldest


def test_put_drop_oldest_keeps_queue_bounded_and_recent() -> None:
    q: queue.Queue[int] = queue.Queue(maxsize=2)
    for n in range(5):
        put_drop_oldest(q, n)
    assert q.qsize() == 2  # stays bounded at maxsize
    assert [q.get_nowait(), q.get_nowait()] == [3, 4]  # oldest dropped, most-recent kept


def test_put_drop_oldest_under_capacity_preserves_order() -> None:
    q: queue.Queue[str] = queue.Queue(maxsize=5)
    for item in ("a", "b", "c"):
        put_drop_oldest(q, item)
    assert [q.get_nowait() for _ in range(3)] == ["a", "b", "c"]
