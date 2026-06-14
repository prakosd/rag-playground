from __future__ import annotations

from collections.abc import Sequence

import pytest

from vector_indexer import messages
from vector_indexer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LOCAL_MODEL,
    DISABLED_MODELS,
    OPENAI_MODEL,
    TITAN_MODEL,
    EmbeddingProvider,
    EmbeddingProviderUnavailable,
    build_embedding_provider,
    resolve_embedding,
)


class _FakeProvider(EmbeddingProvider):
    def __init__(self, model_id: str, dimension: int) -> None:
        self._model_id = model_id
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * self._dimension for _ in texts]


def test_disabled_models_fail_gracefully() -> None:
    for model in DISABLED_MODELS:
        with pytest.raises(EmbeddingProviderUnavailable):
            build_embedding_provider(model)


def test_unknown_model_fails_gracefully() -> None:
    with pytest.raises(EmbeddingProviderUnavailable):
        build_embedding_provider("nonexistent/model")


def test_titan_without_credentials_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(EmbeddingProviderUnavailable):
        build_embedding_provider(TITAN_MODEL)


def test_openai_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EmbeddingProviderUnavailable):
        build_embedding_provider(OPENAI_MODEL)


def test_default_model_falls_back_to_offline() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        raise EmbeddingProviderUnavailable("titan unavailable")

    def offline_build(*, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("offline", 384)

    provider, warnings = resolve_embedding(
        DEFAULT_EMBEDDING_MODEL, 512, build=failing_build, default_build=offline_build
    )

    assert provider.model_id == "offline"
    assert any(warning.code == messages.CODE_EMBEDDING_FALLBACK for warning in warnings)
    assert any("offline" in str(warning).lower() for warning in warnings)


def test_non_default_unavailable_model_falls_back_to_offline() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        raise EmbeddingProviderUnavailable("openai unavailable")

    def offline_build(*, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("offline", 384)

    provider, warnings = resolve_embedding(
        OPENAI_MODEL, 512, build=failing_build, default_build=offline_build
    )

    assert provider.model_id == "offline"
    assert any(warning.code == messages.CODE_EMBEDDING_FALLBACK for warning in warnings)
    assert any("offline" in str(warning).lower() for warning in warnings)


def test_available_model_resolves_without_warnings() -> None:
    def build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider(model, dimension or 384)

    def offline_build(*, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("offline", 384)

    provider, warnings = resolve_embedding(
        OPENAI_MODEL, 384, build=build, default_build=offline_build
    )

    assert provider.model_id == OPENAI_MODEL
    assert warnings == []


def test_requested_local_model_failure_raises() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        raise EmbeddingProviderUnavailable("chromadb missing")

    def offline_build(*, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("offline", 384)

    with pytest.raises(EmbeddingProviderUnavailable):
        resolve_embedding(
            DEFAULT_LOCAL_MODEL, 384, build=failing_build, default_build=offline_build
        )


def test_fallback_failure_raises_combined_error() -> None:
    def failing_build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        raise EmbeddingProviderUnavailable("titan unavailable")

    def failing_offline(*, dimension: int | None = None) -> EmbeddingProvider:
        raise EmbeddingProviderUnavailable("chromadb missing")

    with pytest.raises(EmbeddingProviderUnavailable) as exc_info:
        resolve_embedding(OPENAI_MODEL, 512, build=failing_build, default_build=failing_offline)

    message = str(exc_info.value)
    assert "titan unavailable" in message
    assert "chromadb missing" in message


def test_dimension_mismatch_adds_warning() -> None:
    def build(model: str, *, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("fixed", 384)

    def offline_build(*, dimension: int | None = None) -> EmbeddingProvider:
        return _FakeProvider("offline", 384)

    provider, warnings = resolve_embedding("fixed", 512, build=build, default_build=offline_build)

    assert provider.dimension == 384
    assert any(warning.code == messages.CODE_DIMENSION_MISMATCH for warning in warnings)
    assert any("dimension" in str(warning).lower() for warning in warnings)
