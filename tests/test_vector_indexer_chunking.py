from __future__ import annotations

from vector_indexer.chunking import chunk_documents
from vector_indexer.models import Document


def _crawl_output(title: str, url: str, content: str) -> str:
    """Build a one-page crawl4md-style file with metadata front matter."""
    return (
        "---\n"
        'crawl_start_datetime: "2026-06-22T10:30:00Z"\n'
        'session_id: "s123"\n'
        "status: success\n"
        "---\n"
        "\n\n---\n\n<!-- crawl4md:source -->\n"
        f"# {title}\n\n*Source: {url}*\n<!-- /crawl4md:source -->\n\n---\n\n{content}\n"
    )


def test_chunking_respects_size_and_records_metadata() -> None:
    text = "abcdefghij" * 30  # 300 characters with no natural separators
    documents = [Document(source="a.md", text=text)]

    chunks = chunk_documents(documents, chunk_size=100, chunk_overlap=20, language="english")

    assert len(chunks) >= 3
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.metadata["language"] == "english" for chunk in chunks)
    assert all(chunk.metadata["source"] == "a.md" for chunk in chunks)


def test_chunking_drops_empty_documents() -> None:
    chunks = chunk_documents(
        [Document(source="x.md", text="   ")],
        chunk_size=100,
        chunk_overlap=10,
        language="english",
    )

    assert chunks == []


def test_chunking_stamps_source_line_and_excludes_run_metadata() -> None:
    text = _crawl_output("Page One", "https://x.test/a", "Alpha beta gamma delta. " * 20)
    documents = [Document(source="c.md", text=text)]

    chunks = chunk_documents(documents, chunk_size=120, chunk_overlap=20, language="english")

    assert chunks
    assert all(chunk.text.startswith("Source: [Page One](https://x.test/a)") for chunk in chunks)
    assert all(chunk.metadata["source_title"] == "Page One" for chunk in chunks)
    assert all(chunk.metadata["source_url"] == "https://x.test/a" for chunk in chunks)
    # The crawl4md run metadata must never reach indexed chunk text.
    assert all("crawl_start_datetime" not in chunk.text for chunk in chunks)
    assert all("session_id" not in chunk.text for chunk in chunks)


def test_chunking_without_markers_adds_no_source_prefix() -> None:
    documents = [Document(source="plain.txt", text="Plain content without any markers.")]

    chunks = chunk_documents(documents, chunk_size=100, chunk_overlap=10, language="english")

    assert chunks
    assert all(not chunk.text.startswith("Source:") for chunk in chunks)
    assert all("source_title" not in chunk.metadata for chunk in chunks)
    assert all("source_url" not in chunk.metadata for chunk in chunks)


def test_chunking_numbers_chunks_continuously_across_pages() -> None:
    two_pages = (
        "---\n"
        'session_id: "s1"\n'
        "---\n"
        "\n\n---\n\n<!-- crawl4md:source -->\n"
        "# One\n\n*Source: https://x.test/a*\n<!-- /crawl4md:source -->\n\n---\n\n"
        "Alpha alpha alpha. " * 12 + "\n\n---\n\n<!-- crawl4md:source -->\n"
        "# Two\n\n*Source: https://x.test/b*\n<!-- /crawl4md:source -->\n\n---\n\n"
        + "Beta beta beta. "
        * 12
    )
    chunks = chunk_documents(
        [Document(source="d.md", text=two_pages)],
        chunk_size=100,
        chunk_overlap=10,
        language="english",
    )

    # chunk_index runs continuously over the whole document, not per page.
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == [
        str(index) for index in range(len(chunks))
    ]
    assert {chunk.metadata["source_url"] for chunk in chunks} == {
        "https://x.test/a",
        "https://x.test/b",
    }
