"""Tests for final-output orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import crawl4md._internal.final_output as _fo_mod
from crawl4md._internal.final_output import FinalOutputWriter
from crawl4md.config import CrawlResult, ExtractedPage
from crawl4md.writer import PageSidecar


def _output_writer(output_dir: Path) -> FinalOutputWriter:
    return FinalOutputWriter(
        output_dir=output_dir,
        output_extension=".md",
        max_file_size_mb=1.0,
        run_metadata={},
    )


def _append_page(path: Path, url: str, markdown: str) -> None:
    PageSidecar.append(
        ExtractedPage(url=url, title=url.rsplit("/", 1)[-1], markdown=markdown), path
    )


def test_write_final_files_writes_url_lists_and_content(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    success_sidecar = round_dir / "success_pages.jsonl"
    fail_sidecar = round_dir / "fail_pages.jsonl"
    _append_page(success_sidecar, "https://example.com/a", "# A")
    _append_page(fail_sidecar, "https://example.com/b", "# B failed")
    writer = _output_writer(tmp_path)

    writer.write_final_files(
        [CrawlResult(url="https://example.com/a", success=True)],
        [CrawlResult(url="https://example.com/b", success=False)],
        write_content=True,
    )

    final_dir = tmp_path / "final"
    assert (final_dir / "success_urls.txt").read_text(encoding="utf-8") == "https://example.com/a"
    assert (final_dir / "fail_urls.txt").read_text(encoding="utf-8") == "https://example.com/b"
    assert "# A" in next(final_dir.glob("success_content_*.md")).read_text(encoding="utf-8")
    assert "# B failed" in next(final_dir.glob("fail_content_*.md")).read_text(encoding="utf-8")


def test_write_sorted_files_sorts_urls_and_renames_content(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    success_sidecar = round_dir / "success_pages.jsonl"
    _append_page(success_sidecar, "https://example.com/b", "# B")
    _append_page(success_sidecar, "https://example.com/a", "# A")
    writer = _output_writer(tmp_path)

    writer.write_sorted_files()

    final_dir = tmp_path / "final"
    assert (final_dir / "sorted_success_urls.txt").read_text(encoding="utf-8") == (
        "https://example.com/a\nhttps://example.com/b"
    )
    assert list(final_dir.glob("sorted_success_content_*_of_*.md"))


def test_saved_results_from_sidecars_excludes_failed_urls_that_later_succeeded(
    tmp_path: Path,
) -> None:
    round_1 = tmp_path / "round_1"
    round_2 = tmp_path / "round_2"
    _append_page(round_1 / "fail_pages.jsonl", "https://example.com/a", "# Failed")
    _append_page(round_2 / "success_pages.jsonl", "https://example.com/a", "# Success")
    writer = _output_writer(tmp_path)

    success, fail = writer.saved_results_from_sidecars()

    assert [result.url for result in success] == ["https://example.com/a"]
    assert fail == []


def test_write_url_file_removes_stale_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "urls.txt"
    path.write_text("https://example.com", encoding="utf-8")

    FinalOutputWriter.write_url_file(path, [])

    assert not path.exists()


# ---------------------------------------------------------------------------
# _CLEANUP_INTERMEDIATE_FILES toggle tests
# ---------------------------------------------------------------------------


def test_write_sorted_files_deletes_sidecars_when_cleanup_enabled(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    success_sidecar = round_dir / "success_pages.jsonl"
    fail_sidecar = round_dir / "fail_pages.jsonl"
    _append_page(success_sidecar, "https://example.com/a", "# A")
    _append_page(fail_sidecar, "https://example.com/b", "# B")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_CLEANUP_INTERMEDIATE_FILES", True):
        writer.write_sorted_files()

    assert not success_sidecar.exists()
    assert not fail_sidecar.exists()


def test_write_sorted_files_keeps_sidecars_when_cleanup_disabled(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    success_sidecar = round_dir / "success_pages.jsonl"
    _append_page(success_sidecar, "https://example.com/a", "# A")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_CLEANUP_INTERMEDIATE_FILES", False):
        writer.write_sorted_files()

    assert success_sidecar.exists()


def test_write_sorted_files_deletes_unsorted_final_content_when_cleanup_enabled(
    tmp_path: Path,
) -> None:
    round_dir = tmp_path / "round_1"
    _append_page(round_dir / "success_pages.jsonl", "https://example.com/a", "# A")
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    unsorted = final_dir / "success_content_001.md"
    unsorted.write_text("old", encoding="utf-8")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_CLEANUP_INTERMEDIATE_FILES", True):
        writer.write_sorted_files()

    assert not unsorted.exists()
    assert list(final_dir.glob("sorted_success_content_*"))


def test_write_sorted_files_keeps_unsorted_final_content_when_cleanup_disabled(
    tmp_path: Path,
) -> None:
    round_dir = tmp_path / "round_1"
    _append_page(round_dir / "success_pages.jsonl", "https://example.com/a", "# A")
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    unsorted = final_dir / "success_content_001.md"
    unsorted.write_text("old", encoding="utf-8")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_CLEANUP_INTERMEDIATE_FILES", False):
        writer.write_sorted_files()

    assert unsorted.exists()


def test_delete_sidecars_handles_absent_files_gracefully(tmp_path: Path) -> None:
    writer = _output_writer(tmp_path)
    # No sidecar files exist — should not raise
    writer.delete_sidecars()


def test_write_sorted_round_files_skipped_when_cleanup_enabled(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    _append_page(round_dir / "success_pages.jsonl", "https://example.com/a", "# A")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_ENABLE_SORTED_ROUND_FILES", False):
        writer.write_sorted_round_files(1, round_dir)

    assert not list(round_dir.glob("sorted_success_content_*"))
    assert not list(round_dir.glob("sorted_success_urls.txt"))


def test_write_sorted_round_files_produced_when_cleanup_disabled(tmp_path: Path) -> None:
    round_dir = tmp_path / "round_1"
    _append_page(round_dir / "success_pages.jsonl", "https://example.com/a", "# A")
    writer = _output_writer(tmp_path)

    with patch.object(_fo_mod, "_ENABLE_SORTED_ROUND_FILES", True):
        writer.write_sorted_round_files(2, round_dir)

    assert list(round_dir.glob("sorted_success_content_*"))
    assert (round_dir / "sorted_success_urls.txt").exists()
