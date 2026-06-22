from __future__ import annotations

from vector_indexer.page_source import format_source_line, split_into_pages


def _crawl_output(*pages: tuple[str | None, str, str]) -> str:
    """Build a crawl4md-style file: metadata front matter + marked pages."""
    parts = [
        "---\n",
        'crawl_start_datetime: "2026-06-22T10:30:00Z"\n',
        'session_id: "s123"\n',
        "status: success\n",
        "---\n",
    ]
    for title, url, content in pages:
        parts.append("\n\n---\n\n<!-- crawl4md:source -->\n")
        if title:
            parts.append(f"# {title}\n\n")
        parts.append(f"*Source: {url}*\n<!-- /crawl4md:source -->\n\n---\n\n{content}\n")
    return "".join(parts)


def test_split_strips_front_matter_and_recovers_pages() -> None:
    text = _crawl_output(
        ("Page One", "https://x.test/a", "Body one."),
        ("Page Two", "https://x.test/b", "Body two."),
    )

    pages = split_into_pages(text)

    assert [page.title for page in pages] == ["Page One", "Page Two"]
    assert [page.url for page in pages] == ["https://x.test/a", "https://x.test/b"]
    assert [page.body for page in pages] == ["Body one.", "Body two."]


def test_split_excludes_run_metadata_from_bodies() -> None:
    text = _crawl_output(("Page One", "https://x.test/a", "Body one."))

    pages = split_into_pages(text)

    assert "crawl_start_datetime" not in pages[0].body
    assert "session_id" not in pages[0].body


def test_split_recovers_url_when_title_missing() -> None:
    text = _crawl_output((None, "https://x.test/a", "Body."))

    pages = split_into_pages(text)

    assert pages[0].title is None
    assert pages[0].url == "https://x.test/a"


def test_split_without_markers_returns_single_untitled_page() -> None:
    pages = split_into_pages("Just some plain text.\n")

    assert len(pages) == 1
    assert pages[0].title is None
    assert pages[0].url is None
    assert pages[0].body == "Just some plain text."


def test_split_blank_input_returns_no_pages() -> None:
    assert split_into_pages("   \n\n") == []


def test_format_source_line_variants() -> None:
    assert format_source_line("Title", "https://x.test/a") == "Source: [Title](https://x.test/a)"
    assert format_source_line(None, "https://x.test/a") == "Source: https://x.test/a"
    assert format_source_line("Title", None) == ""
    assert format_source_line(None, None) == ""
