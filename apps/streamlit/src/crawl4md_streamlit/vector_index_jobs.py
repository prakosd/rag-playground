"""Background vector indexing job helpers for the crawl4md Streamlit app.

Mirrors the crawl job pattern: an indexing run executes in a daemon thread,
emits progress events through a queue, and supports cooperative cancellation.
The heavy lifting lives in the UI-independent :mod:`vector_indexer` library.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from log4py import get_logger
from vector_indexer import IndexingConfig, VectorIndexer, messages
from vector_indexer.indexer import (
    STAGE_CHUNKING,
    STAGE_EMBEDDING,
    STAGE_LOADING,
    STAGE_RESOLVING_MODEL,
    STAGE_SAVING,
)
from vector_indexer.messages import (
    CODE_EMBEDDING_FAILED,
    CODE_MISSING_AWS_CREDENTIALS,
    CODE_MISSING_OPENAI_KEY,
    CODE_MODEL_UNAVAILABLE,
    CODE_SSL_CERTIFICATE,
)

from crawl4md_streamlit.log_context import set_log_session_id
from crawl4md_streamlit.session_manager import DEFAULT_SESSIONS_ROOT, prepare_vector_output_base

_EVENT_STARTED = "started"
_EVENT_PROGRESS = "progress"
_EVENT_COMPLETED = "completed"
_EVENT_FAILED = "failed"
_EVENT_CANCELLED = "cancelled"
_EVENT_CANCEL_REQUESTED = "cancel_requested"

_UPLOAD_DIR_NAME = "uploads"

_logger = get_logger(__name__)

# Per-stage i18n label keys for the indeterminate "what's happening now" caption
# shown whenever there is no measurable chunk progress to put on the bar yet.
_VECTOR_STAGE_LABELS: dict[str, str] = {
    STAGE_RESOLVING_MODEL: "VEC_STAGE_RESOLVING_MODEL",
    STAGE_LOADING: "VEC_STAGE_LOADING",
    STAGE_CHUNKING: "VEC_STAGE_CHUNKING",
    STAGE_EMBEDDING: "VEC_STAGE_EMBEDDING",
    STAGE_SAVING: "VEC_STAGE_SAVING",
}


@dataclass(frozen=True)
class VectorIndexJob:
    """Background vector-index job state shared with the Streamlit session."""

    session_id: str
    vector_id: str
    output_base: Path
    events: queue.Queue[dict[str, object]]
    cancel_event: threading.Event
    thread: threading.Thread


@dataclass
class VectorJobSnapshot:
    """Process-local snapshot of a running indexing job, shared across sessions.

    Mirrors ``crawl_jobs.JobSnapshot``: the background thread updates ``latest_event``
    on every emit so any browser session (even a different one that reopened the
    same crawl session) can read the current indexing progress without consuming
    the single-consumer event queue.
    """

    job: VectorIndexJob
    vector_id: str
    started_at: datetime
    job_state: str
    latest_event: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Process-local active indexing job registry
# ---------------------------------------------------------------------------
# Maps session_id → VectorJobSnapshot for indexing jobs that are still alive (or
# recently finished). Protected by _REGISTRY_LOCK so background threads and
# Streamlit reruns can both read/write safely. This is what lets a second browser
# tab see an in-progress index and keep its form locked.
_REGISTRY_LOCK: threading.Lock = threading.Lock()
_VECTOR_JOB_REGISTRY: dict[str, VectorJobSnapshot] = {}


def _register_job(snapshot: VectorJobSnapshot) -> None:
    """Register a new indexing snapshot, pruning any stale terminal entries first."""
    with _REGISTRY_LOCK:
        stale = [
            sid for sid, snap in _VECTOR_JOB_REGISTRY.items() if not snap.job.thread.is_alive()
        ]
        for sid in stale:
            del _VECTOR_JOB_REGISTRY[sid]
        _VECTOR_JOB_REGISTRY[snapshot.job.session_id] = snapshot


def _update_snapshot(session_id: str, event: dict[str, object], state: str) -> None:
    """Update the registry snapshot's latest_event and job_state from a worker emit."""
    with _REGISTRY_LOCK:
        snap = _VECTOR_JOB_REGISTRY.get(session_id)
        if snap is None:
            return
        snap.latest_event = dict(event)
        snap.job_state = state


def get_active_vector_job_snapshot(session_id: str) -> VectorJobSnapshot | None:
    """Return the active indexing snapshot for a session if its thread is alive."""
    with _REGISTRY_LOCK:
        snap = _VECTOR_JOB_REGISTRY.get(session_id)
    if snap is None:
        return None
    if not snap.job.thread.is_alive():
        return None
    return snap


def active_vector_registry_session_ids() -> frozenset[str]:
    """Return session IDs whose indexing job threads are still alive."""
    with _REGISTRY_LOCK:
        return frozenset(
            sid for sid, snap in _VECTOR_JOB_REGISTRY.items() if snap.job.thread.is_alive()
        )


def _safe_upload_name(index: int, name: str) -> str:
    base = Path(name).name or f"upload_{index}"
    return f"{index:02d}_{base}"


def _write_uploads(upload_dir: Path, uploads: Sequence[tuple[str, bytes]]) -> list[Path]:
    if not uploads:
        return []
    upload_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, (name, data) in enumerate(uploads, start=1):
        target = upload_dir / _safe_upload_name(index, name)
        target.write_bytes(data)
        written.append(target)
    return written


def start_vector_index_job(
    *,
    session_id: str,
    vector_id: str,
    config: IndexingConfig,
    selected_paths: Sequence[str | Path],
    uploads: Sequence[tuple[str, bytes]] = (),
    sessions_root: Path | str = DEFAULT_SESSIONS_ROOT,
    indexer: VectorIndexer | None = None,
) -> VectorIndexJob:
    """Start an indexing run in a background thread and return its job handle."""
    output_base = prepare_vector_output_base(sessions_root, session_id, vector_id)
    event_queue: queue.Queue[dict[str, object]] = queue.Queue()
    cancel_event = threading.Event()
    runner = indexer or VectorIndexer()
    upload_paths = _write_uploads(output_base / _UPLOAD_DIR_NAME, uploads)
    input_paths = [str(path) for path in selected_paths] + [str(path) for path in upload_paths]

    def emit(event: Mapping[str, object]) -> None:
        raw = dict(event)
        raw.setdefault("session_id", session_id)
        raw.setdefault("vector_id", vector_id)
        event_queue.put(raw)
        _update_snapshot(session_id, raw, job_state_from_event(str(raw.get("event", ""))))

    def run() -> None:
        set_log_session_id(session_id)  # route this worker thread's logs to the session
        emit({"event": _EVENT_STARTED})
        try:
            result = runner.run(
                config,
                input_paths,
                output_base,
                progress_callback=lambda payload: emit({"event": _EVENT_PROGRESS, **payload}),
                should_cancel=cancel_event.is_set,
            )
            if cancel_event.is_set():
                state = _EVENT_CANCELLED
            elif result.success:
                state = _EVENT_COMPLETED
            else:
                state = _EVENT_FAILED
            emit(
                {
                    "event": state,
                    "output_dir": str(result.output_dir),
                    "indexed_file_count": result.indexed_file_count,
                    "indexed_chunk_count": result.indexed_chunk_count,
                    "skipped_file_count": result.skipped_file_count,
                    "warnings": [message.as_dict() for message in result.warnings],
                    "errors": [message.as_dict() for message in result.errors],
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface background errors to the UI.
            failure = messages.classify_embedding_failure(f"{type(exc).__name__}: {exc}")
            emit({"event": _EVENT_FAILED, "errors": [failure.as_dict()]})

    started_at = datetime.now(timezone.utc)
    thread = threading.Thread(target=run, name=f"vector-index-{vector_id}", daemon=True)
    job = VectorIndexJob(
        session_id=session_id,
        vector_id=vector_id,
        output_base=output_base,
        events=event_queue,
        cancel_event=cancel_event,
        thread=thread,
    )
    _register_job(
        VectorJobSnapshot(
            job=job,
            vector_id=vector_id,
            started_at=started_at,
            job_state=job_state_from_event(_EVENT_STARTED),
        )
    )
    thread.start()
    _logger.info("Indexing job started: session=%s vector=%s", session_id, vector_id)
    return job


def request_cancel(job: VectorIndexJob) -> None:
    """Request cooperative cancellation for a running indexing job."""
    job.cancel_event.set()
    _logger.info("Indexing job cancel requested: vector=%s", job.vector_id)
    cancel_event_dict: dict[str, object] = {
        "event": _EVENT_CANCEL_REQUESTED,
        "vector_id": job.vector_id,
    }
    job.events.put(cancel_event_dict)
    _update_snapshot(
        job.session_id, cancel_event_dict, job_state_from_event(_EVENT_CANCEL_REQUESTED)
    )


def drain_events(job: VectorIndexJob) -> list[dict[str, object]]:
    """Drain queued job events without blocking."""
    events: list[dict[str, object]] = []
    while True:
        try:
            events.append(job.events.get_nowait())
        except queue.Empty:
            return events


def job_state_from_event(event_name: str) -> str:
    """Map a worker event name to the user-facing job state."""
    states = {
        _EVENT_STARTED: "running",
        _EVENT_PROGRESS: "running",
        _EVENT_COMPLETED: "completed",
        _EVENT_FAILED: "failed",
        _EVENT_CANCEL_REQUESTED: "cancel_requested",
        _EVENT_CANCELLED: "cancelled",
    }
    return states.get(event_name, "running")


def vector_progress_fraction(
    stage: str, processed: int = 0, total: int = 0
) -> tuple[float, str] | None:
    """Return the progress-bar fraction and label key for an indexing stage.

    The bar is shown only when there is a real fraction to display: during
    embedding it equals the per-chunk ratio, so the bar matches the "Indexed X of
    Y chunks" caption exactly; during saving it sits at full. Every other stage —
    and embedding before any chunk counts arrive — returns ``None`` so the caller
    shows an indeterminate stage caption instead of a misleading partial bar.
    """
    if stage == STAGE_EMBEDDING and total > 0:
        return min(processed / total, 1.0), "VEC_STATUS_CHUNKS"
    if stage == STAGE_SAVING:
        return 1.0, "VEC_STAGE_SAVING"
    return None


def vector_stage_label_key(stage: str) -> str:
    """Return the i18n label key for *stage*'s indeterminate caption.

    Falls back to the generic running label when the stage is unknown (for example
    before the first stage event arrives).
    """
    return _VECTOR_STAGE_LABELS.get(stage, "VEC_STATUS_RUNNING")


def vector_eta_seconds(processed: int, total: int, elapsed_seconds: float) -> float | None:
    """Estimate the remaining indexing seconds from chunk progress and elapsed time.

    Returns ``None`` (no estimate yet) until there is enough signal — at least one
    processed chunk, more chunks still ahead, and non-zero elapsed time — so the
    caller can show an "estimating" placeholder.
    """
    if processed <= 0 or total <= 0 or processed >= total or elapsed_seconds <= 0:
        return None
    return elapsed_seconds * (total - processed) / processed


# Embedding error code -> app i18n hint key, ordered most specific first. The
# first matching error decides which actionable hint the UI shows below the
# error list.
_EMBEDDING_ERROR_HINT_KEYS: tuple[tuple[str, str], ...] = (
    (CODE_SSL_CERTIFICATE, "VEC_ERROR_SSL_HINT"),
    (CODE_MISSING_OPENAI_KEY, "VEC_ERROR_OPENAI_KEY_HINT"),
    (CODE_MISSING_AWS_CREDENTIALS, "VEC_ERROR_AWS_CREDENTIALS_HINT"),
    (CODE_EMBEDDING_FAILED, "VEC_ERROR_EMBEDDING_FAILED_HINT"),
    (CODE_MODEL_UNAVAILABLE, "VEC_ERROR_MODEL_UNAVAILABLE_HINT"),
)


def embedding_error_hint_key(errors: Sequence[Mapping[str, object]]) -> str | None:
    """Return the i18n hint key for the most specific embedding error, if any.

    Maps a structured ``vector_indexer`` error code to the app string key whose
    text tells the user what to do (set an API key, configure AWS credentials,
    check the network, or pick the local offline model). Returns ``None`` when no
    error carries an actionable hint.
    """
    codes = {str(error.get("code", "")) for error in errors}
    for code, hint_key in _EMBEDDING_ERROR_HINT_KEYS:
        if code in codes:
            return hint_key
    return None
