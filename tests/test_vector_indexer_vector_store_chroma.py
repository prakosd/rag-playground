from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_chroma")

from langchain_core.embeddings import Embeddings  # noqa: E402

from vector_indexer.manifest import CHROMA_SUBDIR, DEFAULT_COLLECTION_NAME  # noqa: E402
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

    texts = ["hello", "world"]
    store.add_embeddings(
        texts=texts,
        embeddings=_FakeEmbeddings().embed_documents(texts),
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


def test_add_embeddings_empty_is_noop(tmp_path: Path) -> None:
    persist_dir = tmp_path / "chroma"
    store = ChromaVectorStore(persist_dir, DEFAULT_COLLECTION_NAME, _FakeEmbeddings())

    store.add_embeddings(texts=[], embeddings=[], metadatas=[], ids=[])

    # An empty batch must not touch the backend or create the persist directory.
    assert not persist_dir.exists()


def test_indexer_parallel_workers_write_all_chunks(tmp_path: Path) -> None:
    """Regression: index_workers > 1 must not corrupt or lock the Chroma store."""
    from vector_indexer.config import IndexingConfig
    from vector_indexer.embeddings import ResolvedEmbedding
    from vector_indexer.indexer import VectorIndexer

    source = tmp_path / "doc.md"
    source.write_text("hello world " * 4000, encoding="utf-8")

    def resolver(model: str, dimension: int | None) -> tuple[ResolvedEmbedding, list]:
        embedding = ResolvedEmbedding(
            embeddings=_FakeEmbeddings(), model_id="cloud-fake", dimension=3
        )
        return embedding, []

    # The default factory builds the real ChromaVectorStore; a non-local model id
    # keeps index_workers > 1 active, exercising concurrent writes to one store.
    indexer = VectorIndexer(embedding_resolver=resolver)
    result = indexer.run(
        IndexingConfig(chunk_size=120, chunk_overlap=20, index_workers=4),
        [source],
        tmp_path / "vector_01_demo",
    )

    assert result.success
    assert result.indexed_chunk_count > 1

    from chromadb.config import Settings
    from langchain_chroma import Chroma

    reopened = Chroma(
        collection_name=DEFAULT_COLLECTION_NAME,
        embedding_function=_FakeEmbeddings(),
        persist_directory=str(result.output_dir / CHROMA_SUBDIR),
        client_settings=Settings(anonymized_telemetry=False),
    )
    assert len(reopened.get()["ids"]) == result.indexed_chunk_count
