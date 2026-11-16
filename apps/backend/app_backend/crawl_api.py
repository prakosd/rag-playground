"""HTTP routes for crawl jobs (Step 1): a streaming crawl plus cooperative cancel.

The crawl runs in a background thread (via the shared :mod:`app_backend.job_stream`
scaffold) writing Markdown under the configured artifacts root; its progress events stream
back as newline-delimited JSON, and a cancel endpoint (keyed by the ``job_id`` sent in the
first frame) requests a cooperative stop. The frontend relays the ``event`` frames to its
existing progress UI and builds its own terminal event from the final ``result`` frame
(keeping the app-specific error classification + output path on the app side). ``SiteCrawler``
is imported lazily, so the backend module loads without the ``[crawl]`` extra until a crawl
is requested.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from artifact_store import ensure_within_root
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app_backend.config import get_backend_settings
from app_backend.job_stream import SENTINEL, cancel_job, stream_job

router = APIRouter(prefix="/crawl", tags=["crawl"])


class CrawlRequest(BaseModel):
    output_base: str
    crawler_config: dict[str, Any] = {}
    page_config: dict[str, Any] = {}
    activity_log_size: int = 10


def _resolve_output_base(output_base: str) -> Path:
    root = Path(get_backend_settings().artifacts_root).resolve()
    try:
        return ensure_within_root(root, root / output_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# page_config keys that execute arbitrary script in the headless browser (SEC-M1).
_SCRIPT_PAGE_CONFIG_KEYS = ("js_code",)


def _sanitize_page_config(page_config: dict[str, Any]) -> dict[str, Any]:
    """Drop script-injection keys from an incoming ``page_config`` unless opted in.

    The backend accepts an arbitrary ``page_config``; ``js_code`` would run attacker-supplied
    JavaScript in the server's headless browser. Networked deployments must not expose that
    by default, so the keys are removed unless ``ALLOW_PAGE_SCRIPTS`` is set. The in-process
    library caller builds its own ``PageConfig`` and is unaffected.
    """
    if get_backend_settings().allow_page_scripts:
        return page_config
    return {key: value for key, value in page_config.items() if key not in _SCRIPT_PAGE_CONFIG_KEYS}


@router.post("")
def crawl(request: CrawlRequest) -> StreamingResponse:
    """Run a crawl in a background thread, streaming its progress events as NDJSON.

    The first frame is ``{"job_id": ...}`` (used to cancel). Subsequent frames are
    ``{"event": <crawl event>}`` exactly as the crawler emits them, then a final
    ``{"result": {...}}`` frame carries the page counts, the output directory's name, and
    any crawl error so the frontend can build its terminal event with its own paths.
    """
    try:
        from crawl4md import CrawlerConfig, PageConfig  # lazy: needs the [crawl] extra
        from crawl4md.crawler import SiteCrawler
    except ImportError as exc:  # pragma: no cover - deployment without the crawl extra
        raise HTTPException(status_code=503, detail=f"crawl extra not installed: {exc}") from exc

    output_base = _resolve_output_base(request.output_base)
    crawler_config = CrawlerConfig.model_validate(request.crawler_config)
    if get_backend_settings().block_private_networks:
        # Force the SSRF guard on regardless of the incoming config (defense in depth).
        crawler_config = crawler_config.model_copy(update={"block_private_networks": True})
    page_config = PageConfig.model_validate(_sanitize_page_config(request.page_config))

    def worker(events: queue.Queue[object], cancel_event: threading.Event) -> None:
        try:
            crawler = SiteCrawler(
                crawler_config,
                page_config,
                output_base=output_base,
                activity_log_size=request.activity_log_size,
                progress_callback=lambda event: events.put({"event": dict(event)}),
                should_cancel=cancel_event.is_set,
            )
            results = crawler.crawl()
            success = sum(1 for result in results if result.success)
            events.put(
                {
                    "result": {
                        "processed_pages": len(results),
                        "successful_pages": success,
                        "failed_pages": len(results) - success,
                        "output_dir_name": Path(crawler.output_dir).name
                        if crawler.output_dir
                        else "",
                        "crawl_error": crawler.crawl_error,
                        "cancelled": cancel_event.is_set(),
                    }
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface worker errors as a final frame
            events.put({"result": {"error": str(exc)}})
        finally:
            events.put(SENTINEL)

    return stream_job(worker, name="backend-crawl")


@router.post("/{job_id}/cancel")
def cancel(job_id: str) -> dict[str, bool]:
    """Request cooperative cancellation of a running crawl job."""
    return cancel_job(job_id)
