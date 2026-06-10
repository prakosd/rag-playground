from __future__ import annotations

from pathlib import Path

import pytest

from artifact_store.paths import ensure_within_root


def test_ensure_within_root_allows_descendant(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "file.txt"

    assert ensure_within_root(tmp_path, target) == target.resolve()


def test_ensure_within_root_allows_root_itself(tmp_path: Path) -> None:
    assert ensure_within_root(tmp_path, tmp_path) == tmp_path.resolve()


def test_ensure_within_root_rejects_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere"

    with pytest.raises(ValueError):
        ensure_within_root(tmp_path, outside)


def test_ensure_within_root_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ensure_within_root(tmp_path, tmp_path / ".." / "escape.txt")
