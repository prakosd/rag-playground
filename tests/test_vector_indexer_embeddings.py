from __future__ import annotations

import pytest

from vector_indexer import messages
from vector_indexer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LOCAL_MODEL,
    DISABLED_MODELS,
    OPENAI_MODEL,
    TITAN_MODEL,
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    build_embeddings,
    resolve_embedding,
)


def _resolved(model_id: str, dimension: int) -> ResolvedEmbedding:
    # The embeddings client is never called during resolution, so a sentinel
    # stands in for a real LangChain ``Embeddings`` object.
    return ResolvedEmbedding(embeddings=object(), model_id=model_id, dimension=dimension)


def test_disabled_models_fail_gracefully() -> None:
    for model in DISABLED_MODELS:
        with pytest.raises(EmbeddingProviderUnavailable):
            build_embeddings(model)


def test_unknown_model_fails_gracefully() -> None:
    with pytest.raises(EmbeddingProviderUnavailable):
        build_embeddings("nonexistent/model")


def test_titan_without_credentials_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(EmbeddingProviderUnavailable):
        build_embeddings(TITAN_MODEL)


def test_openai_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EmbeddingProviderUnavailable):
        build_embeddings(OPENAI_MODEL)


def test_default_model_falls_back_to_offline() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        raise EmbeddingProviderUnavailable("titan unavailable")

    def offline_build(*, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("offline", 384)

    resolved, warnings = resolve_embedding(
        DEFAULT_EMBEDDING_MODEL, 512, build=failing_build, default_build=offline_build
    )

    assert resolved.model_id == "offline"
    assert any(warning.code == messages.CODE_EMBEDDING_FALLBACK for warning in warnings)
    assert any("offline" in str(warning).lower() for warning in warnings)


def test_non_default_unavailable_model_falls_back_to_offline() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        raise EmbeddingProviderUnavailable("openai unavailable")

    def offline_build(*, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("offline", 384)

    resolved, warnings = resolve_embedding(
        OPENAI_MODEL, 512, build=failing_build, default_build=offline_build
    )

    assert resolved.model_id == "offline"
    assert any(warning.code == messages.CODE_EMBEDDING_FALLBACK for warning in warnings)
    assert any("offline" in str(warning).lower() for warning in warnings)


def test_available_model_resolves_without_warnings() -> None:
    def build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved(model, dimension or 384)

    def offline_build(*, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("offline", 384)

    resolved, warnings = resolve_embedding(
        OPENAI_MODEL, 384, build=build, default_build=offline_build
    )

    assert resolved.model_id == OPENAI_MODEL
    assert warnings == []


def test_requested_local_model_failure_raises() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        raise EmbeddingProviderUnavailable("chromadb missing")

    def offline_build(*, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("offline", 384)

    with pytest.raises(EmbeddingProviderUnavailable):
        resolve_embedding(
            DEFAULT_LOCAL_MODEL, 384, build=failing_build, default_build=offline_build
        )


def test_fallback_failure_raises_combined_error() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        raise EmbeddingProviderUnavailable("titan unavailable")

    def failing_offline(*, dimension: int | None = None) -> ResolvedEmbedding:
        raise EmbeddingProviderUnavailable("chromadb missing")

    with pytest.raises(EmbeddingProviderUnavailable) as exc_info:
        resolve_embedding(OPENAI_MODEL, 512, build=failing_build, default_build=failing_offline)

    message = str(exc_info.value)
    assert "titan unavailable" in message
    assert "chromadb missing" in message


def test_dimension_mismatch_adds_warning() -> None:
    def build(model: str, *, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("fixed", 384)

    def offline_build(*, dimension: int | None = None) -> ResolvedEmbedding:
        return _resolved("offline", 384)

    resolved, warnings = resolve_embedding("fixed", 512, build=build, default_build=offline_build)

    assert resolved.dimension == 384
    assert any(warning.code == messages.CODE_DIMENSION_MISMATCH for warning in warnings)
    assert any("dimension" in str(warning).lower() for warning in warnings)
