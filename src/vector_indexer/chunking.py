"""Splits documents into overlapping chunks via langchain-text-splitters.

The language hint is recorded as chunk metadata; it does not change the split
boundaries (Lucene analyzer languages are unrelated to code-aware splitting).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vector_indexer.models import Chunk, Document

__all__ = ["chunk_documents"]


def chunk_documents(
    documents: Sequence[Document],
    *,
    chunk_size: int,
    chunk_overlap: int,
    language: str,
) -> list[Chunk]:
    """Split *documents* into overlapping chunks, dropping empty fragments."""
    splitter = _build_splitter(chunk_size, chunk_overlap)
    chunks: list[Chunk] = []
    for document in documents:
        pieces = splitter.split_text(document.text)
        for index, piece in enumerate(pieces):
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    document_source=document.source,
                    index=index,
                    text=piece,
                    metadata={
                        "source": document.source,
                        "chunk_index": str(index),
                        "language": language,
                    },
                )
            )
    return chunks


def _build_splitter(chunk_size: int, chunk_overlap: int) -> Any:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "langchain-text-splitters is required for chunking. Install it with: "
            'pip install "rag-playground[vector]"'
        ) from exc
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
