"""Tests for the backend-neutral storage seam (LocalStorageBackend)."""

from __future__ import annotations

from pathlib import Path

from artifact_store import LocalStorageBackend, StorageBackend


def test_local_backend_satisfies_the_protocol() -> None:
    assert isinstance(LocalStorageBackend(), StorageBackend)


def test_local_backend_round_trips_bytes(tmp_path: Path) -> None:
    backend = LocalStorageBackend()
    target = tmp_path / "nested" / "file.md"
    backend.write_bytes(target, b"hello")  # parent dirs created on write
    assert backend.exists(target)
    assert not backend.is_dir(target)
    assert backend.read_bytes(target) == b"hello"


def test_local_backend_lists_sorted_and_reports_mtime(tmp_path: Path) -> None:
    backend = LocalStorageBackend()
    backend.write_bytes(tmp_path / "b.txt", b"b")
    backend.write_bytes(tmp_path / "a.txt", b"a")

    listed = backend.iterdir(tmp_path)

    assert [p.name for p in listed] == ["a.txt", "b.txt"]  # deterministic order
    assert backend.is_dir(tmp_path)
    assert backend.mtime(tmp_path / "a.txt") > 0


def test_local_backend_remove_tree_is_forgiving(tmp_path: Path) -> None:
    backend = LocalStorageBackend()
    backend.write_bytes(tmp_path / "sub" / "x.txt", b"x")

    backend.remove_tree(tmp_path / "sub")
    assert not backend.exists(tmp_path / "sub")
    backend.remove_tree(tmp_path / "sub")  # already gone → no error
