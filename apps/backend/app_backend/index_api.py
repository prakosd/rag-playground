"""HTTP routes for index jobs (Step 2): a streaming index run plus cooperative cancel.

Mirrors the crawl job API for vector indexing, reusing the shared
:mod:`app_backend.job_stream` scaffold. The run executes ``VectorIndexer.run()`` in a
background thread writing the Chroma index under the artifacts root; the input paths and the
output base arrive relative and are resolved under the root (containment), so uploads the
frontend wrote to shared storage are read in place. ``VectorIndexer`` is imported lazily, so
the backend module loads without the ``[vector]`` extra until an index is requested.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app_backend.config import resolve_within_artifacts
from app_backend.job_stream import SENTINEL, cancel_job, stream_job

router = APIRouter(prefix="/index", tags=["index"])


class IndexRequest(BaseModel):
    output_base: str
    input_paths: list[str] = []
    config: dict[str, Any] = {}


@router.post("")
def index(request: IndexRequest) -> StreamingResponse:
    """Run an indexing job in a background thread, streaming its progress as NDJSON.

    The first frame is ``{"job_id": ...}`` (used to cancel). Subsequent frames are
    ``{"event": {"event": "progress", ...}}`` as the indexer reports, then a final
    ``{"result": {...}}`` frame carries the counts, the output directory's name, success,
    and any warnings/errors so the frontend builds its terminal event with its own paths.
    """
    try:
        from vector_indexer import IndexingConfig, VectorIndexer  # lazy: needs the [vector] extra
    except ImportError as exc:  # pragma: no cover - deployment without the vector extra
        raise HTTPException(status_code=503, detail=f"vector extra not installed: {exc}") from exc

    output_base = resolve_within_artifacts(request.output_base)
    inputs = [str(resolve_within_artifacts(path)) for path in request.input_paths]
    config = IndexingConfig.model_validate(request.config)

    def worker(events: queue.Queue[object], cancel_event: threading.Event) -> None:
        try:
            result = VectorIndexer().run(
                config,
                inputs,
                output_base,
                progress_callback=lambda payload: events.put(
                    {"event": {"event": "progress", **payload}}
                ),
                should_cancel=cancel_event.is_set,
            )
            events.put(
                {
                    "result": {
                        "success": result.success,
                        "output_dir_name": Path(result.output_dir).name
                        if result.output_dir
                        else "",
                        "indexed_file_count": result.indexed_file_count,
                        "indexed_chunk_count": result.indexed_chunk_count,
                        "skipped_file_count": result.skipped_file_count,
                        "warnings": [message.as_dict() for message in result.warnings],
                        "errors": [message.as_dict() for message in result.errors],
                        "cancelled": cancel_event.is_set(),
                    }
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface worker errors as a final frame
            events.put({"result": {"error": f"{type(exc).__name__}: {exc}"}})
        finally:
            events.put(SENTINEL)

    return stream_job(worker, name="backend-index")


@router.post("/{job_id}/cancel")
def cancel(job_id: str) -> dict[str, bool]:
    """Request cooperative cancellation of a running index job."""
    return cancel_job(job_id)
