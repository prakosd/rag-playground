"""Discovery of crawl result files that can feed downstream artifact builders.

A completed crawl writes its clean, sorted output into ``<run>/final/``, but a
stopped or in-progress crawl only has per-round snapshots under ``<run>/round_N/``.
The helpers here surface the success content of either case so other tools (for
example a vector indexer) can enumerate it without depending on the crawler or
any UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from artifact_store.naming import (
    CRAWL_FOLDER_PREFIX,
    parse_utc_timestamp_slug,
    sequence_sort_key,
)
from artifact_store.paths import ensure_within_root

__all__ = [
    "SUPPORTED_INPUT_SUFFIXES",
    "CrawlResultFile",
    "list_crawl_result_files",
]

SUPPORTED_INPUT_SUFFIXES = frozenset({".md", ".txt", ".zip"})

_FINAL_DIR_NAME = "final"
_ROUND_DIR_PREFIX = "round_"
_SORTED_SUCCESS_CONTENT_GLOB = "sorted_success_content_*"
_SUCCESS_CONTENT_GLOB = "success_content_*"
_ZIP_SUFFIX = ".zip"


@dataclass(frozen=True)
class CrawlResultFile:
    """A selectable crawl output file that downstream tools can ingest."""

    path: Path
    relative_path: str
    crawl_label: str
    size_bytes: int


def list_crawl_result_files(session_root: Path | str) -> list[CrawlResultFile]:
    """Return selectable crawl result files under *session_root*, newest crawl first.

    Scans ``crawl_*`` subdirectories and, for each crawl's newest run directory,
    surfaces the successfully extracted content. The final sorted output
    (``final/sorted_success_content_*``) is preferred; when a crawl was stopped
    before it finished, this falls back to the unsorted final files and then to
    the newest ``round_N/`` snapshot so partial crawls are still selectable. URL
    lists, failed-page content, and the generated ``success_content.zip`` are not
    returned.
    """
    root = Path(session_root).resolve()
    if not root.is_dir():
        return []
    crawl_dirs = sorted(
        (path for path in root.iterdir() if path.is_dir() and _is_crawl_dir(path.name)),
        key=lambda path: sequence_sort_key(path.name, prefix=CRAWL_FOLDER_PREFIX),
    )
    results: list[CrawlResultFile] = []
    for crawl_dir in crawl_dirs:
        run_dir = _latest_run_dir(crawl_dir)
        if run_dir is None:
            continue
        for content_file in _collect_success_content(run_dir):
            result = _build_result_file(content_file, root, crawl_dir.name)
            if result is not None:
                results.append(result)
    return results


def _is_crawl_dir(name: str) -> bool:
    return name.startswith(CRAWL_FOLDER_PREFIX)


def _collect_success_content(run_dir: Path) -> list[Path]:
    """Return success content files for a run, preferring final/ over round_N/."""
    final_files = _success_content_in_dir(run_dir / _FINAL_DIR_NAME)
    if final_files:
        return final_files
    round_dirs = sorted(
        (
            path
            for path in run_dir.iterdir()
            if path.is_dir() and path.name.startswith(_ROUND_DIR_PREFIX)
        ),
        key=_round_dir_sort_key,
    )
    for round_dir in round_dirs:
        round_files = _success_content_in_dir(round_dir)
        if round_files:
            return round_files
    return []


def _success_content_in_dir(directory: Path) -> list[Path]:
    """Return success content files in *directory*, preferring sorted output."""
    if not directory.is_dir():
        return []
    sorted_files = sorted(f for f in directory.glob(_SORTED_SUCCESS_CONTENT_GLOB) if f.is_file())
    if sorted_files:
        return sorted_files
    return sorted(
        f
        for f in directory.glob(_SUCCESS_CONTENT_GLOB)
        if f.is_file() and f.suffix.lower() != _ZIP_SUFFIX
    )


def _build_result_file(file_path: Path, root: Path, crawl_label: str) -> CrawlResultFile | None:
    try:
        safe_path = ensure_within_root(root, file_path)
        size_bytes = safe_path.stat().st_size
    except (ValueError, OSError):
        return None
    return CrawlResultFile(
        path=safe_path,
        relative_path=safe_path.relative_to(root).as_posix(),
        crawl_label=crawl_label,
        size_bytes=size_bytes,
    )


def _round_dir_sort_key(path: Path) -> tuple[int, str]:
    """Sort round directories with the highest round number first."""
    suffix = path.name[len(_ROUND_DIR_PREFIX) :]
    return (-int(suffix), path.name) if suffix.isdigit() else (0, path.name)


def _latest_run_dir(crawl_dir: Path) -> Path | None:
    runs = [path for path in crawl_dir.iterdir() if path.is_dir()]
    if not runs:
        return None
    return sorted(runs, key=_run_dir_sort_key)[0]


def _run_dir_sort_key(path: Path) -> tuple[int, float, str]:
    parsed = parse_utc_timestamp_slug(path.name)
    if parsed is not None:
        return (0, -parsed.timestamp(), path.name.lower())
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        modified_at = 0.0
    return (1, -modified_at, path.name.lower())
