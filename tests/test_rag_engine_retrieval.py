from __future__ import annotations

from pathlib import Path

import pytest

from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.retrieval import retrieve
from vector_indexer import EmbeddingProviderUnavailable, ResolvedEmbedding


class _FakeDoc:
    def __init__(self, content: str, metadata: dict) -> None:
        self.page_content = content
        self.metadata = metadata


class _FakeStore:
    def __init__(self, hits: list) -> None:
        self._hits = hits

    def similarity_search_with_score(self, query: str, k: int) -> list:
        return self._hits[:k]


def _loader_ok(run_dir: Path | str):
    return ResolvedEmbedding(embeddings=object(), model_id="fake", dimension=4), []


def test_retrieve_returns_ranked_chunks() -> None:
    # Hits are (document, distance); the store returns raw distances which the
    # retriever maps to a 0-1 similarity (lower distance -> higher score).
    hits = [
        (_FakeDoc("hello", {"source": "a.md"}), 0.0),
        (_FakeDoc("world", {"source": "b.md"}), 1.0),
    ]

    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(top_k=2),
        embedding_loader=_loader_ok,
        store_opener=lambda run_dir, embeddings: _FakeStore(hits),
    )

    assert [chunk.source for chunk in result.chunks] == ["a.md", "b.md"]
    assert result.chunks[0].score == 1.0  # distance 0.0 -> perfect similarity
    assert result.chunks[1].score == 0.5  # distance 1.0 -> 1/(1+1)
    assert not result.errors


def test_retrieve_empty_warns_no_context() -> None:
    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(),
        embedding_loader=_loader_ok,
        store_opener=lambda run_dir, embeddings: _FakeStore([]),
    )

    assert result.chunks == []
    assert any(w.code == messages.CODE_NO_CONTEXT for w in result.warnings)


def test_retrieve_missing_index_reports_error() -> None:
    def loader(run_dir: Path | str):
        raise FileNotFoundError()

    result = retrieve("/tmp/missing", "q", RagConfig(), embedding_loader=loader)

    assert any(e.code == messages.CODE_INDEX_NOT_FOUND for e in result.errors)


def test_retrieve_embedding_unavailable_reports_error() -> None:
    def loader(run_dir: Path | str):
        raise EmbeddingProviderUnavailable("no chromadb")

    result = retrieve("/tmp/index", "q", RagConfig(), embedding_loader=loader)

    assert any(e.code == messages.CODE_EMBEDDING_UNAVAILABLE for e in result.errors)


def test_retrieve_store_failure_reports_error() -> None:
    def opener(run_dir: Path | str, embeddings: object):
        raise RuntimeError("boom")

    result = retrieve(
        "/tmp/index",
        "q",
        RagConfig(),
        embedding_loader=_loader_ok,
        store_opener=opener,
    )

    assert any(e.code == messages.CODE_RETRIEVAL_FAILED for e in result.errors)


def test_retrieve_real_index_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("langchain_chroma")
    from langchain_core.embeddings import Embeddings

    from vector_indexer import IndexingConfig, VectorIndexer

    class _FakeEmbeddings(Embeddings):
        # Unit vectors keep relevance scores within [0, 1] (as real, normalized
        # embedding models produce), mirroring production behaviour.
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    fake = _FakeEmbeddings()

    def resolver(model: str, dimension: int | None):
        return ResolvedEmbedding(embeddings=fake, model_id="fake", dimension=3), []

    source = tmp_path / "a.md"
    source.write_text("Paris is the capital of France. " * 10, encoding="utf-8")
    run = VectorIndexer(embedding_resolver=resolver).run(
        IndexingConfig(chunk_size=120, chunk_overlap=20), [source], tmp_path / "vec"
    )

    result = retrieve(
        run.output_dir,
        "France",
        RagConfig(top_k=2),
        embedding_loader=lambda run_dir: (
            ResolvedEmbedding(embeddings=fake, model_id="fake", dimension=3),
            [],
        ),
    )

    assert result.chunks
    assert any("Paris" in chunk.text for chunk in result.chunks)
