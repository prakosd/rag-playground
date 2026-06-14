from __future__ import annotations

import json
from pathlib import Path

import pytest

from vector_indexer.manifest import (
    DEFAULT_COLLECTION_NAME,
    MANIFEST_NAME,
    IndexManifest,
    load_manifest,
    write_manifest,
)


def test_write_then_load_round_trip(tmp_path: Path) -> None:
    payload = {
        "embedding_model_requested": "amazon.titan-embed-text-v2:0",
        "embedding_model_used": "all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "collection_name": "docs",
        "chunk_size": 600,
        "chunk_overlap": 100,
        "language": "english",
        "success": True,
        "indexed_file_count": 2,
        "indexed_chunk_count": 10,
        "skipped_file_count": 1,
    }
    write_manifest(tmp_path, payload)

    manifest = load_manifest(tmp_path)
    assert isinstance(manifest, IndexManifest)
    assert manifest.embedding_model_used == "all-MiniLM-L6-v2"
    assert manifest.embedding_dimension == 384
    assert manifest.collection_name == "docs"
    assert manifest.success is True
    assert manifest.indexed_chunk_count == 10


def test_load_manifest_defaults_collection_when_missing(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"success": False}), encoding="utf-8")

    manifest = load_manifest(tmp_path)

    assert manifest.collection_name == DEFAULT_COLLECTION_NAME
    assert manifest.success is False
    assert manifest.embedding_model_used is None


def test_load_manifest_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path)


def test_load_manifest_invalid_json_raises(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_manifest(tmp_path)
