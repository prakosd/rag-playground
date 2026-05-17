"""HTML preprocessing helpers for ContentExtractor."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from io import StringIO
from itertools import pairwise
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from crawl4md.config import PageConfig

__all__ = ["HTMLPreprocessor", "_WRAPPER_LINK_LABEL"]

_HTML_PARSER = "html.parser"
_STRIKETHROUGH_RE = re.compile(
    r"<(del|s|strike)\b[^>]*>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
_STRIKETHROUGH_MD = r"~~\2~~"
_HEADING_TAG_RE = re.compile(r"^h[1-6]$")
_DATA_ATTR_RE = re.compile(r"^data-")
_TABLE_CELL_BLOCK_TAGS = frozenset({"p", "div"})
_MIN_WRAPPER_TEXT_LEN = 20
_MIN_OVERLAY_SIBLING_LEN = 30
_LINK_FALLBACK_TEXT = "Link"
_WRAPPER_LINK_LABEL = "Learn more"
_JAVASCRIPT_LINK_PREFIX = "javascript:"
_TableCellTags = ("td", "th")
_StrikeTags = ("del", "s", "strike")
_BreakTag = "br"
_HtmlOrSoup = str | BeautifulSoup


class HTMLPreprocessor:
    def __init__(self, page_config: PageConfig) -> None:
        self.page_config = page_config

    @staticmethod
    def coerce_soup(html: _HtmlOrSoup) -> tuple[BeautifulSoup, bool]:
        if isinstance(html, BeautifulSoup):
            return html, False
        return BeautifulSoup(html, _HTML_PARSER), True

    @staticmethod
    def return_html_or_soup(soup: BeautifulSoup, stringify: bool) -> _HtmlOrSoup:
        return str(soup) if stringify else soup

    def preprocess_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        self.filter_tags(soup)
        self.preserve_strikethrough(soup)
        self.space_heading_children(soup)
        self.populate_empty_links(soup)
        self.flatten_table_cells(soup)
        return soup

    @staticmethod
    def strip_data_attributes(html: _HtmlOrSoup) -> _HtmlOrSoup:
        soup, stringify = HTMLPreprocessor.coerce_soup(html)
        for tag in soup.find_all(True):
            names = [attr_name for attr_name in tag.attrs if _DATA_ATTR_RE.match(attr_name)]
            for name in names:
                del tag[name]
        return HTMLPreprocessor.return_html_or_soup(soup, stringify)

    @staticmethod
    def link_text_from_href(href: str) -> str:
        path = urlparse(href).path.rstrip("/")
        if path:
            segment = path.rsplit("/", 1)[-1]
            dot = segment.rfind(".")
            if dot > 0:
                segment = segment[:dot]
            if segment:
                return segment.replace("-", " ").replace("_", " ").title()
        return _LINK_FALLBACK_TEXT

    @staticmethod
    def populate_empty_links(html: _HtmlOrSoup) -> _HtmlOrSoup:
        soup, stringify = HTMLPreprocessor.coerce_soup(html)
        relocate: list[Tag] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith(("#", _JAVASCRIPT_LINK_PREFIX)):
                continue
            had_children = bool(anchor.find(True))
            child_text = anchor.get_text(strip=True)
            if had_children and child_text and len(child_text) >= _MIN_WRAPPER_TEXT_LEN:
                reference = soup.new_tag("a", href=href)
                reference.string = _WRAPPER_LINK_LABEL
                anchor.insert_after(reference)
                reference.insert_before(" ")
                anchor.unwrap()
                continue
            if child_text or had_children:
                continue
            text = (
                (anchor.get("title") or "").strip()
                or (anchor.get("aria-label") or "").strip()
                or HTMLPreprocessor.link_text_from_href(href)
            )
            anchor.string = text
            if anchor.parent is not None:
                sibling_text = "".join(
                    sibling.get_text(strip=True)
                    for sibling in anchor.parent.children
                    if sibling is not anchor and isinstance(sibling, Tag)
                )
                if len(sibling_text) >= _MIN_OVERLAY_SIBLING_LEN:
                    relocate.append(anchor)
        for anchor in relocate:
            parent = anchor.parent
            if parent is not None:
                anchor.extract()
                parent.append(anchor)
        return HTMLPreprocessor.return_html_or_soup(soup, stringify)

    @staticmethod
    def space_heading_children(html: _HtmlOrSoup) -> _HtmlOrSoup:
        soup, stringify = HTMLPreprocessor.coerce_soup(html)
        for heading in soup.find_all(_HEADING_TAG_RE):
            children = list(heading.children)
            if len(children) < 2:
                continue
            for first_child, second_child in pairwise(children):
                if isinstance(first_child, Tag) and isinstance(second_child, Tag):
                    first_child.insert_after(NavigableString(" "))
        return HTMLPreprocessor.return_html_or_soup(soup, stringify)

    @staticmethod
    def preserve_strikethrough(html: _HtmlOrSoup) -> _HtmlOrSoup:
        if isinstance(html, BeautifulSoup):
            for tag in html.find_all(_StrikeTags):
                tag.insert_before(NavigableString("~~"))
                tag.insert_after(NavigableString("~~"))
                tag.unwrap()
            return html
        return _STRIKETHROUGH_RE.sub(_STRIKETHROUGH_MD, html)

    @staticmethod
    def flatten_table_cells(html: _HtmlOrSoup) -> _HtmlOrSoup:
        soup, stringify = HTMLPreprocessor.coerce_soup(html)
        cells = soup.find_all(_TableCellTags)
        if not cells:
            return html
        modified = False
        for cell in cells:
            for break_tag in cell.find_all(_BreakTag):
                break_tag.insert_before(" ")
                break_tag.unwrap()
                modified = True
            for tag in cell.find_all(list(_TABLE_CELL_BLOCK_TAGS)):
                tag.unwrap()
                modified = True
        if not modified:
            return html
        return HTMLPreprocessor.return_html_or_soup(soup, stringify)

    def filter_tags(self, html: _HtmlOrSoup) -> _HtmlOrSoup:
        if not self.page_config.include_only_tags and not self.page_config.exclude_tags:
            return html

        if isinstance(html, BeautifulSoup):
            include_only = [tag_name.lower() for tag_name in self.page_config.include_only_tags]
            exclude = [tag_name.lower() for tag_name in self.page_config.exclude_tags]
            if exclude:
                for tag in html.find_all(exclude):
                    tag.decompose()
                return html
            included = [
                tag
                for tag in html.find_all(include_only)
                if not any(
                    parent.name in include_only for parent in tag.parents if isinstance(parent, Tag)
                )
            ]
            included = [tag.extract() for tag in included]
            html.clear()
            for tag in included:
                html.append(tag)
            return html

        parser = _TagFilter(
            include_only=self.page_config.include_only_tags,
            exclude=self.page_config.exclude_tags,
        )
        parser.feed(html)
        return parser.output.getvalue()


class _TagFilter(HTMLParser):
    def __init__(self, include_only: list[str], exclude: list[str]) -> None:
        super().__init__()
        self.include_only = [tag_name.lower() for tag_name in include_only]
        self.exclude = [tag_name.lower() for tag_name in exclude]
        self.output = StringIO()
        self._skip_depth = 0
        self._include_depth = 0 if include_only else 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if self.exclude and tag_lower in self.exclude:
            self._skip_depth += 1
            return
        if self.include_only and tag_lower in self.include_only:
            self._include_depth += 1
        if self._skip_depth == 0 and self._include_depth > 0:
            attr_str = "".join(
                f' {attr_name}="{attr_value}"' if attr_value else f" {attr_name}"
                for attr_name, attr_value in attrs
            )
            self.output.write(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self.exclude and tag_lower in self.exclude:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth == 0 and self._include_depth > 0:
            self.output.write(f"</{tag}>")
        if self.include_only and tag_lower in self.include_only:
            self._include_depth = max(0, self._include_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._include_depth > 0:
            self.output.write(data)
