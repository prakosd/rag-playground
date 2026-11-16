"""Spill chunks to a temporary JSONL and stream them back in batches.

Lets the indexer process a large corpus with bounded memory: the chunking pass writes each
chunk to disk (so documents + chunks are never all held at once) and records the total count;
the embedding pass reads the spill back in fixed-size batches. The spill file lives inside the
run directory and is removed when indexing finishes.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from vector_indexer.models import Chunk

__all__ = ["read_chunk_batches", "write_chunks"]


def write_chunks(path: Path, chunks: Iterable[Chunk]) -> int:
    """Write *chunks* to *path* as JSON lines, returning the number written."""
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "document_source": chunk.document_source,
                        "index": chunk.index,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    },
                    ensure_ascii=False,
                )
            )
            handle.write("\n")
            written += 1
    return written


def read_chunk_batches(path: Path, size: int) -> Iterator[list[Chunk]]:
    """Yield chunks read back from *path* in batches of at most *size* (bounded memory)."""
    batch: list[Chunk] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            data = json.loads(line)
            batch.append(
                Chunk(
                    document_source=data["document_source"],
                    index=data["index"],
                    text=data["text"],
                    metadata=data["metadata"],
                )
            )
            if len(batch) >= size:
                yield batch
                batch = []
    if batch:
        yield batch
