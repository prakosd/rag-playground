"""UI-agnostic crawl output naming and timestamp helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone

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

CRAWL_FOLDER_PREFIX = "crawl_"
UTC_TIMESTAMP_SLUG_FORMAT = "%Y-%m-%d_%H-%M-%S"

_CRAWL_ID_PADDING = 2
_CRAWL_SEQUENCE_PATTERN = re.compile(r"^crawl_(?P<sequence>\d+)(?:_(?P<rest>.*))?$")
_TIMESTAMP_ID_SECOND_PART_LENGTH = 6


def format_crawl_id(sequence: int, suffix: str, *, width: int = _CRAWL_ID_PADDING) -> str:
    """Return a zero-padded crawl ID such as ``01_example``."""
    if sequence < 1:
        raise ValueError("Crawl sequence must be at least 1.")
    normalized_suffix = suffix.strip("_")
    if not normalized_suffix:
        raise ValueError("Crawl suffix must not be empty.")
    return f"{sequence:0{width}d}_{normalized_suffix}"


def crawl_folder_name(crawl_id: str) -> str:
    """Return the on-disk crawl folder name for a crawl ID."""
    return (
        crawl_id if crawl_id.startswith(CRAWL_FOLDER_PREFIX) else f"{CRAWL_FOLDER_PREFIX}{crawl_id}"
    )


def parse_crawl_folder_sequence(folder_name: str) -> int | None:
    """Return the numeric sequence from ``crawl_01_name`` or legacy ``crawl_1_name``."""
    match = _CRAWL_SEQUENCE_PATTERN.fullmatch(folder_name)
    if match is None:
        return None
    rest = match.group("rest") or ""
    rest_first_part = rest.split("_", 1)[0]
    if len(rest_first_part) == _TIMESTAMP_ID_SECOND_PART_LENGTH and rest_first_part.isdigit():
        return None
    try:
        sequence = int(match.group("sequence"))
    except ValueError:
        return None
    return sequence if sequence > 0 else None


def crawl_sequence_sort_key(folder_name: str) -> tuple[int, int, str]:
    """Return a key that sorts numbered crawl folders newest-first."""
    sequence = parse_crawl_folder_sequence(folder_name)
    if sequence is None:
        return (1, 0, folder_name.lower())
    return (0, -sequence, folder_name.lower())


def format_utc_timestamp_slug(value: datetime | None = None) -> str:
    """Return a UTC timestamp slug for crawl output directories."""
    normalized = _normalize_utc_datetime(value or datetime.now(timezone.utc))
    return normalized.strftime(UTC_TIMESTAMP_SLUG_FORMAT)


def parse_utc_timestamp_slug(value: str) -> datetime | None:
    """Parse a crawl timestamp slug as a UTC datetime."""
    try:
        parsed = datetime.strptime(value, UTC_TIMESTAMP_SLUG_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
