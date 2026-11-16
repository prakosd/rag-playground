"""A bounded event queue for background job progress (crawl, index).

The live progress/activity stream is drained by the Streamlit UI on reruns. If a tab is closed
mid-job there is no consumer, so an unbounded queue would grow for the whole job; these helpers
cap it and drop the *oldest* event on overflow — the registry's ``latest_event`` snapshot still
carries current progress for reattach, so only the live activity backlog is trimmed.
"""

from __future__ import annotations

import contextlib
import queue
from typing import TypeVar

# Cap the live event queue: generous for an actively-draining tab (reruns clear it every few
# seconds), bounded for an abandoned one so a long job can't grow it without limit.
EVENT_QUEUE_MAXSIZE = 10_000

_T = TypeVar("_T")


def put_drop_oldest(q: queue.Queue[_T], item: _T) -> None:
    """Enqueue *item*, dropping the oldest event if the queue is full.

    Safe for concurrent producers (the worker's ``emit`` plus a cancel request) and a
    concurrent UI drain: the drop-then-insert retry tolerates a racing refill, keeping the
    queue bounded at its ``maxsize`` while retaining the most recent events.
    """
    try:
        q.put_nowait(item)
    except queue.Full:
        with contextlib.suppress(queue.Empty):
            q.get_nowait()  # drop the oldest event to make room
        with contextlib.suppress(queue.Full):
            q.put_nowait(item)
