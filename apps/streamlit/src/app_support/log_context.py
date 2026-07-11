"""Per-thread log routing context for the Streamlit app.

The app configures ``log4py`` once per process, but a single process serves many
browser sessions and runs crawl/index jobs in background threads. To route each
log record to the *right* session's file, code sets the active session id in this
context; the log4py file router reads it per record.

``contextvars`` are not inherited by new threads, so each background job must call
:func:`set_log_session_id` at the top of its worker function, and the main script
sets it once per run.
"""

from __future__ import annotations

import contextvars

_log_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("log_session_id", default="")


def set_log_session_id(session_id: str) -> None:
    """Set the session id used to route log records on the current thread."""
    _log_session_id.set(session_id or "")


def get_log_session_id() -> str:
    """Return the session id for the current thread's log routing (``""`` if unset)."""
    return _log_session_id.get()
