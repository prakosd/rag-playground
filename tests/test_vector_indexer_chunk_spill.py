"""Tests for the chunk spill-to-disk helpers (PERF-M1 streaming)."""

from __future__ import annotations

from pathlib import Path

from vector_indexer.chunk_spill import read_chunk_batches, write_chunks
from vector_indexer.models import Chunk


def _chunk(i: int) -> Chunk:
    return Chunk(
        document_source="a.md",
        index=i,
        text=f"text {i}\nwith newline",
        metadata={"source": "a.md", "n": str(i)},
    )


def test_write_then_read_round_trips_chunks(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    total = write_chunks(path, [_chunk(i) for i in range(5)])
    assert total == 5

    read_back = [chunk for batch in read_chunk_batches(path, size=2) for chunk in batch]
    assert [c.text for c in read_back] == [f"text {i}\nwith newline" for i in range(5)]
    assert [c.index for c in read_back] == list(range(5))
    assert [c.metadata for c in read_back] == [{"source": "a.md", "n": str(i)} for i in range(5)]


def test_read_chunk_batches_respects_size(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    write_chunks(path, [_chunk(i) for i in range(5)])
    assert [len(batch) for batch in read_chunk_batches(path, size=2)] == [2, 2, 1]


def test_write_chunks_empty(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    assert write_chunks(path, []) == 0
    assert list(read_chunk_batches(path, size=2)) == []


def test_write_chunks_keeps_non_ascii_unescaped(tmp_path: Path) -> None:
    """Non-ASCII text is stored raw (ensure_ascii=False) so the spill stays compact and
    round-trips intact — Indonesian/Unicode content is a first-class use case."""
    path = tmp_path / "chunks.jsonl"
    text = "Ringkasan dokumen — kaféé 日本語"
    write_chunks(path, [Chunk(document_source="id.md", index=0, text=text, metadata={})])

    raw = path.read_text(encoding="utf-8")
    assert "日本語" in raw  # stored literally, not \\uXXXX-escaped
    assert "\\u" not in raw

    read_back = [c for batch in read_chunk_batches(path, size=10) for c in batch]
    assert read_back[0].text == text
