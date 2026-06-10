"""UI-agnostic crawl output naming and timestamp helpers.

Crawl-specific names are kept here for backwards compatibility while the generic
naming primitives live in :mod:`artifact_store.naming`.
"""

from __future__ import annotations

from artifact_store.naming import (
    CRAWL_FOLDER_PREFIX,
    UTC_TIMESTAMP_SLUG_FORMAT,
    folder_name,
    format_sequence_id,
    format_utc_timestamp_slug,
    parse_folder_sequence,
    parse_utc_timestamp_slug,
    sequence_sort_key,
)

__all__ = [
    "CRAWL_FOLDER_PREFIX",
    "UTC_TIMESTAMP_SLUG_FORMAT",
    "crawl_folder_name",
    "crawl_sequence_sort_key",
    "format_crawl_id",
    "format_utc_timestamp_slug",
    "parse_crawl_folder_sequence",
    "parse_utc_timestamp_slug",
]


def format_crawl_id(sequence: int, suffix: str, *, width: int = 2) -> str:
    """Return a zero-padded crawl ID such as ``01_example``."""
    return format_sequence_id(sequence, suffix, width=width)


def crawl_folder_name(crawl_id: str) -> str:
    """Return the on-disk crawl folder name for a crawl ID."""
    return folder_name(CRAWL_FOLDER_PREFIX, crawl_id)


def parse_crawl_folder_sequence(folder: str) -> int | None:
    """Return the numeric sequence from ``crawl_01_name`` or legacy ``crawl_1_name``."""
    return parse_folder_sequence(folder, prefix=CRAWL_FOLDER_PREFIX)


def crawl_sequence_sort_key(folder: str) -> tuple[int, int, str]:
    """Return a key that sorts numbered crawl folders newest-first."""
    return sequence_sort_key(folder, prefix=CRAWL_FOLDER_PREFIX)
