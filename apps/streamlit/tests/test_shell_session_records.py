"""Tests for the pure session-records cache helpers extracted to the shell.

These exercise ``shell/session_records.py`` directly (no Streamlit runtime): the
cache-key derivation and the memoized normalization with its bounded eviction.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app_support.shell.session_records import (
    SESSION_RECORDS_CACHE_MAX_ENTRIES,
    normalize_session_records_cached,
    session_records_cache_key,
)
from app_support.support import SessionRecord

_CREATED_AT = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)


# Risk: an unstable or colliding cache key would defeat memoization or mix records.
# Type: unit.
def test_cache_key_is_stable_and_distinguishes_payloads() -> None:
    payload_a = [{"session_id": "a", "created_at": "2026-05-13T10:00:00Z"}]
    payload_b = [{"session_id": "b", "created_at": "2026-05-13T10:00:00Z"}]
    assert session_records_cache_key(payload_a) == session_records_cache_key(payload_a)
    assert session_records_cache_key(payload_a) != session_records_cache_key(payload_b)


# Risk: non-record payloads must not raise and must key to empty.
# Type: unit.
def test_cache_key_empty_for_non_iterable_and_strings() -> None:
    assert session_records_cache_key(None) == ()
    assert session_records_cache_key(123) == ()
    assert session_records_cache_key("sessions") == ()
    assert session_records_cache_key(b"bytes") == ()


# Risk: the "sessions" wrapper and both record shapes must each produce a key.
# Type: unit.
def test_cache_key_handles_records_mappings_and_wrapper() -> None:
    from_records = session_records_cache_key([SessionRecord("r", _CREATED_AT, "EN")])
    from_mapping = session_records_cache_key(
        [{"session_id": "r", "created_at": _CREATED_AT.isoformat(), "language": "EN"}]
    )
    from_wrapper = session_records_cache_key(
        {"sessions": [{"session_id": "r", "created_at": "2026-05-13T10:00:00Z"}]}
    )
    assert from_records and from_records[0][0] == "record"
    assert from_mapping and from_mapping[0][0] == "mapping"
    assert from_wrapper and from_wrapper[0][0] == "mapping"


# Risk: a cache miss must normalize and populate; a hit must reuse without recomputing.
# Type: unit.
def test_normalize_cached_populates_then_reuses() -> None:
    cache: dict = {}
    payload = {"sessions": [{"session_id": "a", "created_at": "2026-05-13T10:00:00Z"}]}
    first = normalize_session_records_cached(payload, cache)
    assert [record.session_id for record in first] == ["a"]
    assert len(cache) == 1

    second = normalize_session_records_cached(payload, cache)
    assert second == first
    assert second is not first  # each call returns a fresh list copy
    assert len(cache) == 1


# Risk: mutating the returned list must not corrupt the cached snapshot.
# Type: unit.
def test_normalize_cached_returns_independent_list() -> None:
    cache: dict = {}
    payload = [{"session_id": "a", "created_at": "2026-05-13T10:00:00Z"}]
    normalize_session_records_cached(payload, cache).clear()
    again = normalize_session_records_cached(payload, cache)
    assert [record.session_id for record in again] == ["a"]


# Risk: an unbounded cache leaks memory; it must clear when it hits the entry cap.
# Type: unit.
def test_normalize_cached_clears_at_max_entries() -> None:
    cache: dict = {}
    for index in range(SESSION_RECORDS_CACHE_MAX_ENTRIES):
        normalize_session_records_cached(
            [{"session_id": f"s{index}", "created_at": "2026-05-13T10:00:00Z"}], cache
        )
    assert len(cache) == SESSION_RECORDS_CACHE_MAX_ENTRIES

    normalize_session_records_cached(
        [{"session_id": "overflow", "created_at": "2026-05-13T10:00:00Z"}], cache
    )
    assert len(cache) == 1  # tripping the cap clears, then stores just the new entry
