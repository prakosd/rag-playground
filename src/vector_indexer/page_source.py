"""Recover per-page source from crawl4md output and drop run metadata.

crawl4md writes each output file with a leading YAML *front matter* block (run
metadata such as ``crawl_start_datetime`` and ``session_id``) followed by one or
more pages. Each page's human-readable header (title heading + ``*Source: URL*``
line) is bracketed by render-invisible markers:

    <!-- crawl4md:source -->
    # Page title

    *Source: https://example.com/page*
    <!-- /crawl4md:source -->
    ...page body...

This module is pure stdlib (no heavy imports). It strips the metadata front
matter so it never reaches indexed chunks, splits the remaining text into pages,
and recovers each page's title/URL so the chunker can record them as chunk
metadata. Files without markers (plain ``.txt`` or
non-crawl4md Markdown) degrade to a single untitled page. The marker strings must
stay in sync with ``crawl4md.writer``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["PageSection", "extract_crawl_date", "split_into_pages"]

_PAGE_HEADER_START_MARKER = "<!-- crawl4md:source -->"
_PAGE_HEADER_END_MARKER = "<!-- /crawl4md:source -->"

# A leading YAML front matter block: "---\n ... \n---\n" anchored at the start.
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# The crawl capture date inside that block: crawl_start_datetime: "YYYY-MM-DD...".
_CRAWL_DATE_RE = re.compile(
    r"^crawl_start_datetime:\s*\"?(?P<date>\d{4}-\d{2}-\d{2})", re.MULTILINE
)
# A page header block emitted by crawl4md, capturing the human-readable header.
_PAGE_HEADER_RE = re.compile(
    re.escape(_PAGE_HEADER_START_MARKER) + r"(?P<header>.*?)" + re.escape(_PAGE_HEADER_END_MARKER),
    re.DOTALL,
)
_TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)
_SOURCE_RE = re.compile(r"^\*Source:\s*(?P<url>.+?)\s*\*\s*$", re.MULTILINE)
_SEPARATOR_LINE_RE = re.compile(r"^\s*-{3,}\s*$")


@dataclass(frozen=True)
class PageSection:
    """One page recovered from a crawl4md output file."""

    title: str | None
    url: str | None
    body: str


def split_into_pages(text: str) -> list[PageSection]:
    """Strip run metadata and split *text* into its per-page sections.

    Returns one :class:`PageSection` per page header found. Text without markers
    (front matter removed) becomes a single untitled section; empty input — or
    input that is only metadata/separators — yields an empty list.
    """
    body_text = _FRONT_MATTER_RE.sub("", text, count=1)
    matches = list(_PAGE_HEADER_RE.finditer(body_text))
    if not matches:
        trimmed = _trim_separators(body_text)
        return [PageSection(title=None, url=None, body=trimmed)] if trimmed else []

    sections: list[PageSection] = []
    for position, match in enumerate(matches):
        header = match.group("header")
        title_match = _TITLE_RE.search(header)
        source_match = _SOURCE_RE.search(header)
        body_end = matches[position + 1].start() if position + 1 < len(matches) else len(body_text)
        body = _trim_separators(body_text[match.end() : body_end])
        sections.append(
            PageSection(
                title=title_match.group("title").strip() if title_match else None,
                url=source_match.group("url").strip() if source_match else None,
                body=body,
            )
        )
    return sections


def extract_crawl_date(text: str) -> str | None:
    """Return the crawl capture date (``YYYY-MM-DD``) from the leading front matter.

    Reads ``crawl_start_datetime`` from the crawl4md metadata block and keeps only
    its date part. Returns ``None`` for non-crawl4md input or when the key or a
    valid date is absent, so plain ``.txt`` and foreign Markdown get no date.
    """
    front_matter = _FRONT_MATTER_RE.match(text)
    if front_matter is None:
        return None
    match = _CRAWL_DATE_RE.search(front_matter.group(0))
    return match.group("date") if match else None


def _trim_separators(text: str) -> str:
    """Drop leading/trailing blank lines and ``---`` horizontal-rule separators.

    Only the wrapping separators that crawl4md adds around each page are removed;
    a ``---`` rule in the middle of the body is preserved.
    """
    lines = text.splitlines()
    start, end = 0, len(lines)
    while start < end and _is_trim_line(lines[start]):
        start += 1
    while end > start and _is_trim_line(lines[end - 1]):
        end -= 1
    return "\n".join(lines[start:end])


def _is_trim_line(line: str) -> bool:
    return not line.strip() or bool(_SEPARATOR_LINE_RE.match(line))
