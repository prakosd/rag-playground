from __future__ import annotations

import pytest
from pydantic import ValidationError

from vector_indexer.config import IndexingConfig


def test_defaults_match_spec() -> None:
    config = IndexingConfig()

    assert config.chunk_size == 600
    assert config.chunk_overlap == 100
    assert config.embedding_dimension == 512
    assert config.language == "english"
    assert config.embedding_model == "amazon.titan-embed-text-v2:0"
    assert config.index_workers == 4


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError):
        IndexingConfig(chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValidationError):
        IndexingConfig(chunk_size=100, chunk_overlap=150)


def test_sizes_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        IndexingConfig(chunk_size=0)
    with pytest.raises(ValidationError):
        IndexingConfig(embedding_dimension=0)


def test_overlap_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        IndexingConfig(chunk_overlap=-1)


def test_index_workers_must_be_within_range() -> None:
    with pytest.raises(ValidationError):
        IndexingConfig(index_workers=0)
    with pytest.raises(ValidationError):
        IndexingConfig(index_workers=9)


def test_language_is_normalized() -> None:
    assert IndexingConfig(language="  English ").language == "english"


def test_unsupported_language_rejected() -> None:
    with pytest.raises(ValidationError):
        IndexingConfig(language="klingon")
