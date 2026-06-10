"""Plain data structures shared across the vector_indexer pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Chunk",
    "Document",
    "IndexingResult",
    "VectorRecord",
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


@dataclass(frozen=True)
class VectorRecord:
    """An embedded chunk ready to be written to a vector store."""

    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, str]


@dataclass
class IndexingResult:
    """Structured outcome of an indexing run that any UI can render."""

    success: bool
    output_dir: Path
    indexed_file_count: int = 0
    indexed_chunk_count: int = 0
    skipped_file_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
