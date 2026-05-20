"""Generated output file helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import mimetypes
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from crawl4md_streamlit.session_manager import ensure_within_root

_ACTIVITY_LOG_FILE = "activity_log.txt"
_CRAWL_DIR_PREFIX = "crawl_"
_DEFAULT_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DEFAULT_PREVIEW_MAX_BYTES = 256 * 1024
_HIDDEN_FILE_PREFIX = "."
_FINAL_DIR_NAME = "final"
_MISSING_CACHE_TOKEN = (0.0, 0)
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
    return sorted(scanned, key=lambda file: file.relative_path)


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
    """Return the newest crawler-created output directory under a crawl base."""
    base = Path(crawl_base)
    if not base.exists():
        return None
    candidates = [path for path in base.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


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


def collapse_crawl_run_folder(
    folder_name: str,
    folder_node: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Merge crawl folder and single timestamp child into a compact UI label."""
    label = folder_name.removeprefix(_CRAWL_DIR_PREFIX)
    if not folder_name.startswith(_CRAWL_DIR_PREFIX) or len(folder_node) != 1:
        return label, folder_node

    child_name, child_entry = next(iter(folder_node.items()))
    if not isinstance(child_entry, dict) or not _RUN_FOLDER_PATTERN.fullmatch(child_name):
        return label, folder_node

    return f"{label}/{child_name}", child_entry


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
