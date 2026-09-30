"""Pure session-record normalization + cache-key helpers for the shell.

Extracted from ``streamlit_app.py`` so the caching logic is unit-testable without a
Streamlit runtime. The shell keeps only a thin wrapper that supplies the per-session
cache dict from ``st.session_state`` (see ``_cached_normalize_session_records``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app_support.support import SessionRecord, normalize_session_records

__all__ = [
    "SESSION_RECORDS_CACHE_MAX_ENTRIES",
    "SESSION_RECORDS_CACHE_STATE",
    "normalize_session_records_cached",
    "session_records_cache_key",
]

# st.session_state key holding the per-session normalized-records cache dict.
SESSION_RECORDS_CACHE_STATE = "normalized_session_records_cache"
# Cap on distinct cache entries so the cache cannot grow without bound.
SESSION_RECORDS_CACHE_MAX_ENTRIES = 8

_RECORDS_FIELD = "sessions"
_ID_FIELD = "session_id"
_CREATED_AT_FIELD = "created_at"
_LANGUAGE_FIELD = "language"

_CacheKey = tuple[tuple[str, str, str, str], ...]


def session_records_cache_key(payload: object) -> _CacheKey:
    """Return a stable, hashable cache key derived from a records *payload*."""
    raw_records = payload.get(_RECORDS_FIELD, []) if isinstance(payload, Mapping) else payload
    if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Iterable):
        return ()

    key_parts: list[tuple[str, str, str, str]] = []
    for raw_record in raw_records:
        if isinstance(raw_record, SessionRecord):
            key_parts.append(
                (
                    "record",
                    raw_record.session_id,
                    raw_record.created_at.isoformat(),
                    raw_record.language,
                )
            )
            continue
        if isinstance(raw_record, Mapping):
            key_parts.append(
                (
                    "mapping",
                    str(raw_record.get(_ID_FIELD, "")),
                    str(raw_record.get(_CREATED_AT_FIELD, "")),
                    str(raw_record.get(_LANGUAGE_FIELD, "")),
                )
            )
            continue
        key_parts.append(("other", repr(raw_record), "", ""))
    return tuple(key_parts)


def normalize_session_records_cached(
    payload: object, cache: dict[_CacheKey, tuple[SessionRecord, ...]]
) -> list[SessionRecord]:
    """Normalize *payload* into ``SessionRecord``s, memoized in the caller's *cache*.

    On a cache miss the records are normalized fresh; when the cache reaches
    ``SESSION_RECORDS_CACHE_MAX_ENTRIES`` distinct keys it is cleared first so it
    cannot grow without bound.
    """
    cache_key = session_records_cache_key(payload)
    cached_records = cache.get(cache_key)
    if cached_records is not None:
        return list(cached_records)

    records = normalize_session_records(payload)
    if len(cache) >= SESSION_RECORDS_CACHE_MAX_ENTRIES:
        cache.clear()
    cache[cache_key] = tuple(records)
    return records
