from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_chroma")

from langchain_core.embeddings import Embeddings  # noqa: E402

from vector_indexer.manifest import DEFAULT_COLLECTION_NAME  # noqa: E402
from vector_indexer.vector_store.chroma import ChromaVectorStore  # noqa: E402


class _FakeEmbeddings(Embeddings):
    """Deterministic embeddings so the store never downloads a model."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0, 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 0.0, 1.0]


def test_chroma_store_persists_texts(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    store = ChromaVectorStore(persist_dir, DEFAULT_COLLECTION_NAME, _FakeEmbeddings())

    store.add_texts(
        texts=["hello", "world"],
        metadatas=[{"source": "a.md"}, {"source": "b.md"}],
        ids=["1", "2"],
    )
    store.persist()

    assert (persist_dir / "chroma.sqlite3").exists()

    from chromadb.config import Settings
    from langchain_chroma import Chroma

    reopened = Chroma(
        collection_name=DEFAULT_COLLECTION_NAME,
        embedding_function=_FakeEmbeddings(),
        persist_directory=str(persist_dir),
        client_settings=Settings(anonymized_telemetry=False),
    )
    assert len(reopened.get()["ids"]) == 2


def test_add_texts_empty_is_noop(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    store = ChromaVectorStore(persist_dir, DEFAULT_COLLECTION_NAME, _FakeEmbeddings())

    store.add_texts(texts=[], metadatas=[], ids=[])

    # An empty batch must not touch the backend or create the persist directory.
    assert not persist_dir.exists()
