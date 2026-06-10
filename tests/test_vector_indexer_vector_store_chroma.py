from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("chromadb")

from vector_indexer.models import VectorRecord  # noqa: E402
from vector_indexer.vector_store.chroma import ChromaVectorStore  # noqa: E402


def test_chroma_store_persists_records(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    store = ChromaVectorStore(persist_dir)
    store.create_collection("crawl4md_documents")
    store.add_documents(
        [
            VectorRecord(
                id="1", text="hello", embedding=[0.1, 0.2, 0.3], metadata={"source": "a.md"}
            ),
            VectorRecord(
                id="2", text="world", embedding=[0.4, 0.5, 0.6], metadata={"source": "b.md"}
            ),
        ]
    )
    store.persist()

    assert (persist_dir / "chroma.sqlite3").exists()
    assert store._collection.count() == 2


def test_add_documents_requires_collection(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(RuntimeError):
        store.add_documents(
            [VectorRecord(id="1", text="x", embedding=[0.1], metadata={"source": "a"})]
        )
