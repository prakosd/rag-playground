from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from crawl4md_streamlit.generated_files import (
    GeneratedFile,
    build_download_tree,
    generated_files_cache_token,
)

_MODIFIED_AT = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)


def _generated_file(relative_path: str) -> GeneratedFile:
    return GeneratedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        name=Path(relative_path).name,
        size_bytes=10,
        modified_at=_MODIFIED_AT,
        file_type="md",
        download_allowed=True,
    )


def test_build_download_tree_nests_generated_files_by_relative_path() -> None:
    root_file = _generated_file("summary.md")
    nested_file = _generated_file("crawl_run/final/content.md")

    tree = build_download_tree([nested_file, root_file])

    assert tree["summary.md"] == root_file
    assert tree["crawl_run"]["final"]["content.md"] == nested_file


def test_generated_files_cache_token_handles_missing_path(tmp_path: Path) -> None:
    assert generated_files_cache_token(tmp_path / "missing") == (0.0, 0)


def test_generated_files_cache_token_reflects_path_stat(tmp_path: Path) -> None:
    output_path = tmp_path / "session"
    output_path.mkdir()

    first_token = generated_files_cache_token(output_path)
    next_mtime = first_token[0] + 10
    os.utime(output_path, (next_mtime, next_mtime))
    second_token = generated_files_cache_token(output_path)

    assert second_token[0] > first_token[0]
    assert second_token[1] == first_token[1]
