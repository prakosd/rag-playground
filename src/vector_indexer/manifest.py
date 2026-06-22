"""Run manifest: the JSON record written beside each vector index.

The manifest lets a reader (the retrieval layer) reopen an index without
guessing: it records which embedding model and dimension produced the vectors
and which collection name holds them. ``write_manifest`` persists the payload
the indexer assembles; ``load_manifest`` parses it back into a typed object.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "CHROMA_SUBDIR",
    "DEFAULT_COLLECTION_NAME",
    "MANIFEST_NAME",
    "IndexManifest",
    "load_manifest",
    "write_manifest",
]

# Collection name and on-disk layout shared by the writer (indexer) and the
# reader (retrieval layer) so an index can be reopened from its run directory.
DEFAULT_COLLECTION_NAME = "crawl4md_documents"
CHROMA_SUBDIR = "chroma"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class IndexManifest:
    """Typed view of a run ``manifest.json`` for the retrieval layer."""

    embedding_model_requested: str | None
    embedding_model_used: str | None
    embedding_dimension: int | None
    collection_name: str
    chunk_size: int | None
    chunk_overlap: int | None
    language: str | None
    success: bool
    indexed_file_count: int
    indexed_chunk_count: int
    skipped_file_count: int
    created_at: str | None = None


def write_manifest(run_dir: Path | str, payload: dict[str, Any]) -> None:
    """Write *payload* as ``manifest.json`` inside *run_dir* (best effort)."""
    with contextlib.suppress(OSError):
        (Path(run_dir) / MANIFEST_NAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def load_manifest(run_dir: Path | str) -> IndexManifest:
    """Read and parse the ``manifest.json`` inside *run_dir*.

    Raises ``FileNotFoundError`` when no manifest exists and ``ValueError`` when
    it is not valid JSON.
    """
    path = Path(run_dir) / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    return IndexManifest(
        embedding_model_requested=data.get("embedding_model_requested"),
        embedding_model_used=data.get("embedding_model_used"),
        embedding_dimension=data.get("embedding_dimension"),
        collection_name=data.get("collection_name") or DEFAULT_COLLECTION_NAME,
        chunk_size=data.get("chunk_size"),
        chunk_overlap=data.get("chunk_overlap"),
        language=data.get("language"),
        success=bool(data.get("success", False)),
        indexed_file_count=int(data.get("indexed_file_count", 0)),
        indexed_chunk_count=int(data.get("indexed_chunk_count", 0)),
        skipped_file_count=int(data.get("skipped_file_count", 0)),
        created_at=data.get("created_at"),
    )
