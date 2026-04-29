"""Tests for ContentSorter."""

from crawl4md.config import ExtractedPage
from crawl4md.sorter import ContentSorter


def _page(url: str, title: str = "") -> ExtractedPage:
    return ExtractedPage(url=url, title=title, markdown=f"Content for {url}")


class TestContentSorter:
    def test_sorts_by_url_path(self) -> None:
        pages = [
            _page("https://example.com/b/page"),
            _page("https://example.com/a/page"),
            _page("https://example.com/c/page"),
        ]
        result = ContentSorter.sort(pages)
        assert [p.url for p in result] == [
            "https://example.com/a/page",
            "https://example.com/b/page",
            "https://example.com/c/page",
        ]

    def test_groups_related_paths(self) -> None:
        pages = [
            _page("https://example.com/personal/broadband/plan-a"),
            _page("https://example.com/personal/mobile/plan-x"),
            _page("https://example.com/personal/broadband/plan-b"),
            _page("https://example.com/personal/mobile/plan-y"),
            _page("https://example.com/personal/tv/plan-1"),
        ]
        result = ContentSorter.sort(pages)
        urls = [p.url for p in result]
        # broadband pages should be adjacent
        assert urls.index("https://example.com/personal/broadband/plan-a") + 1 == urls.index(
            "https://example.com/personal/broadband/plan-b"
        )
        # mobile pages should be adjacent
        assert urls.index("https://example.com/personal/mobile/plan-x") + 1 == urls.index(
            "https://example.com/personal/mobile/plan-y"
        )

    def test_stable_sort_preserves_order_for_same_path(self) -> None:
        pages = [
            _page("https://example.com/a", title="first"),
            _page("https://example.com/a", title="second"),
            _page("https://example.com/a", title="third"),
        ]
        result = ContentSorter.sort(pages)
        assert [p.title for p in result] == ["first", "second", "third"]

    def test_empty_list(self) -> None:
        assert ContentSorter.sort([]) == []

    def test_single_page(self) -> None:
        pages = [_page("https://example.com/only")]
        result = ContentSorter.sort(pages)
        assert len(result) == 1
        assert result[0].url == "https://example.com/only"

    def test_root_urls_sorted_before_deeper_paths(self) -> None:
        pages = [
            _page("https://example.com/deep/nested/page"),
            _page("https://example.com/"),
            _page("https://example.com/shallow"),
        ]
        result = ContentSorter.sort(pages)
        urls = [p.url for p in result]
        # Root (empty path) comes first, then shallow, then deep
        assert urls[0] == "https://example.com/"
        assert urls[1] == "https://example.com/deep/nested/page"
        assert urls[2] == "https://example.com/shallow"

    def test_does_not_mutate_original(self) -> None:
        pages = [
            _page("https://example.com/b"),
            _page("https://example.com/a"),
        ]
        original_urls = [p.url for p in pages]
        ContentSorter.sort(pages)
        assert [p.url for p in pages] == original_urls


class TestContentSorterSortKeys:
    """Tests for the streaming-sort variant: sort_keys on PageIndexEntry."""

    @staticmethod
    def _entry(url: str):
        from pathlib import Path

        from crawl4md.writer import PageIndexEntry

        return PageIndexEntry(
            url=url, sidecar_path=Path("/tmp/x.jsonl"), byte_offset=0, byte_length=1
        )

    def test_sorts_by_url_path(self) -> None:
        entries = [
            self._entry("https://example.com/b/page"),
            self._entry("https://example.com/a/page"),
            self._entry("https://example.com/c/page"),
        ]
        result = ContentSorter.sort_keys(entries)
        assert [e.url for e in result] == [
            "https://example.com/a/page",
            "https://example.com/b/page",
            "https://example.com/c/page",
        ]

    def test_matches_sort_pages_order(self) -> None:
        """sort_keys must produce the same URL order as sort() on equivalent pages."""
        urls = [
            "https://example.com/personal/broadband/plan-a",
            "https://example.com/personal/mobile/plan-x",
            "https://example.com/personal/broadband/plan-b",
            "https://example.com/business/connect",
            "https://example.com/",
        ]
        pages_sorted = ContentSorter.sort([_page(u) for u in urls])
        entries_sorted = ContentSorter.sort_keys([self._entry(u) for u in urls])
        assert [p.url for p in pages_sorted] == [e.url for e in entries_sorted]

    def test_does_not_mutate_original(self) -> None:
        entries = [self._entry("https://example.com/b"), self._entry("https://example.com/a")]
        original_urls = [e.url for e in entries]
        ContentSorter.sort_keys(entries)
        assert [e.url for e in entries] == original_urls
