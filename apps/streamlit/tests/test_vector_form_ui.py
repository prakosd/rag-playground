from __future__ import annotations

from pathlib import Path

from artifact_store.crawl_results import CrawlResultFile

from crawl4md_streamlit.vector_form_ui import crawl_result_options, has_index_inputs


def _crawl_result(crawl_label: str, relative_path: str, path: str) -> CrawlResultFile:
    return CrawlResultFile(
        path=Path(path),
        relative_path=relative_path,
        crawl_label=crawl_label,
        size_bytes=1,
    )


def test_crawl_result_options_maps_label_to_path() -> None:
    files = [_crawl_result("crawl_01_a", "crawl_01_a/final/notes.md", "/abs/notes.md")]

    options = crawl_result_options(files)

    label = next(iter(options))
    assert "crawl_01_a" in label
    assert "notes.md" in label
    assert list(options.values()) == [str(Path("/abs/notes.md"))]


def test_crawl_result_options_disambiguates_duplicate_labels() -> None:
    files = [
        _crawl_result("c", "c/final/x.md", "/a/x.md"),
        _crawl_result("c", "c/final/x.md", "/b/x.md"),
    ]

    options = crawl_result_options(files)

    assert len(options) == 2
    assert set(options.values()) == {str(Path("/a/x.md")), str(Path("/b/x.md"))}


def test_has_index_inputs() -> None:
    assert has_index_inputs(["/a"], 0)
    assert has_index_inputs([], 2)
    assert not has_index_inputs([], 0)
