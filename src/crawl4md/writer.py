"""FileWriter — combines extracted pages into size-limited output files."""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crawl4md.config import ExtractedPage

_SEPARATOR = "\n\n---\n\n"
_MB = 1024 * 1024

# Prefix for numbered content output files (e.g. "content_001.txt")
_CONTENT_PREFIX = "content_"
# Zero-padding width for file index numbers (e.g. 3 → 001, 002, …)
_FILE_INDEX_WIDTH = 3
_YAML_FRONT_MATTER_DELIMITER = "---\n"


@dataclass(frozen=True)
class PageIndexEntry:
    """Lightweight pointer to a page stored in a JSONL sidecar.

    Used by streaming sort: we sort lists of these entries (cheap —
    only short strings and ints) and then read each ``ExtractedPage``
    back from disk via :meth:`PageSidecar.read_page_at` in sorted
    order, so the full corpus never lives in RAM at once.
    """

    url: str
    sidecar_path: Path
    byte_offset: int
    byte_length: int


class FileWriter:
    """Writes extracted Markdown content to numbered output files.

    Each page is preceded by a URL header and separator.  Files are split
    when adding another page would exceed ``max_file_size_mb``.  A single
    page is **never** split across two files.

    Supports two usage modes:

    **Batch mode** (original API)::

        writer = FileWriter()
        files = writer.write(pages, output_dir, max_file_size_mb)

    **Incremental mode** (for flushing during a crawl)::

        writer = FileWriter(output_dir, max_file_size_mb)
        for page in pages:
            writer.add(page)
        files = writer.flush()
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        max_file_size_mb: float = 15.0,
        file_extension: str = ".txt",
        prefix: str = "",
        run_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._output_dir = Path(output_dir) if output_dir else None
        self._max_bytes = int(max_file_size_mb * _MB)
        self._max_file_size_mb = max_file_size_mb
        self._file_extension = file_extension
        self._prefix = prefix
        self._file_index = 1
        self._current_chunks: list[str] = []
        self._current_size = 0
        self._bytes_on_disk = 0  # bytes already written to the current file
        self._files: list[Path] = []
        self._run_metadata: dict[str, Any] = run_metadata.copy() if run_metadata else {}

    def set_run_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Set run metadata used to render file-level YAML front matter."""
        self._run_metadata = metadata.copy() if metadata else {}

    # ------------------------------------------------------------------
    # Incremental API
    # ------------------------------------------------------------------

    def add(self, page: ExtractedPage) -> None:
        """Add a single page to the write buffer.

        When the current file would exceed ``max_file_size_mb``, the
        buffer is flushed and a new file is started automatically.
        """
        assert self._output_dir is not None, "output_dir required for incremental mode"
        block = self._format_page(page)
        block_size = len(block.encode("utf-8"))

        if block_size > self._max_bytes:
            warnings.warn(
                f"Page {page.url} ({block_size / _MB:.1f} MB) exceeds the "
                f"{self._max_file_size_mb} MB limit and will be saved as its own file.",
                stacklevel=2,
            )
            # Flush current buffer to the current file first
            self._flush_buffer()
            # If the current file already has data, move to a new file
            if self._bytes_on_disk > 0:
                self._file_index += 1
                self._bytes_on_disk = 0
            # Write oversized page alone in its own file
            self._write_file([block])
            self._file_index += 1
            self._bytes_on_disk = 0
            return

        total = self._bytes_on_disk + self._current_size + block_size
        if total > self._max_bytes and (self._current_chunks or self._bytes_on_disk > 0):
            # Current file is full — flush buffer, then start a new file
            self._flush_buffer()
            self._file_index += 1
            self._bytes_on_disk = 0

        self._current_chunks.append(block)
        self._current_size += block_size

    def flush(self) -> list[Path]:
        """Flush the in-memory buffer to disk and return all files created."""
        self._flush_buffer()
        return list(self._files)

    def reset(self, prefix: str = "") -> None:
        """Reset the writer for a new round with a different file prefix."""
        self._prefix = prefix
        self._file_index = 1
        self._current_chunks = []
        self._current_size = 0
        self._bytes_on_disk = 0
        self._files = []

    # ------------------------------------------------------------------
    # Batch API (backward-compatible)
    # ------------------------------------------------------------------

    def write(
        self,
        pages: list[ExtractedPage],
        output_dir: Path | str,
        max_file_size_mb: float = 15.0,
        file_extension: str | None = None,
    ) -> list[Path]:
        """Write pages to numbered text files and return created paths."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = file_extension if file_extension is not None else self._file_extension

        max_bytes = int(max_file_size_mb * _MB)
        files: list[Path] = []
        current_chunks: list[str] = []
        current_size = 0
        file_index = 1

        for page in pages:
            block = self._format_page(page)
            block_size = len(block.encode("utf-8"))

            if block_size > max_bytes:
                warnings.warn(
                    f"Page {page.url} ({block_size / _MB:.1f} MB) exceeds the "
                    f"{max_file_size_mb} MB limit and will be saved as its own file.",
                    stacklevel=2,
                )
                # Flush current buffer first
                if current_chunks:
                    files.append(
                        self._write_to_with_prefix(output_dir, file_index, current_chunks, ext)
                    )
                    file_index += 1
                    current_chunks = []
                    current_size = 0
                # Write oversized page alone
                files.append(self._write_to_with_prefix(output_dir, file_index, [block], ext))
                file_index += 1
                continue

            if current_size + block_size > max_bytes and current_chunks:
                files.append(
                    self._write_to_with_prefix(output_dir, file_index, current_chunks, ext)
                )
                file_index += 1
                current_chunks = []
                current_size = 0

            current_chunks.append(block)
            current_size += block_size

        if current_chunks:
            files.append(self._write_to_with_prefix(output_dir, file_index, current_chunks, ext))

        return files

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _flush_buffer(self) -> None:
        """Append the in-memory buffer to the current file on disk."""
        if not self._current_chunks:
            return
        assert self._output_dir is not None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = (
            self._output_dir
            / f"{self._prefix}{_CONTENT_PREFIX}{self._file_index:0{_FILE_INDEX_WIDTH}d}{self._file_extension}"
        )
        self._write_file_header_if_needed(path)
        with path.open("ab") as fh:
            fh.write("".join(self._current_chunks).encode("utf-8"))
        if path not in self._files:
            self._files.append(path)
        self._bytes_on_disk = path.stat().st_size
        self._current_chunks = []
        self._current_size = 0

    def _write_file(self, chunks: list[str]) -> None:
        """Write chunks to the current file index (used for oversized pages)."""
        assert self._output_dir is not None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = (
            self._output_dir
            / f"{self._prefix}{_CONTENT_PREFIX}{self._file_index:0{_FILE_INDEX_WIDTH}d}{self._file_extension}"
        )
        self._write_file_header_if_needed(path)
        with path.open("ab") as fh:
            fh.write("".join(chunks).encode("utf-8"))
        if path not in self._files:
            self._files.append(path)

    @staticmethod
    def _format_page(page: ExtractedPage) -> str:
        """Format a single page as a Markdown block with metadata header."""
        parts = [_SEPARATOR]
        if page.title:
            parts.append(f"# {page.title}\n\n")
        parts.append(f"*Source: {page.url}*\n")
        parts.append(_SEPARATOR)
        parts.append(page.markdown)
        parts.append("\n")
        return "".join(parts)

    @staticmethod
    def _write_to(output_dir: Path, index: int, chunks: list[str], ext: str = ".txt") -> Path:
        """Write chunks to a numbered output file (batch mode helper)."""
        filename = f"{_CONTENT_PREFIX}{index:0{_FILE_INDEX_WIDTH}d}{ext}"
        path = output_dir / filename
        path.write_bytes("".join(chunks).encode("utf-8"))
        return path

    def _write_to_with_prefix(
        self,
        output_dir: Path,
        index: int,
        chunks: list[str],
        ext: str = ".txt",
    ) -> Path:
        """Write chunks to a numbered output file including writer prefix."""
        filename = f"{self._prefix}{_CONTENT_PREFIX}{index:0{_FILE_INDEX_WIDTH}d}{ext}"
        path = output_dir / filename
        self._write_file_header_if_needed(path)
        with path.open("ab") as fh:
            fh.write("".join(chunks).encode("utf-8"))
        return path

    def _write_file_header_if_needed(self, path: Path) -> None:
        """Write YAML front matter once at the top of each new content file."""
        try:
            if path.stat().st_size > 0:
                return
        except FileNotFoundError:
            pass

        front_matter = self._build_front_matter(path.parent)
        if not front_matter:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as fh:
            fh.write(front_matter.encode("utf-8"))

    def _build_front_matter(self, stored_directory: Path) -> str:
        """Build file-level YAML metadata for generated crawl content files."""
        if not self._run_metadata:
            return ""

        status = "success"
        if self._prefix.startswith("fail_") or self._prefix.startswith("sorted_fail_"):
            status = "failed"

        data: dict[str, Any] = {
            "crawl_start_datetime": self._run_metadata.get("crawl_start_datetime"),
            "session_id": self._run_metadata.get("session_id"),
            "stored_directory": str(stored_directory),
            "crawl_parameters": self._run_metadata.get("crawl_parameters", {}),
            "status": status,
        }

        lines = [_YAML_FRONT_MATTER_DELIMITER]
        for key, value in data.items():
            self._append_yaml_key_value(lines, key, value)
        lines.append(_YAML_FRONT_MATTER_DELIMITER)
        return "".join(lines)

    @classmethod
    def _append_yaml_key_value(
        cls,
        lines: list[str],
        key: str,
        value: Any,
        *,
        indent: int = 0,
    ) -> None:
        """Append one YAML key/value entry, expanding nested objects as needed."""
        prefix = " " * indent
        if isinstance(value, dict):
            if not value:
                lines.append(f"{prefix}{key}: {{}}\n")
                return
            lines.append(f"{prefix}{key}:\n")
            for child_key, child_value in value.items():
                cls._append_yaml_key_value(
                    lines,
                    str(child_key),
                    child_value,
                    indent=indent + 2,
                )
            return

        if isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []\n")
                return
            lines.append(f"{prefix}{key}:\n")
            cls._append_yaml_list(lines, value, indent=indent + 2)
            return

        lines.append(f"{prefix}{key}: {cls._yaml_scalar(value)}\n")

    @classmethod
    def _append_yaml_list(cls, lines: list[str], values: list[Any], *, indent: int = 0) -> None:
        """Append YAML list items, expanding nested containers recursively."""
        prefix = " " * indent
        for item in values:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{prefix}- {{}}\n")
                    continue
                lines.append(f"{prefix}-\n")
                for child_key, child_value in item.items():
                    cls._append_yaml_key_value(
                        lines,
                        str(child_key),
                        child_value,
                        indent=indent + 2,
                    )
                continue

            if isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}- []\n")
                    continue
                lines.append(f"{prefix}-\n")
                cls._append_yaml_list(lines, item, indent=indent + 2)
                continue

            lines.append(f"{prefix}- {cls._yaml_scalar(item)}\n")

    @staticmethod
    def _yaml_scalar(value: Any) -> str:
        """Render a JSON-serializable scalar/object in a YAML-compatible form."""
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        return str(value)


def rename_files_with_total(files: list[Path]) -> list[Path]:
    """Rename numbered content files to include the total file count.

    ``content_001.md`` → ``content_001_of_003.md`` (when *files* has 3 items).

    Returns the list of new ``Path`` objects after renaming.
    """
    total = len(files)
    if not total:
        return []
    suffix = f"_of_{total:0{_FILE_INDEX_WIDTH}d}"
    renamed: list[Path] = []
    for path in files:
        new_name = f"{path.stem}{suffix}{path.suffix}"
        target_path = path.parent / new_name
        if target_path.exists() and target_path != path:
            target_path.unlink()
        new_path = path.rename(target_path)
        renamed.append(new_path)
    return renamed


class PageSidecar:
    """Append/read ``ExtractedPage`` objects as JSONL for memory-efficient crawls.

    Each line is a self-contained JSON object produced by Pydantic's
    ``model_dump_json()``, so the file is trivially round-trippable
    without parsing the formatted Markdown content files.

    The file is **append-only**.  Streaming sort relies on byte offsets
    captured by :meth:`iter_index` remaining valid for the lifetime of
    the file — never rewrite or truncate sidecars after the fact.
    """

    @staticmethod
    def append(page: ExtractedPage, path: Path) -> None:
        """Serialize *page* and append it as one JSONL line."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(page.model_dump_json())
            fh.write("\n")

    @staticmethod
    def read_pages(path: Path) -> Iterator[ExtractedPage]:
        """Yield ``ExtractedPage`` objects from a JSONL sidecar file."""
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield ExtractedPage.model_validate_json(line)

    @staticmethod
    def iter_index(path: Path) -> Iterator[PageIndexEntry]:
        """Yield one lightweight ``PageIndexEntry`` per record in *path*.

        Streams the file once and parses each JSON line only to extract
        the ``url`` field — the heavy ``markdown`` string is allocated
        briefly during JSON parsing, then discarded.  Memory cost stays
        O(1) per record, which lets sort steps handle large corpora
        without materialising every page at once.

        Records with missing ``url`` or empty ``markdown`` are skipped,
        matching the historical behaviour of dedup helpers.
        """
        if not path.exists():
            return
        offset = 0
        with path.open("rb") as fh:
            for raw_line in fh:
                length = len(raw_line)
                stripped = raw_line.strip()
                if stripped:
                    obj = json.loads(stripped)
                    url = obj.get("url", "")
                    markdown = obj.get("markdown", "")
                    if url and markdown.strip():
                        yield PageIndexEntry(
                            url=url,
                            sidecar_path=path,
                            byte_offset=offset,
                            byte_length=length,
                        )
                offset += length

    @staticmethod
    def read_page_at(path: Path, byte_offset: int, byte_length: int) -> ExtractedPage:
        """Read a single ``ExtractedPage`` at the given byte offset."""
        with path.open("rb") as fh:
            fh.seek(byte_offset)
            raw = fh.read(byte_length)
        return ExtractedPage.model_validate_json(raw)
