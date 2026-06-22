"""Splits documents into overlapping chunks via langchain-text-splitters.

The language hint is recorded as chunk metadata; it does not change the split
boundaries (Lucene analyzer languages are unrelated to code-aware splitting).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vector_indexer.models import Chunk, Document
from vector_indexer.page_source import format_source_line, split_into_pages

__all__ = ["chunk_documents"]


def chunk_documents(
    documents: Sequence[Document],
    *,
    chunk_size: int,
    chunk_overlap: int,
    language: str,
) -> list[Chunk]:
    """Split *documents* into overlapping chunks, dropping empty fragments.

    Run metadata (the crawl4md front matter) is excluded, and every chunk is
    stamped with a ``Source: [title](url)`` line recovered from its page header.
    """
    splitter = _build_splitter(chunk_size, chunk_overlap)
    chunks: list[Chunk] = []
    for document in documents:
        index = 0
        for page in split_into_pages(document.text):
            source_line = format_source_line(page.title, page.url)
            for piece in splitter.split_text(page.body):
                if not piece.strip():
                    continue
                metadata = {
                    "source": document.source,
                    "chunk_index": str(index),
                    "language": language,
                }
                if page.title:
                    metadata["source_title"] = page.title
                if page.url:
                    metadata["source_url"] = page.url
                chunks.append(
                    Chunk(
                        document_source=document.source,
                        index=index,
                        text=f"{source_line}\n\n{piece}" if source_line else piece,
                        metadata=metadata,
                    )
                )
                index += 1
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
