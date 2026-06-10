from __future__ import annotations

from vector_indexer.chunking import chunk_documents
from vector_indexer.models import Document


def test_chunking_respects_size_and_records_metadata() -> None:
    text = "abcdefghij" * 30  # 300 characters with no natural separators
    documents = [Document(source="a.md", text=text)]

    chunks = chunk_documents(documents, chunk_size=100, chunk_overlap=20, language="english")

    assert len(chunks) >= 3
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.metadata["language"] == "english" for chunk in chunks)
    assert all(chunk.metadata["source"] == "a.md" for chunk in chunks)


def test_chunking_drops_empty_documents() -> None:
    chunks = chunk_documents(
        [Document(source="x.md", text="   ")],
        chunk_size=100,
        chunk_overlap=10,
        language="english",
    )

    assert chunks == []
