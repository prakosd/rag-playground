from __future__ import annotations

from pathlib import Path

from artifact_store.naming import VECTOR_FOLDER_PREFIX
from vector_indexer.manifest import write_manifest

from app_support.rag_shared.index_catalog import IndexRef, list_session_indexes


def _make_index(
    session_root: Path,
    vector_folder: str,
    run_name: str,
    *,
    success: bool = True,
    chunks: int = 5,
    chroma: bool = True,
) -> Path:
    run_dir = session_root / vector_folder / run_name
    run_dir.mkdir(parents=True)
    if chroma:
        (run_dir / "chroma").mkdir()
    write_manifest(
        run_dir,
        {
            "success": success,
            "indexed_chunk_count": chunks,
            "embedding_model_used": "all-MiniLM-L6-v2",
            "collection_name": "crawl4md_documents",
        },
    )
    return run_dir


def test_lists_successful_index(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    root.mkdir()
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}1_alpha", "20260101_000000_run")

    refs = list_session_indexes(root)

    assert len(refs) == 1
    assert isinstance(refs[0], IndexRef)
    assert refs[0].manifest.indexed_chunk_count == 5
    assert refs[0].vector_folder == f"{VECTOR_FOLDER_PREFIX}1_alpha"


def test_skips_unsuccessful_or_empty_indexes(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    root.mkdir()
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}1_a", "r1", success=False)
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}2_b", "r2", chunks=0)

    assert list_session_indexes(root) == []


def test_skips_dirs_without_chroma_or_manifest(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    root.mkdir()
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}1_a", "r1", chroma=False)
    no_manifest = root / f"{VECTOR_FOLDER_PREFIX}2_b" / "r2"
    no_manifest.mkdir(parents=True)
    (no_manifest / "chroma").mkdir()

    assert list_session_indexes(root) == []


def test_sorted_newest_first(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    root.mkdir()
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}1_a", "20260101_000000_a")
    _make_index(root, f"{VECTOR_FOLDER_PREFIX}1_a", "20260202_000000_b")

    refs = list_session_indexes(root)

    assert [ref.run_name for ref in refs] == ["20260202_000000_b", "20260101_000000_a"]


def test_missing_root_returns_empty(tmp_path: Path) -> None:
    assert list_session_indexes(tmp_path / "nope") == []
