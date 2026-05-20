from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from crawl4md_streamlit.generated_files import (
    GeneratedFile,
    ReadyDownload,
    build_download_tree,
    build_ready_download,
    collapse_crawl_run_folder,
    collect_success_content_files,
    find_ready_download_in_session,
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


def test_collapse_crawl_run_folder_merges_single_timestamp_child() -> None:
    crawl_tree = {
        "2026-05-19_18-17-52": {
            "final": {"content.md": _generated_file("crawl_1/final/content.md")},
            "round_1": {},
        }
    }

    label, folder_node = collapse_crawl_run_folder("crawl_1_parlor", crawl_tree)

    assert label == "1_parlor/2026-05-19_18-17-52"
    assert folder_node == crawl_tree["2026-05-19_18-17-52"]


def test_collapse_crawl_run_folder_keeps_folder_when_not_single_timestamp_child() -> None:
    crawl_tree = {
        "2026-05-19_18-17-52": {},
        "2026-05-19_18-17-53": {},
    }

    label, folder_node = collapse_crawl_run_folder("crawl_1_parlor", crawl_tree)

    assert label == "1_parlor"
    assert folder_node == crawl_tree


def test_collapse_crawl_run_folder_keeps_non_timestamp_child() -> None:
    crawl_tree = {"final": {"content.md": _generated_file("crawl_1/final/content.md")}}

    label, folder_node = collapse_crawl_run_folder("crawl_1_parlor", crawl_tree)

    assert label == "1_parlor"
    assert folder_node == crawl_tree


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


# ── collect_success_content_files ────────────────────────────────────────────


def _make_final_dir(root: Path) -> Path:
    final = root / "final"
    final.mkdir(parents=True)
    return final


def test_collect_prefers_sorted_success_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    sorted_f = final / "sorted_success_content_001_of_001.md"
    unsorted_f = final / "success_content_001.md"
    sorted_f.write_text("sorted", encoding="utf-8")
    unsorted_f.write_text("unsorted", encoding="utf-8")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [sorted_f]


def test_collect_falls_back_to_unsorted_success_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "success_content_001.md"
    content_f.write_text("content", encoding="utf-8")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [content_f]


def test_collect_excludes_zip_from_fallback(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "success_content_001.md"
    zip_f = final / "success_content.zip"
    content_f.write_text("content", encoding="utf-8")
    zip_f.write_bytes(b"PK")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [content_f]


def test_collect_returns_empty_when_no_final_dir(tmp_path: Path) -> None:
    assert collect_success_content_files(tmp_path, tmp_path) == []


def test_collect_returns_empty_for_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "session"
    root.mkdir()

    assert collect_success_content_files(outside, root) == []


# ── build_ready_download ─────────────────────────────────────────────────────


def test_build_ready_download_returns_none_when_no_success_files(tmp_path: Path) -> None:
    _make_final_dir(tmp_path)

    assert build_ready_download(tmp_path, tmp_path) is None


def test_build_ready_download_returns_single_file_directly(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "sorted_success_content_001_of_001.md"
    content_f.write_text("# Page", encoding="utf-8")

    result = build_ready_download(tmp_path, tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.source_count == 1
    assert result.file.path == content_f
    assert result.file.file_type == "md"
    assert not (final / "success_content.zip").exists()


def test_build_ready_download_creates_zip_for_multiple_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    (final / "sorted_success_content_001_of_002.md").write_text("# A", encoding="utf-8")
    (final / "sorted_success_content_002_of_002.md").write_text("# B", encoding="utf-8")

    result = build_ready_download(tmp_path, tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.source_count == 2
    assert result.file.name == "success_content.zip"
    assert result.file.file_type == "zip"
    assert (final / "success_content.zip").exists()


def test_build_ready_download_reuses_zip_when_up_to_date(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    (final / "sorted_success_content_001_of_002.md").write_text("# A", encoding="utf-8")
    (final / "sorted_success_content_002_of_002.md").write_text("# B", encoding="utf-8")
    build_ready_download(tmp_path, tmp_path)
    zip_path = final / "success_content.zip"
    future_mtime = zip_path.stat().st_mtime + 100
    os.utime(zip_path, (future_mtime, future_mtime))

    build_ready_download(tmp_path, tmp_path)

    assert zip_path.stat().st_mtime == future_mtime


def test_build_ready_download_respects_download_limit(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "sorted_success_content_001_of_001.md"
    content_f.write_bytes(b"x" * 20)

    result = build_ready_download(tmp_path, tmp_path, download_limit_bytes=10)

    assert result is not None
    assert result.file.download_allowed is False


def test_build_ready_download_returns_none_for_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "session"
    root.mkdir()

    assert build_ready_download(outside, root) is None


# ── find_ready_download_in_session ────────────────────────────────────────────


def _make_crawl_run(session_root: Path, crawl_name: str, run_name: str) -> Path:
    """Create crawl_name/run_name/final/ structure and return the run dir."""
    run_dir = session_root / crawl_name / run_name
    (run_dir / "final").mkdir(parents=True)
    return run_dir


def test_find_ready_download_in_session_returns_none_for_missing_root(tmp_path: Path) -> None:
    assert find_ready_download_in_session(tmp_path / "missing") is None


def test_find_ready_download_in_session_returns_none_when_no_crawl_dirs(tmp_path: Path) -> None:
    (tmp_path / "not_a_crawl").mkdir()

    assert find_ready_download_in_session(tmp_path) is None


def test_find_ready_download_in_session_returns_none_when_no_success_content(
    tmp_path: Path,
) -> None:
    _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_12-00-00")

    assert find_ready_download_in_session(tmp_path) is None


def test_find_ready_download_in_session_returns_single_crawl_result(tmp_path: Path) -> None:
    run_dir = _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_12-00-00")
    content = run_dir / "final" / "sorted_success_content_001_of_001.md"
    content.write_text("# Page", encoding="utf-8")

    result = find_ready_download_in_session(tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.file.path == content


def test_find_ready_download_in_session_returns_newest_run(tmp_path: Path) -> None:
    old_run = _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_10-00-00")
    new_run = _make_crawl_run(tmp_path, "crawl_2_other", "2026-05-20_12-00-00")
    (old_run / "final" / "sorted_success_content_001_of_001.md").write_text("old", encoding="utf-8")
    new_content = new_run / "final" / "sorted_success_content_001_of_001.md"
    new_content.write_text("new", encoding="utf-8")
    # Ensure new_run is clearly newer by mtime
    old_mtime = old_run.stat().st_mtime - 100
    os.utime(old_run, (old_mtime, old_mtime))

    result = find_ready_download_in_session(tmp_path)

    assert result is not None
    assert result.file.path == new_content


def test_find_ready_download_in_session_falls_back_to_older_crawl(tmp_path: Path) -> None:
    empty_run = _make_crawl_run(tmp_path, "crawl_2_empty", "2026-05-20_12-00-00")
    old_run = _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_10-00-00")
    old_content = old_run / "final" / "sorted_success_content_001_of_001.md"
    old_content.write_text("content", encoding="utf-8")
    # Make empty_run clearly newer
    new_mtime = old_run.stat().st_mtime + 100
    os.utime(empty_run, (new_mtime, new_mtime))

    result = find_ready_download_in_session(tmp_path)

    assert result is not None
    assert result.file.path == old_content
