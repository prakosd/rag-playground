from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from artifact_store.naming import (
    CRAWL_FOLDER_PREFIX,
    VECTOR_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    format_utc_timestamp_slug,
    parse_folder_sequence,
    parse_utc_timestamp_slug,
    sequence_sort_key,
)


def test_format_sequence_id_zero_pads_sequence() -> None:
    assert format_sequence_id(1, "boulder") == "01_boulder"
    assert format_sequence_id(10, "boulder") == "10_boulder"
    assert format_sequence_id(100, "boulder") == "100_boulder"


def test_format_sequence_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        format_sequence_id(0, "boulder")
    with pytest.raises(ValueError):
        format_sequence_id(1, "")


def test_folder_name_adds_prefix_only_when_missing() -> None:
    assert folder_name(CRAWL_FOLDER_PREFIX, "01_x") == "crawl_01_x"
    assert folder_name(CRAWL_FOLDER_PREFIX, "crawl_01_x") == "crawl_01_x"
    assert folder_name(VECTOR_FOLDER_PREFIX, "01_x") == "vector_01_x"


def test_parse_folder_sequence_supports_crawl_and_vector_prefixes() -> None:
    assert parse_folder_sequence("crawl_01_boulder") == 1
    assert parse_folder_sequence("crawl_1_boulder") == 1
    assert parse_folder_sequence("vector_10_river", prefix=VECTOR_FOLDER_PREFIX) == 10


def test_parse_folder_sequence_ignores_non_sequence_names() -> None:
    assert parse_folder_sequence("crawl_00_boulder") is None
    assert parse_folder_sequence("crawl_20260504_123045_boulder") is None
    assert parse_folder_sequence("other_01_boulder") is None
    assert parse_folder_sequence("vector_01_x") is None  # default prefix is crawl_


def test_sequence_sort_key_orders_numbered_folders_descending() -> None:
    folders = ["vector_01_b", "vector_10_r", "other", "vector_2_c"]

    ordered = sorted(folders, key=lambda name: sequence_sort_key(name, prefix=VECTOR_FOLDER_PREFIX))

    assert ordered == ["vector_10_r", "vector_2_c", "vector_01_b", "other"]


def test_format_utc_timestamp_slug_normalizes_aware_datetime() -> None:
    local_timezone = timezone(timedelta(hours=10), "AEST")
    local_value = datetime(2026, 6, 1, 21, 58, 32, tzinfo=local_timezone)

    assert format_utc_timestamp_slug(local_value) == "2026-06-01_11-58-32"


def test_parse_utc_timestamp_slug_round_trips() -> None:
    parsed = parse_utc_timestamp_slug("2026-06-01_11-58-32")

    assert parsed == datetime(2026, 6, 1, 11, 58, 32, tzinfo=timezone.utc)


def test_parse_utc_timestamp_slug_rejects_invalid_value() -> None:
    assert parse_utc_timestamp_slug("not-a-timestamp") is None
