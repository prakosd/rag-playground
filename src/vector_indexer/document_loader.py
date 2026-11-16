"""Loads ``.md``/``.txt`` files and ``.zip`` archives into in-memory documents.

Archive members are read through :mod:`artifact_store.archives`, which enforces
the ``.md``/``.txt`` allow-list and rejects unsafe member paths.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from artifact_store import LibraryMessage
from artifact_store.archives import iter_text_members
from vector_indexer import messages
from vector_indexer.models import Document
from vector_indexer.page_source import extract_crawl_date

__all__ = [
    "SUPPORTED_TEXT_SUFFIXES",
    "DocumentLoadResult",
    "iter_documents",
    "load_documents",
]

SUPPORTED_TEXT_SUFFIXES = frozenset({".md", ".txt"})
_ZIP_SUFFIX = ".zip"


@dataclass
class DocumentLoadResult:
    """Documents loaded from inputs plus a record of what was skipped."""

    documents: list[Document] = field(default_factory=list)
    skipped_file_count: int = 0
    warnings: list[LibraryMessage] = field(default_factory=list)


def iter_documents(inputs: Sequence[Path | str], result: DocumentLoadResult) -> Iterator[Document]:
    """Yield documents one at a time, recording skips/warnings on *result*.

    Streaming: each input is read and yielded before the next, so the whole corpus is never
    resident at once. ``result.skipped_file_count`` and ``result.warnings`` are populated as
    iteration proceeds (and are final only once the iterator is fully consumed).
    """
    for raw in inputs:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix in SUPPORTED_TEXT_SUFFIXES:
            yield from _iter_text_file(path, result)
        elif suffix == _ZIP_SUFFIX:
            yield from _iter_zip(path, result)
        else:
            result.skipped_file_count += 1
            result.warnings.append(messages.skipped_unsupported_file(path.name))


def load_documents(inputs: Sequence[Path | str]) -> DocumentLoadResult:
    """Load *inputs* eagerly into a :class:`DocumentLoadResult` (wraps :func:`iter_documents`).

    Supported inputs are ``.md``/``.txt`` files and ``.zip`` archives; archives contribute
    only their ``.md``/``.txt`` members. Unsupported or unreadable inputs are skipped with a
    warning.
    """
    result = DocumentLoadResult()
    result.documents = list(iter_documents(inputs, result))
    return result


def _iter_text_file(path: Path, result: DocumentLoadResult) -> Iterator[Document]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.skipped_file_count += 1
        result.warnings.append(messages.file_unreadable(path.name, str(exc)))
        return
    yield Document(source=path.name, text=text, crawl_date=extract_crawl_date(text))


def _iter_zip(path: Path, result: DocumentLoadResult) -> Iterator[Document]:
    try:
        members = list(iter_text_members(path))
    except (OSError, zipfile.BadZipFile) as exc:
        result.skipped_file_count += 1
        result.warnings.append(messages.archive_unreadable(path.name, str(exc)))
        return
    if not members:
        result.warnings.append(messages.archive_empty(path.name))
        return
    for member_name, data in members:
        text = data.decode("utf-8", errors="replace")
        yield Document(
            source=f"{path.name}:{member_name}",
            text=text,
            crawl_date=extract_crawl_date(text),
        )
