"""Tests for the shared streaming-job scaffold (job_stream)."""

from __future__ import annotations

import asyncio
import gc
import json
import threading

from app_backend import job_stream


def test_stream_job_signals_cancel_when_stream_is_abandoned() -> None:
    captured: dict[str, threading.Event] = {}
    started = threading.Event()
    stopped = threading.Event()

    def worker(events, cancel_event):
        captured["cancel"] = cancel_event
        started.set()
        events.put({"event": "one"})
        cancel_event.wait(timeout=5)  # block as if still working mid-job
        stopped.set()
        events.put(job_stream.SENTINEL)

    async def drive() -> str:
        response = job_stream.stream_job(worker, name="test")
        body = response.body_iterator
        first = await body.__anext__()  # {"job_id": ...}
        await body.__anext__()  # {"event": "one"}
        await body.aclose()  # the client goes away mid-stream
        return first

    first = asyncio.run(drive())
    gc.collect()  # force any pending generator finalization so the finally runs

    assert "job_id" in json.loads(first)
    assert started.wait(1.0)
    assert captured["cancel"].is_set()  # teardown signalled the worker to stop
    assert stopped.wait(2.0)  # so the worker unblocked and exited instead of running on
    assert job_stream._CANCEL_EVENTS == {}  # registry entry pruned on disconnect


def test_stream_job_prunes_registry_on_normal_completion() -> None:
    def worker(events, cancel_event):
        events.put({"event": "done"})
        events.put(job_stream.SENTINEL)

    async def drive() -> list[str]:
        response = job_stream.stream_job(worker, name="test")
        return [line async for line in response.body_iterator]

    frames = asyncio.run(drive())

    assert "job_id" in json.loads(frames[0])
    assert json.loads(frames[1]) == {"event": "done"}
    assert job_stream._CANCEL_EVENTS == {}  # entry removed once the stream drains
