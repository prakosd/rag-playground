"""Tests for the per-thread log routing context."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from app_support.log_context import get_log_session_id, set_log_session_id


@pytest.fixture(autouse=True)
def _reset_context() -> Iterator[None]:
    set_log_session_id("")
    yield
    set_log_session_id("")


def test_set_and_get_log_session_id() -> None:
    set_log_session_id("abc")
    assert get_log_session_id() == "abc"
    set_log_session_id("")
    assert get_log_session_id() == ""


def test_log_session_id_is_thread_local() -> None:
    # A background job thread must set its own id; contextvars are not inherited.
    set_log_session_id("main")
    seen: dict[str, str] = {}

    def worker() -> None:
        seen["before"] = get_log_session_id()
        set_log_session_id("worker")
        seen["after"] = get_log_session_id()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert seen["before"] == ""  # fresh thread starts with the default, not "main"
    assert seen["after"] == "worker"
    assert get_log_session_id() == "main"  # the worker's set does not leak back
