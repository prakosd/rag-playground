"""Tests for crawl4md.writer — FileWriter."""

from __future__ import annotations

from pathlib import Path

import pytest

from crawl4md.config import ExtractedPage
from crawl4md.writer import _MB, FileWriter, PageSidecar, rename_files_with_total


class TestFileWriter:
    def test_writes_single_file(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path, max_file_size_mb=15.0)

        assert len(files) == 1
        assert files[0].name == "content_001.txt"
        content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/page1" in content
        assert "https://example.com/page2" in content
        assert "https://example.com/page3" in content

    def test_file_contains_url_headers(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        content = files[0].read_text(encoding="utf-8")

        assert "*Source: https://example.com/page1*" in content
        assert "# Page One" in content

    def test_file_contains_separators(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        content = files[0].read_text(encoding="utf-8")

        assert "\n---\n" in content

    def test_splits_at_size_limit(self, tmp_path: Path):
        """Produces multiple files when content exceeds max size."""
        big_text = "x" * 500
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown=big_text) for i in range(5)
        ]
        writer = FileWriter()
        # Tiny limit forces splitting
        files = writer.write(pages, tmp_path, max_file_size_mb=0.001)

        assert len(files) > 1
        for f in files:
            assert f.exists()

    def test_never_splits_single_page(self, tmp_path: Path):
        """A single page that exceeds the limit gets its own file."""
        big_page = ExtractedPage(
            url="https://example.com/huge",
            markdown="x" * 2000,
        )
        small_page = ExtractedPage(
            url="https://example.com/small",
            markdown="tiny",
        )
        writer = FileWriter()
        with pytest.warns(UserWarning, match="exceeds"):
            files = writer.write([big_page, small_page], tmp_path, max_file_size_mb=0.001)

        # Big page should be alone in its file
        assert len(files) == 2
        big_content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/huge" in big_content
        assert "https://example.com/small" not in big_content

    def test_naming_scheme(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        assert all(f.name.startswith("content_") for f in files)
        assert all(f.suffix == ".txt" for f in files)

    def test_md_extension_batch(self, tmp_path: Path, sample_pages):
        writer = FileWriter(file_extension=".md")
        files = writer.write(sample_pages, tmp_path)
        assert all(f.suffix == ".md" for f in files)
        assert files[0].name == "content_001.md"

    def test_write_override_extension(self, tmp_path: Path, sample_pages):
        writer = FileWriter(file_extension=".txt")
        files = writer.write(sample_pages, tmp_path, file_extension=".md")
        assert all(f.suffix == ".md" for f in files)

    def test_empty_pages_produces_no_files(self, tmp_path: Path):
        writer = FileWriter()
        files = writer.write([], tmp_path)
        assert files == []

    def test_creates_output_dir_if_missing(self, tmp_path: Path, sample_pages):
        out = tmp_path / "sub" / "dir"
        writer = FileWriter()
        files = writer.write(sample_pages, out)
        assert out.exists()
        assert len(files) == 1


class TestFileWriterIncremental:
    """Tests for the incremental add/flush API."""

    def test_add_and_flush_writes_file(self, tmp_path: Path, sample_pages):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)
        for page in sample_pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "content_001.txt"
        content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/page1" in content
        assert "https://example.com/page3" in content

    def test_add_and_flush_md_extension(self, tmp_path: Path, sample_pages):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0, file_extension=".md")
        for page in sample_pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "content_001.md"
        assert files[0].suffix == ".md"

    def test_multiple_flushes_append_to_same_file(self, tmp_path: Path):
        """Consecutive flushes write to the same file until size limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)

        page1 = ExtractedPage(url="https://example.com/a", markdown="First page")
        page2 = ExtractedPage(url="https://example.com/b", markdown="Second page")

        writer.add(page1)
        files1 = writer.flush()
        assert len(files1) == 1

        writer.add(page2)
        files2 = writer.flush()
        assert len(files2) == 1  # still the same file

        content = files2[0].read_text(encoding="utf-8")
        assert "https://example.com/a" in content
        assert "https://example.com/b" in content

    def test_flush_respects_max_file_size(self, tmp_path: Path):
        """A new file starts when adding a page would exceed the limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)
        big_text = "x" * 500
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown=big_text) for i in range(3)
        ]
        for page in pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) > 1
        for f in files:
            assert f.exists()

    def test_flush_creates_new_file_after_size_reached(self, tmp_path: Path):
        """Flushing small pages, then adding more still respects size limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)

        page1 = ExtractedPage(url="https://example.com/a", markdown="x" * 500)
        page2 = ExtractedPage(url="https://example.com/b", markdown="y" * 500)

        writer.add(page1)
        writer.flush()

        writer.add(page2)
        files = writer.flush()

        assert len(files) == 2
        assert files[0].name == "content_001.txt"
        assert files[1].name == "content_002.txt"

    def test_oversized_page_gets_own_file(self, tmp_path: Path):
        """A page exceeding max_file_size_mb is written alone."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)
        small = ExtractedPage(url="https://example.com/small", markdown="tiny")
        huge = ExtractedPage(url="https://example.com/huge", markdown="x" * 2000)

        writer.add(small)
        with pytest.warns(UserWarning, match="exceeds"):
            writer.add(huge)
        files = writer.flush()

        assert len(files) >= 2
        # The small and huge pages are in separate files
        contents = [f.read_text(encoding="utf-8") for f in files]
        small_file = [c for c in contents if "https://example.com/small" in c]
        huge_file = [c for c in contents if "https://example.com/huge" in c]
        assert len(small_file) == 1
        assert len(huge_file) == 1

    def test_empty_flush_returns_empty(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)
        files = writer.flush()
        assert files == []

    def test_creates_output_dir_if_missing(self, tmp_path: Path):
        out = tmp_path / "sub" / "dir"
        writer = FileWriter(output_dir=out, max_file_size_mb=15.0)
        page = ExtractedPage(url="https://example.com/a", markdown="content")
        writer.add(page)
        files = writer.flush()
        assert out.exists()
        assert len(files) == 1


class TestFileWriterPrefix:
    """Tests for the prefix and reset() API."""

    def test_prefix_in_filename(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0, prefix="round_1_")
        page = ExtractedPage(url="https://example.com/a", markdown="content")
        writer.add(page)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "round_1_content_001.txt"

    def test_reset_changes_prefix(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0, prefix="round_1_")
        page1 = ExtractedPage(url="https://example.com/a", markdown="first")
        writer.add(page1)
        files1 = writer.flush()

        writer.reset("round_2_")
        page2 = ExtractedPage(url="https://example.com/b", markdown="second")
        writer.add(page2)
        files2 = writer.flush()

        assert files1[0].name == "round_1_content_001.txt"
        assert files2[0].name == "round_2_content_001.txt"

    def test_reset_clears_state(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0, prefix="round_1_")
        page = ExtractedPage(url="https://example.com/a", markdown="x" * 500)
        writer.add(page)
        writer.flush()

        writer.reset("round_2_")
        # After reset, file index should restart at 1
        page2 = ExtractedPage(url="https://example.com/b", markdown="y" * 500)
        writer.add(page2)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "round_2_content_001.txt"

    def test_default_prefix_is_empty(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)
        page = ExtractedPage(url="https://example.com/a", markdown="content")
        writer.add(page)
        files = writer.flush()

        assert files[0].name == "content_001.txt"


class TestFileWriterDiskSizeLimit:
    """Verify that output files never exceed max_file_size_mb on disk."""

    def test_incremental_files_within_limit(self, tmp_path: Path):
        """Every file produced by add/flush respects the size limit on disk."""
        limit_mb = 0.001
        max_bytes = int(limit_mb * _MB)
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=limit_mb)
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown="x" * 300) for i in range(10)
        ]
        for page in pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) > 1
        for f in files:
            assert f.stat().st_size <= max_bytes

    def test_batch_files_within_limit(self, tmp_path: Path):
        """Every file produced by write() respects the size limit on disk."""
        limit_mb = 0.001
        max_bytes = int(limit_mb * _MB)
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown="y" * 300) for i in range(10)
        ]
        writer = FileWriter()
        files = writer.write(pages, tmp_path, max_file_size_mb=limit_mb)

        assert len(files) > 1
        for f in files:
            assert f.stat().st_size <= max_bytes

    def test_multi_flush_append_within_limit(self, tmp_path: Path):
        """Repeated flush-then-add cycles keep files within the limit on disk."""
        limit_mb = 0.002
        max_bytes = int(limit_mb * _MB)
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=limit_mb)

        for i in range(8):
            page = ExtractedPage(url=f"https://example.com/p{i}", markdown="z" * 200)
            writer.add(page)
            writer.flush()

        files = writer.flush()
        assert len(files) >= 1
        for f in files:
            assert f.stat().st_size <= max_bytes


class TestPageSidecar:
    def test_round_trip(self, tmp_path: Path):
        """append + read_pages produces identical ExtractedPage objects."""
        path = tmp_path / "pages.jsonl"
        pages = [
            ExtractedPage(url="https://a.com/1", title="A", markdown="# A"),
            ExtractedPage(url="https://b.com/2", title="B", markdown="# B"),
        ]
        for p in pages:
            PageSidecar.append(p, path)
        result = list(PageSidecar.read_pages(path))
        assert len(result) == 2
        assert result[0].url == "https://a.com/1"
        assert result[0].title == "A"
        assert result[0].markdown == "# A"
        assert result[1].url == "https://b.com/2"

    def test_empty_file(self, tmp_path: Path):
        """read_pages yields nothing for a non-existent file."""
        path = tmp_path / "missing.jsonl"
        assert list(PageSidecar.read_pages(path)) == []

    def test_unicode_content(self, tmp_path: Path):
        """Non-ASCII text survives serialization round-trip."""
        path = tmp_path / "unicode.jsonl"
        page = ExtractedPage(
            url="https://example.com/日本語",
            title="日本語タイトル",
            markdown="# こんにちは\n\n内容です。",
        )
        PageSidecar.append(page, path)
        result = list(PageSidecar.read_pages(path))
        assert len(result) == 1
        assert result[0].url == page.url
        assert result[0].title == page.title
        assert result[0].markdown == page.markdown

    def test_newlines_in_markdown(self, tmp_path: Path):
        """Markdown with embedded newlines round-trips correctly."""
        path = tmp_path / "newlines.jsonl"
        page = ExtractedPage(
            url="https://example.com/multi",
            title="Multi",
            markdown="Line 1\nLine 2\n\n## Heading\n\nParagraph.",
        )
        PageSidecar.append(page, path)
        result = list(PageSidecar.read_pages(path))
        assert result[0].markdown == page.markdown

    def test_creates_parent_dirs(self, tmp_path: Path):
        """append creates intermediate directories if needed."""
        path = tmp_path / "sub" / "dir" / "pages.jsonl"
        page = ExtractedPage(url="https://example.com", markdown="text")
        PageSidecar.append(page, path)
        assert path.exists()
        result = list(PageSidecar.read_pages(path))
        assert len(result) == 1


class TestPageSidecarIndex:
    """Tests for streaming-sort primitives: iter_index + read_page_at."""

    def test_iter_index_yields_one_entry_per_record(self, tmp_path: Path):
        path = tmp_path / "pages.jsonl"
        pages = [
            ExtractedPage(url="https://a.com/1", title="A", markdown="# A"),
            ExtractedPage(url="https://b.com/2", title="B", markdown="# B"),
            ExtractedPage(url="https://c.com/3", title="C", markdown="# C"),
        ]
        for p in pages:
            PageSidecar.append(p, path)

        entries = list(PageSidecar.iter_index(path))
        assert [e.url for e in entries] == [p.url for p in pages]
        assert all(e.sidecar_path == path for e in entries)
        assert all(e.byte_length > 0 for e in entries)
        # Offsets are strictly increasing
        offsets = [e.byte_offset for e in entries]
        assert offsets == sorted(offsets)
        assert offsets[0] == 0

    def test_iter_index_skips_empty_markdown(self, tmp_path: Path):
        """Records with empty markdown are filtered (defensive parity with old dedup)."""
        path = tmp_path / "pages.jsonl"
        good = ExtractedPage(url="https://a.com", markdown="text")
        empty = ExtractedPage(url="https://b.com", markdown="   ")
        PageSidecar.append(good, path)
        PageSidecar.append(empty, path)

        entries = list(PageSidecar.iter_index(path))
        assert [e.url for e in entries] == ["https://a.com"]

    def test_iter_index_missing_file(self, tmp_path: Path):
        assert list(PageSidecar.iter_index(tmp_path / "nope.jsonl")) == []

    def test_read_page_at_round_trip(self, tmp_path: Path):
        """read_page_at returns the exact ExtractedPage recorded at that offset."""
        path = tmp_path / "pages.jsonl"
        pages = [
            ExtractedPage(url="https://a.com/1", title="A", markdown="# A\nbody"),
            ExtractedPage(url="https://b.com/2", title="B", markdown="# B\n日本語"),
            ExtractedPage(url="https://c.com/3", title="C", markdown="# C\n\n## sec"),
        ]
        for p in pages:
            PageSidecar.append(p, path)

        entries = list(PageSidecar.iter_index(path))
        for entry, original in zip(entries, pages, strict=True):
            loaded = PageSidecar.read_page_at(path, entry.byte_offset, entry.byte_length)
            assert loaded.url == original.url
            assert loaded.title == original.title
            assert loaded.markdown == original.markdown

    def test_read_page_at_random_order(self, tmp_path: Path):
        """Pages can be read back in arbitrary order via byte offsets."""
        path = tmp_path / "pages.jsonl"
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown=f"page {i}") for i in range(5)
        ]
        for p in pages:
            PageSidecar.append(p, path)

        entries = list(PageSidecar.iter_index(path))
        # Read in reverse order
        for entry, original in zip(reversed(entries), reversed(pages), strict=True):
            loaded = PageSidecar.read_page_at(path, entry.byte_offset, entry.byte_length)
            assert loaded.url == original.url
            assert loaded.markdown == original.markdown


class TestRenameFilesWithTotal:
    """Tests for the rename_files_with_total utility function."""

    def test_empty_list(self):
        assert rename_files_with_total([]) == []

    def test_single_file(self, tmp_path: Path):
        f = tmp_path / "content_001.md"
        f.write_text("data", encoding="utf-8")
        result = rename_files_with_total([f])
        assert len(result) == 1
        assert result[0].name == "content_001_of_001.md"
        assert result[0].exists()
        assert not f.exists()

    def test_multiple_files(self, tmp_path: Path):
        files = []
        for i in range(1, 4):
            f = tmp_path / f"content_{i:03d}.txt"
            f.write_text(f"data {i}", encoding="utf-8")
            files.append(f)
        result = rename_files_with_total(files)
        assert len(result) == 3
        assert result[0].name == "content_001_of_003.txt"
        assert result[1].name == "content_002_of_003.txt"
        assert result[2].name == "content_003_of_003.txt"
        for r in result:
            assert r.exists()
        for f in files:
            assert not f.exists()

    def test_preserves_prefix_and_extension(self, tmp_path: Path):
        files = []
        for i in range(1, 6):
            f = tmp_path / f"sorted_final_success_content_{i:03d}.md"
            f.write_text(f"page {i}", encoding="utf-8")
            files.append(f)
        result = rename_files_with_total(files)
        assert result[1].name == "sorted_final_success_content_002_of_005.md"
        assert result[4].name == "sorted_final_success_content_005_of_005.md"

    def test_blank_lines_skipped(self, tmp_path: Path):
        """Blank lines in the JSONL file are silently skipped."""
        path = tmp_path / "blanks.jsonl"
        page = ExtractedPage(url="https://example.com", markdown="ok")
        PageSidecar.append(page, path)
        # Inject a blank line
        with path.open("a") as fh:
            fh.write("\n")
        PageSidecar.append(page, path)
        result = list(PageSidecar.read_pages(path))
        assert len(result) == 2
