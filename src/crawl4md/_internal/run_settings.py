"""Crawl run settings file: the JSON record of what a crawl was configured with.

Written once at the start of each crawl run so a user can see (and reproduce) the
exact crawl parameters — crawler + page config, including advanced options —
without reading them out of each content file's header. Mirrors how
``vector_indexer`` writes ``manifest.json`` beside a vector index.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from log4py import get_logger

__all__ = ["SETTINGS_FILENAME", "write_crawl_settings"]

_logger = get_logger(__name__)

SETTINGS_FILENAME = "settings.json"
_SCHEMA_VERSION = 1


def write_crawl_settings(output_dir: Path, run_metadata: Mapping[str, Any]) -> Path | None:
    """Write the crawl's settings to ``settings.json`` inside *output_dir*.

    Returns the path written, or ``None`` when the write failed (the crawl still
    proceeds — the file is informational). Credentials are already excluded
    upstream (``secret_headers``/``proxies`` are not serialized into
    ``run_metadata``), so no secret reaches this file.
    """
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "crawl_start_datetime": run_metadata.get("crawl_start_datetime"),
        "session_id": run_metadata.get("session_id"),
        "crawl_parameters": run_metadata.get("crawl_parameters", {}),
    }
    path = output_dir / SETTINGS_FILENAME
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        _logger.warning("Could not write crawl settings file: %s", exc)
        return None
    _logger.info("Wrote crawl settings file: %s", path)
    return path
