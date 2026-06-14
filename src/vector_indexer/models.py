"""Plain data structures shared across the vector_indexer pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from artifact_store import LibraryMessage

__all__ = [
    "Chunk",
    "Document",
    "IndexingResult",
]


@dataclass(frozen=True)
class Document:
    """A single text document loaded from a file or archive member."""

    source: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """A contiguous slice of a document prepared for embedding."""

    document_source: str
    index: int
    text: str
    metadata: dict[str, str]


@dataclass
class IndexingResult:
    """Structured outcome of an indexing run that any UI can render.

    ``warnings`` and ``errors`` are :class:`~artifact_store.LibraryMessage`
    objects carrying a stable ``code`` plus structured ``params``; ``str()`` of
    each yields its English ``default_text`` for UIs without localization.
    """

    success: bool
    output_dir: Path
    indexed_file_count: int = 0
    indexed_chunk_count: int = 0
    skipped_file_count: int = 0
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)
