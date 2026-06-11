"""Generated output file helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import calendar
import json
import mimetypes
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path, PurePosixPath
from typing import Any

from artifact_store.naming import (
    VECTOR_FOLDER_PREFIX,
    parse_folder_sequence,
    sequence_sort_key,
)
from crawl4md.naming import (
    CRAWL_FOLDER_PREFIX,
    crawl_sequence_sort_key,
    parse_crawl_folder_sequence,
    parse_utc_timestamp_slug,
)

from crawl4md_streamlit.session_manager import ensure_within_root

_ACTIVITY_LOG_FILE = "activity_log.txt"
_CRAWL_DIR_PREFIX = CRAWL_FOLDER_PREFIX
_VECTOR_DIR_PREFIX = VECTOR_FOLDER_PREFIX
_DEFAULT_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DEFAULT_PREVIEW_MAX_BYTES = 256 * 1024
_HIDDEN_FILE_PREFIX = "."
_FINAL_DIR_NAME = "final"
_MISSING_CACHE_TOKEN = (0.0, 0)
_PROGRESS_HISTORY_FILE = "progress_history.jsonl"
_RUN_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
_SORTED_SUCCESS_CONTENT_GLOB = "sorted_success_content_*"
_SUCCESS_CONTENT_GLOB = "success_content_*"
_SUCCESS_ZIP_NAME = "success_content.zip"
_TEXT_PREVIEW_EXTENSIONS = frozenset(
    {
        ".cfg",
        ".conf",
        ".csv",
        ".htm",
        ".html",
        ".ini",
        ".json",
        ".jsonl",
        ".log",
        ".md",
        ".rst",
        ".text",
        ".toml",
        ".tsv",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True)
class GeneratedFile:
    """Metadata for a generated file that can be shown in Streamlit."""

    path: Path
    relative_path: str
    name: str
    size_bytes: int
    modified_at: datetime
    file_type: str
    download_allowed: bool


@dataclass(frozen=True)
class TextPreview:
    """A capped text preview payload suitable for inline UI display."""

    text: str
    truncated: bool


@dataclass(frozen=True)
class ReadyDownload:
    """A ready-to-download crawl result, either a single file or a zip."""

    file: GeneratedFile
    source_count: int


@dataclass(frozen=True)
class _ScannedGeneratedFile:
    path: Path
    relative_path: str
    name: str
    size_bytes: int
    modified_at: datetime
    file_type: str


def list_generated_files(
    session_root: Path | str,
    search_root: Path | str | None = None,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> list[GeneratedFile]:
    """List generated files under the current session only."""
    root = Path(session_root).resolve()
    target_root = ensure_within_root(root, search_root or root)
    if not target_root.exists():
        return []

    return [
        GeneratedFile(
            path=file.path,
            relative_path=file.relative_path,
            name=file.name,
            size_bytes=file.size_bytes,
            modified_at=file.modified_at,
            file_type=file.file_type,
            download_allowed=file.size_bytes <= download_limit_bytes,
        )
        for file in _scan_generated_files(root, target_root)
    ]


def generated_files_cache_token(path: Path | str) -> tuple[float, int]:
    """Return a cheap cache token for Streamlit generated-file listings."""
    try:
        stat_result = Path(path).stat()
    except OSError:
        return _MISSING_CACHE_TOKEN
    return (stat_result.st_mtime, stat_result.st_size)


def _scan_generated_files(root: Path, target_root: Path) -> list[_ScannedGeneratedFile]:
    scanned: list[_ScannedGeneratedFile] = []
    stack = [target_root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                dir_entries = sorted(entries, key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in dir_entries:
            entry_path = Path(entry.path)
            try:
                safe_path = ensure_within_root(root, entry_path)
            except ValueError:
                continue
            relative = safe_path.relative_to(root)
            if any(part.startswith(_HIDDEN_FILE_PREFIX) for part in relative.parts):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(safe_path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            file_type = safe_path.suffix.lower().lstrip(".") or "file"
            scanned.append(
                _ScannedGeneratedFile(
                    path=safe_path,
                    relative_path=relative.as_posix(),
                    name=safe_path.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    file_type=file_type,
                )
            )
    return sorted(scanned, key=lambda file: generated_file_sort_key(file.relative_path))


def generated_file_sort_key(relative_path: str) -> tuple[int, int, str, str]:
    """Return a sort key that orders numbered crawl runs newest-first."""
    parts = PurePosixPath(relative_path).parts
    if not parts:
        return (1, 0, "", "")
    sequence = parse_crawl_folder_sequence(parts[0])
    if sequence is None:
        return (1, 0, relative_path.lower(), "")
    return (0, -sequence, parts[0].lower(), "/".join(parts[1:]).lower())


def is_text_previewable(path_or_name: Path | str) -> bool:
    """Return True when the file can be shown as plain text in preview UI."""
    file_name = Path(path_or_name).name
    lower_name = file_name.lower()
    if any(lower_name.endswith(ext) for ext in _TEXT_PREVIEW_EXTENSIONS):
        return True
    mime_type = mimetypes.guess_type(file_name)[0]
    return bool(mime_type and mime_type.startswith("text/"))


def preview_created_timestamp(stat_result: Any, *, platform_name: str = os.name) -> float | None:
    """Return a reliable creation timestamp for preview metadata when available."""
    birthtime = getattr(stat_result, "st_birthtime", None)
    if isinstance(birthtime, (int, float)):
        return float(birthtime)
    if platform_name == "nt":
        ctime = getattr(stat_result, "st_ctime", None)
        if isinstance(ctime, (int, float)):
            return float(ctime)
    return None


def read_text_preview(
    path: Path | str,
    *,
    max_bytes: int = _DEFAULT_PREVIEW_MAX_BYTES,
) -> TextPreview:
    """Read up to *max_bytes* from a file and decode as UTF-8 replacement text."""
    if max_bytes < 1:
        raise ValueError("Preview byte limit must be at least 1.")
    preview_path = Path(path)
    if not preview_path.exists() or not preview_path.is_file():
        return TextPreview(text="", truncated=False)
    with preview_path.open("rb") as file_obj:
        raw_bytes = file_obj.read(max_bytes + 1)
    truncated = len(raw_bytes) > max_bytes
    if truncated:
        raw_bytes = raw_bytes[:max_bytes]
    return TextPreview(text=raw_bytes.decode("utf-8", errors="replace"), truncated=truncated)


def read_recent_lines(path: Path | str, *, max_lines: int | None) -> list[str]:
    """Read UTF-8 text file lines, optionally limited to the last *max_lines*."""
    log_path = Path(path)
    if not log_path.exists() or not log_path.is_file():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if max_lines is None:
        return lines
    if max_lines < 1:
        return []
    return lines[-max_lines:]


def find_latest_crawl_dir(crawl_base: Path | str) -> Path | None:
    """Return the newest crawler-created timestamp directory under a crawl base."""
    base = Path(crawl_base)
    if not base.exists():
        return None
    candidates = [path for path in base.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=_crawl_timestamp_dir_sort_key)[0]


def _crawl_timestamp_dir_sort_key(path: Path) -> tuple[int, float, str]:
    parsed = parse_utc_timestamp_slug(path.name)
    if parsed is not None:
        return (0, -parsed.timestamp(), path.name.lower())
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        modified_at = 0.0
    return (1, -modified_at, path.name.lower())


def activity_log_path(crawl_dir: Path | str | None) -> Path | None:
    """Return the activity log path for a crawl output directory when present."""
    if crawl_dir is None:
        return None
    path = Path(crawl_dir) / _ACTIVITY_LOG_FILE
    return path if path.exists() else None


def build_download_tree(files: list[GeneratedFile]) -> dict[str, Any]:
    """Return a nested path tree for generated-file download rendering."""
    tree: dict[str, Any] = {}
    for file in files:
        parts = PurePosixPath(file.relative_path).parts
        node = tree
        for folder in parts[:-1]:
            node = node.setdefault(folder, {})
        node[parts[-1]] = file
    return tree


def download_tree_entry_sort_key(
    name: str,
    entry: Any,
    *,
    top_level: bool = False,
) -> tuple[int, int, str]:
    """Return a tree-entry sort key with newest numbered crawl/vector folders first."""
    if isinstance(entry, dict):
        if top_level and parse_crawl_folder_sequence(name) is not None:
            _, sequence_key, name_key = crawl_sequence_sort_key(name)
            return (0, sequence_key, name_key)
        if top_level and parse_folder_sequence(name, prefix=_VECTOR_DIR_PREFIX) is not None:
            _, sequence_key, name_key = sequence_sort_key(name, prefix=_VECTOR_DIR_PREFIX)
            return (1, sequence_key, name_key)
        return (2, 0, name.lower())
    return (3, 0, name.lower())


def collapse_artifact_run_folder(
    folder_name: str,
    folder_node: dict[str, Any],
    *,
    local_timezone: tzinfo | None = None,
) -> tuple[str, dict[str, Any]]:
    """Merge a crawl/vector folder and its single timestamp child into one label."""
    label = folder_name
    is_artifact_dir = folder_name.startswith(_CRAWL_DIR_PREFIX) or folder_name.startswith(
        _VECTOR_DIR_PREFIX
    )
    if not is_artifact_dir or len(folder_node) != 1:
        return label, folder_node

    child_name, child_entry = next(iter(folder_node.items()))
    if not isinstance(child_entry, dict) or not _RUN_FOLDER_PATTERN.fullmatch(child_name):
        return label, folder_node

    timestamp_label = format_run_timestamp_label(
        child_name,
        child_entry,
        local_timezone=local_timezone,
    )
    return f"{label}/{timestamp_label}", child_entry


def format_run_timestamp_label(
    folder_name: str,
    folder_node: dict[str, Any] | None = None,
    *,
    local_timezone: tzinfo | None = None,
) -> str:
    """Return a timestamp folder label with a local-time companion when possible."""
    timestamp = _progress_history_timestamp(folder_node) if folder_node is not None else None
    if timestamp is None:
        timestamp = parse_utc_timestamp_slug(folder_name)
    if timestamp is None:
        return folder_name
    return f"{folder_name} ({_format_local_timestamp(timestamp, local_timezone=local_timezone)})"


def _format_local_timestamp(value: datetime, *, local_timezone: tzinfo | None = None) -> str:
    target_timezone = local_timezone or datetime.now().astimezone().tzinfo or timezone.utc
    local_value = value.astimezone(timezone.utc).astimezone(target_timezone)
    zone_name = local_value.tzname() or "local"
    month_name = calendar.month_name[local_value.month]
    return (
        f"{local_value.day} {month_name} {local_value.year} "
        f"{local_value.hour:02d}:{local_value.minute:02d} {zone_name}"
    )


def _progress_history_timestamp(folder_node: dict[str, Any] | None) -> datetime | None:
    progress_file = _find_generated_file(folder_node, _PROGRESS_HISTORY_FILE)
    if progress_file is None:
        return None
    try:
        with progress_file.path.open(encoding="utf-8") as handle:
            for line in handle:
                timestamp = _timestamp_from_progress_history_line(line)
                if timestamp is not None:
                    return timestamp
    except OSError:
        return None
    return None


def _find_generated_file(
    folder_node: dict[str, Any] | None, file_name: str
) -> GeneratedFile | None:
    if folder_node is None:
        return None
    for name, entry in folder_node.items():
        if isinstance(entry, GeneratedFile) and name == file_name:
            return entry
        if isinstance(entry, dict):
            found = _find_generated_file(entry, file_name)
            if found is not None:
                return found
    return None


def _timestamp_from_progress_history_line(line: str) -> datetime | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    value = payload.get("timestamp")
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def collect_success_content_files(crawl_output_dir: Path, root: Path) -> list[Path]:
    """Return success content files from the final/ folder of a crawl output directory.

    Prefers ``sorted_success_content_*`` files. Falls back to ``success_content_*``
    (excluding any .zip file) when sorted files are absent.
    """
    try:
        safe_dir = ensure_within_root(root, crawl_output_dir)
    except ValueError:
        return []
    final_dir = safe_dir / _FINAL_DIR_NAME
    if not final_dir.exists():
        return []
    files = sorted(f for f in final_dir.glob(_SORTED_SUCCESS_CONTENT_GLOB) if f.is_file())
    if not files:
        files = sorted(
            f
            for f in final_dir.glob(_SUCCESS_CONTENT_GLOB)
            if f.is_file() and f.suffix.lower() != ".zip"
        )
    return files


def _refresh_success_zip(source_files: list[Path], zip_path: Path) -> None:
    """Create or refresh success_content.zip when any source file is newer."""
    if zip_path.exists():
        zip_mtime = zip_path.stat().st_mtime
        if all(f.stat().st_mtime <= zip_mtime for f in source_files):
            return
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in source_files:
            zf.write(f, f.name)


def build_ready_download(
    crawl_output_dir: Path | str,
    session_root: Path | str,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> ReadyDownload | None:
    """Return the ready-to-download success result for a finished or stopped crawl.

    Returns a single-file ``ReadyDownload`` when only one success content file exists,
    or a zip-based ``ReadyDownload`` when multiple files are present. Returns ``None``
    when no successful content is available or the path is outside the session root.
    """
    root = Path(session_root).resolve()
    try:
        output_dir = ensure_within_root(root, Path(crawl_output_dir))
    except ValueError:
        return None
    source_files = collect_success_content_files(output_dir, root)
    if not source_files:
        return None
    if len(source_files) == 1:
        download_path = source_files[0]
    else:
        zip_path = output_dir / _FINAL_DIR_NAME / _SUCCESS_ZIP_NAME
        _refresh_success_zip(source_files, zip_path)
        download_path = zip_path
    try:
        stat = download_path.stat()
    except OSError:
        return None
    relative = download_path.relative_to(root)
    gf = GeneratedFile(
        path=download_path,
        relative_path=relative.as_posix(),
        name=download_path.name,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        file_type=download_path.suffix.lower().lstrip(".") or "file",
        download_allowed=stat.st_size <= download_limit_bytes,
    )
    return ReadyDownload(file=gf, source_count=len(source_files))


def find_ready_download_in_session(
    session_root: Path | str,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> ReadyDownload | None:
    """Return the most recent ready-to-download result within a session folder.

    Scans ``crawl_*`` subdirectories of *session_root*, finds the newest run
    directory in each, and returns the first ``ReadyDownload`` found when
    searching newest-first. Returns ``None`` when no crawl in the session has
    success content.
    """
    root = Path(session_root).resolve()
    if not root.is_dir():
        return None
    candidates: list[tuple[tuple[int, int, str], tuple[int, float, str], Path]] = []
    for crawl_dir in root.iterdir():
        if not crawl_dir.is_dir() or not crawl_dir.name.startswith(_CRAWL_DIR_PREFIX):
            continue
        run_dir = find_latest_crawl_dir(crawl_dir)
        if run_dir is None:
            continue
        candidates.append(
            (
                crawl_sequence_sort_key(crawl_dir.name),
                _crawl_timestamp_dir_sort_key(run_dir),
                run_dir,
            )
        )
    for _, _, run_dir in sorted(candidates):
        ready = build_ready_download(run_dir, root, download_limit_bytes=download_limit_bytes)
        if ready is not None:
            return ready
    return None
