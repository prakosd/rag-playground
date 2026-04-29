"""ContentSorter — sorts extracted pages by URL path for grouped output."""

from __future__ import annotations

from urllib.parse import urlparse

from crawl4md.config import ExtractedPage
from crawl4md.writer import PageIndexEntry


class ContentSorter:
    """Sorts pages so that content from related URL paths is grouped together.

    Pages are sorted lexicographically by their URL path segments, which
    naturally clusters pages under the same directory (e.g. all
    ``/personal/mobile/...`` pages appear together).  The sort is stable,
    so pages with identical paths retain their original crawl order.
    """

    @staticmethod
    def sort(pages: list[ExtractedPage]) -> list[ExtractedPage]:
        """Return a new list of pages sorted by URL path segments."""
        return sorted(pages, key=ContentSorter._sort_key)

    @staticmethod
    def sort_keys(entries: list[PageIndexEntry]) -> list[PageIndexEntry]:
        """Return a new list of index entries sorted by URL path segments.

        Used by streaming sort to avoid materialising every page in RAM.
        """
        return sorted(entries, key=ContentSorter._sort_key_url)

    @staticmethod
    def _sort_key(page: ExtractedPage) -> tuple[str, ...]:
        """Generate a sort key from URL path segments."""
        return ContentSorter._sort_key_url(page)

    @staticmethod
    def _sort_key_url(item: ExtractedPage | PageIndexEntry) -> tuple[str, ...]:
        """Generate a sort key from the URL of *item*.

        Works for both ``ExtractedPage`` and ``PageIndexEntry`` since
        they expose ``.url`` identically.
        """
        parsed = urlparse(item.url)
        segments = [s for s in parsed.path.split("/") if s]
        return tuple(segments)
