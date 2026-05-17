from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from crawl4md_streamlit.generated_files import GeneratedFile, build_download_tree

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
