"""Background vector indexing job helpers for the crawl4md Streamlit app.

Mirrors the crawl job pattern: an indexing run executes in a daemon thread,
emits progress events through a queue, and supports cooperative cancellation.
The heavy lifting lives in the UI-independent :mod:`vector_indexer` library.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vector_indexer import IndexingConfig, VectorIndexer
from vector_indexer.indexer import (
    STAGE_CHUNKING,
    STAGE_EMBEDDING,
    STAGE_LOADING,
    STAGE_RESOLVING_MODEL,
    STAGE_SAVING,
)

from crawl4md_streamlit.session_manager import DEFAULT_SESSIONS_ROOT, prepare_vector_output_base

_EVENT_STARTED = "started"
_EVENT_PROGRESS = "progress"
_EVENT_COMPLETED = "completed"
_EVENT_FAILED = "failed"
_EVENT_CANCELLED = "cancelled"
_EVENT_CANCEL_REQUESTED = "cancel_requested"

_UPLOAD_DIR_NAME = "uploads"

# Coarse (fraction, i18n label key) per pipeline stage for the progress bar.
# Embedding maps its per-chunk ratio into a band that ends just below the saving
# fraction so the bar advances monotonically across stages.
_VECTOR_STAGE_PROGRESS: dict[str, tuple[float, str]] = {
    STAGE_RESOLVING_MODEL: (0.05, "VEC_STAGE_RESOLVING_MODEL"),
    STAGE_LOADING: (0.15, "VEC_STAGE_LOADING"),
    STAGE_CHUNKING: (0.25, "VEC_STAGE_CHUNKING"),
    STAGE_EMBEDDING: (0.30, "VEC_STAGE_EMBEDDING"),
    STAGE_SAVING: (0.97, "VEC_STAGE_SAVING"),
}
_VECTOR_EMBED_SPAN = 0.65
_SSL_ERROR_SIGNATURES = (
    "certificate_verify_failed",
    "certificate verify failed",
    "self-signed certificate",
)


@dataclass(frozen=True)
class VectorIndexJob:
    """Background vector-index job state shared with the Streamlit session."""

    session_id: str
    vector_id: str
    output_base: Path
    events: queue.Queue[dict[str, object]]
    cancel_event: threading.Event
    thread: threading.Thread


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

    def run() -> None:
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
                    "warnings": list(result.warnings),
                    "errors": list(result.errors),
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface background errors to the UI.
            emit({"event": _EVENT_FAILED, "errors": [f"{type(exc).__name__}: {exc}"]})

    thread = threading.Thread(target=run, name=f"vector-index-{vector_id}", daemon=True)
    job = VectorIndexJob(
        session_id=session_id,
        vector_id=vector_id,
        output_base=output_base,
        events=event_queue,
        cancel_event=cancel_event,
        thread=thread,
    )
    thread.start()
    return job


def request_cancel(job: VectorIndexJob) -> None:
    """Request cooperative cancellation for a running indexing job."""
    job.cancel_event.set()
    job.events.put({"event": _EVENT_CANCEL_REQUESTED, "vector_id": job.vector_id})


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

    Returns ``None`` when *stage* is unknown (no stage reported yet) so the caller
    can fall back to a generic message. During embedding the per-chunk ratio is
    mapped into the embedding band and reported with the chunk-count label.
    """
    base = _VECTOR_STAGE_PROGRESS.get(stage)
    if base is None:
        return None
    fraction, label_key = base
    if stage == STAGE_EMBEDDING and total > 0:
        ratio = min(processed / total, 1.0)
        return fraction + _VECTOR_EMBED_SPAN * ratio, "VEC_STATUS_CHUNKS"
    return fraction, label_key


def has_ssl_certificate_error(errors: Sequence[str]) -> bool:
    """Return True when any error looks like a TLS certificate verification failure."""
    lowered = " ".join(errors).lower()
    return any(signature in lowered for signature in _SSL_ERROR_SIGNATURES)
