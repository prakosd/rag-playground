"""Shared scaffold for long-running streaming jobs (crawl, index).

A worker runs in a background thread, pushing frame dicts (``{"event": ...}`` /
``{"result": ...}``) onto a queue; the response streams ``{"job_id": ...}`` first (so the
client can cancel) then those frames as newline-delimited JSON. A per-job cancel ``Event``
lives in a shared registry so :func:`cancel_job` can flip it, and the registry entry is
pruned when the stream ends (including on client disconnect).
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from collections.abc import Callable, Iterator

from fastapi.responses import StreamingResponse

NDJSON_MEDIA_TYPE = "application/x-ndjson"
SENTINEL = object()  # queue marker: the worker has finished
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()

Worker = Callable[["queue.Queue[object]", threading.Event], None]


def stream_job(worker: Worker, *, name: str) -> StreamingResponse:
    """Run *worker* in a daemon thread, streaming its queued frames as NDJSON.

    *worker(events, cancel_event)* pushes frame dicts onto *events* and must push
    :data:`SENTINEL` when done. The first streamed frame is ``{"job_id": ...}`` (used to
    cancel); the cancel registry entry is removed once the stream drains or the client
    disconnects. If the client disconnects mid-stream, the job is also signalled to cancel
    so the worker stops cooperatively instead of running on against an undrained queue.
    """
    events: queue.Queue[object] = queue.Queue()
    cancel_event = threading.Event()
    job_id = uuid.uuid4().hex
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[job_id] = cancel_event
    threading.Thread(
        target=lambda: worker(events, cancel_event), name=f"{name}-{job_id}", daemon=True
    ).start()

    def frames() -> Iterator[str]:
        try:
            yield json.dumps({"job_id": job_id}) + "\n"
            while True:
                item = events.get()
                if item is SENTINEL:
                    break
                yield json.dumps(item) + "\n"
        finally:
            # On client disconnect the generator is closed here while the worker is still
            # running; flip the cancel flag so it stops instead of filling an undrained
            # queue. On normal completion the worker has already finished, so this is a
            # harmless no-op.
            cancel_event.set()
            with _CANCEL_LOCK:
                _CANCEL_EVENTS.pop(job_id, None)

    return StreamingResponse(frames(), media_type=NDJSON_MEDIA_TYPE)


def cancel_job(job_id: str) -> dict[str, bool]:
    """Request cooperative cancellation of a running streaming job by its id."""
    with _CANCEL_LOCK:
        event = _CANCEL_EVENTS.get(job_id)
    if event is not None:
        event.set()
    return {"cancelled": event is not None}
