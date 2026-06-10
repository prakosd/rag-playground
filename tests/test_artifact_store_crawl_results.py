from __future__ import annotations

from pathlib import Path

from artifact_store.crawl_results import list_crawl_result_files


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discovers_final_success_content_newest_crawl_first(tmp_path: Path) -> None:
    root = tmp_path / "session_demo"
    _write(
        root / "crawl_01_alpha" / "2026-06-01_10-00-00" / "final" / "sorted_success_content_001.md"
    )
    newer_final = root / "crawl_02_beta" / "2026-06-02_09-00-00" / "final"
    _write(newer_final / "sorted_success_content_001.md")
    _write(newer_final / "sorted_success_content_002.md")

    files = list_crawl_result_files(root)

    labels = [result.crawl_label for result in files]
    assert len(files) == 3
    assert labels[0] == "crawl_02_beta"  # higher sequence sorts first
    assert labels[-1] == "crawl_01_alpha"


def test_falls_back_to_round_content_when_no_final(tmp_path: Path) -> None:
    # A stopped or in-progress crawl has round_N/ snapshots but no final/ folder.
    root = tmp_path / "session_x"
    _write(root / "crawl_01_a" / "2026-06-01_10-00-00" / "round_1" / "success_content_001.md")

    files = list_crawl_result_files(root)

    names = [Path(result.relative_path).name for result in files]
    assert names == ["success_content_001.md"]
    assert files[0].crawl_label == "crawl_01_a"


def test_prefers_final_over_round_snapshots(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    run = root / "crawl_01_a" / "2026-06-01_10-00-00"
    _write(run / "round_1" / "success_content_001.md")
    _write(run / "final" / "sorted_success_content_001.md")

    files = list_crawl_result_files(root)

    names = [Path(result.relative_path).name for result in files]
    assert names == ["sorted_success_content_001.md"]


def test_prefers_sorted_over_unsorted_content(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    final = root / "crawl_01_a" / "2026-06-01_10-00-00" / "final"
    _write(final / "success_content_001.md")
    _write(final / "sorted_success_content_001.md")

    files = list_crawl_result_files(root)

    names = [Path(result.relative_path).name for result in files]
    assert names == ["sorted_success_content_001.md"]


def test_uses_newest_round_when_multiple(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    run = root / "crawl_01_a" / "2026-06-01_10-00-00"
    _write(run / "round_1" / "success_content_001.md", "old")
    _write(run / "round_2" / "success_content_001.md", "new")

    files = list_crawl_result_files(root)

    assert len(files) == 1
    assert "round_2" in files[0].relative_path


def test_excludes_url_lists_fail_content_and_generated_zip(tmp_path: Path) -> None:
    root = tmp_path / "session_x"
    final = root / "crawl_01_a" / "2026-06-01_10-00-00" / "final"
    _write(final / "sorted_success_content_001.md")
    _write(final / "sorted_success_urls.txt")  # URL list, not content
    _write(final / "sorted_fail_content_001.md")  # failed pages, not wanted
    _write(final / "sorted_fail_urls.txt")
    _write(final / "success_content.zip")  # generated packaging artifact

    files = list_crawl_result_files(root)

    names = [Path(result.relative_path).name for result in files]
    assert names == ["sorted_success_content_001.md"]


def test_relative_paths_stay_within_session(tmp_path: Path) -> None:
    root = tmp_path / "session_demo"
    _write(
        root / "crawl_01_alpha" / "2026-06-01_10-00-00" / "final" / "sorted_success_content_001.md"
    )

    files = list_crawl_result_files(root)

    assert files[0].relative_path.startswith("crawl_01_alpha/")
    assert files[0].path.is_file()


def test_only_newest_run_directory_is_used(tmp_path: Path) -> None:
    root = tmp_path / "session_demo"
    crawl = root / "crawl_01_alpha"
    _write(crawl / "2026-06-01_09-00-00" / "final" / "sorted_success_content_001.md", "old")
    _write(crawl / "2026-06-02_09-00-00" / "final" / "sorted_success_content_001.md", "new")

    files = list_crawl_result_files(root)

    assert len(files) == 1
    assert "2026-06-02_09-00-00" in files[0].relative_path


def test_missing_root_returns_empty(tmp_path: Path) -> None:
    assert list_crawl_result_files(tmp_path / "does_not_exist") == []
