"""Shared, UI-agnostic helpers for managing persisted project artifacts.

``artifact_store`` is the foundation layer shared by the crawl4md core library,
the vector_indexer library, and UI apps. It owns artifact naming, timestamp
slugs, path-containment safety, safe archive extraction, and crawl-result
discovery. It must not depend on any UI framework or crawler engine.
"""

from __future__ import annotations

from artifact_store.archives import (
    TEXT_MEMBER_SUFFIXES,
    extract_text_members,
    is_safe_member_name,
    iter_text_members,
)
from artifact_store.crawl_results import (
    SUPPORTED_INPUT_SUFFIXES,
    CrawlResultFile,
    list_crawl_result_files,
)
from artifact_store.messages import (
    MESSAGE_SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    LibraryMessage,
)
from artifact_store.naming import (
    CRAWL_FOLDER_PREFIX,
    UTC_TIMESTAMP_SLUG_FORMAT,
    VECTOR_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    format_utc_timestamp_slug,
    parse_folder_sequence,
    parse_utc_timestamp_slug,
    sequence_sort_key,
)
from artifact_store.paths import ensure_within_root

__all__ = [
    "CRAWL_FOLDER_PREFIX",
    "MESSAGE_SEVERITIES",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SUPPORTED_INPUT_SUFFIXES",
    "TEXT_MEMBER_SUFFIXES",
    "UTC_TIMESTAMP_SLUG_FORMAT",
    "VECTOR_FOLDER_PREFIX",
    "CrawlResultFile",
    "LibraryMessage",
    "ensure_within_root",
    "extract_text_members",
    "folder_name",
    "format_sequence_id",
    "format_utc_timestamp_slug",
    "is_safe_member_name",
    "iter_text_members",
    "list_crawl_result_files",
    "parse_folder_sequence",
    "parse_utc_timestamp_slug",
    "sequence_sort_key",
]
