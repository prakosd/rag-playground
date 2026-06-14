"""Discover usable vector indexes inside a Streamlit session directory.

Vector-index runs are written by Step 2 under
``session_<id>/vector_<id>/<timestamp>/`` with a ``manifest.json`` and a
``chroma`` subdirectory. This pure helper scans a session root and returns the
indexes that are ready to query (successful, non-empty), newest first, so Steps
3-5 can offer an index picker. It has no Streamlit dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from artifact_store.naming import VECTOR_FOLDER_PREFIX
from vector_indexer import CHROMA_SUBDIR, IndexManifest, load_manifest

__all__ = ["IndexRef", "list_session_indexes"]


@dataclass(frozen=True)
class IndexRef:
    """A queryable vector index discovered in a session directory."""

    run_dir: Path
    vector_folder: str
    run_name: str
    manifest: IndexManifest


def list_session_indexes(session_root: Path | str) -> list[IndexRef]:
    """Return the queryable indexes under *session_root*, newest first."""
    root = Path(session_root)
    if not root.is_dir():
        return []
    refs = [ref for folder in _vector_folders(root) for ref in _indexes_in(folder)]
    refs.sort(key=lambda ref: (ref.run_name, ref.vector_folder), reverse=True)
    return refs


def _vector_folders(root: Path) -> Iterable[Path]:
    return (
        child
        for child in root.iterdir()
        if child.is_dir() and child.name.startswith(VECTOR_FOLDER_PREFIX)
    )


def _indexes_in(vector_folder: Path) -> Iterable[IndexRef]:
    for run_dir in vector_folder.iterdir():
        if not run_dir.is_dir() or not (run_dir / CHROMA_SUBDIR).is_dir():
            continue
        try:
            manifest = load_manifest(run_dir)
        except (OSError, ValueError):
            continue
        if not manifest.success or manifest.indexed_chunk_count <= 0:
            continue
        yield IndexRef(
            run_dir=run_dir,
            vector_folder=vector_folder.name,
            run_name=run_dir.name,
            manifest=manifest,
        )
