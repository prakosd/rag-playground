from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from crawl4md.naming import (
    crawl_sequence_sort_key,
    format_crawl_id,
    format_utc_timestamp_slug,
    parse_crawl_folder_sequence,
    parse_utc_timestamp_slug,
)


def test_format_crawl_id_zero_pads_sequence() -> None:
    assert format_crawl_id(1, "boulder") == "01_boulder"
    assert format_crawl_id(10, "boulder") == "10_boulder"
    assert format_crawl_id(100, "boulder") == "100_boulder"


def test_format_crawl_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        format_crawl_id(0, "boulder")
    with pytest.raises(ValueError):
        format_crawl_id(1, "")


def test_parse_crawl_folder_sequence_supports_padded_and_legacy_names() -> None:
    assert parse_crawl_folder_sequence("crawl_01_boulder") == 1
    assert parse_crawl_folder_sequence("crawl_1_boulder") == 1
    assert parse_crawl_folder_sequence("crawl_10_river") == 10


def test_parse_crawl_folder_sequence_ignores_non_sequence_names() -> None:
    assert parse_crawl_folder_sequence("crawl_00_boulder") is None
    assert parse_crawl_folder_sequence("crawl_20260504_123045_boulder") is None
    assert parse_crawl_folder_sequence("other_01_boulder") is None


def test_crawl_sequence_sort_key_orders_numbered_folders_descending() -> None:
    folders = ["crawl_01_boulder", "crawl_10_river", "other", "crawl_2_cedar"]

    assert sorted(folders, key=crawl_sequence_sort_key) == [
        "crawl_10_river",
        "crawl_2_cedar",
        "crawl_01_boulder",
        "other",
    ]


def test_format_utc_timestamp_slug_normalizes_aware_datetime() -> None:
    local_timezone = timezone(timedelta(hours=10), "AEST")
    local_value = datetime(2026, 6, 1, 21, 58, 32, tzinfo=local_timezone)

    assert format_utc_timestamp_slug(local_value) == "2026-06-01_11-58-32"


def test_format_utc_timestamp_slug_treats_naive_datetime_as_utc() -> None:
    value = datetime(2026, 6, 1, 11, 58, 32)

    assert format_utc_timestamp_slug(value) == "2026-06-01_11-58-32"


def test_parse_utc_timestamp_slug_returns_aware_utc_datetime() -> None:
    parsed = parse_utc_timestamp_slug("2026-06-01_11-58-32")

    assert parsed == datetime(2026, 6, 1, 11, 58, 32, tzinfo=timezone.utc)
    assert parse_utc_timestamp_slug("not-a-timestamp") is None
