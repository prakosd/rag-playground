"""Per-session semantic-search history stored as a downloadable log.

Every search on Step 3 appends a :class:`SearchRecord` to
``search_history/search_history.jsonl`` inside the browser session's output
folder, with a companion CSV for easy download. This module is pure I/O and
parsing (no Streamlit dependency) so the page stays thin and the logic is
unit-testable. Records are capped at the most recent :data:`_MAX_RECORDS` to keep
the file bounded.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from artifact_store.naming import SEARCH_FOLDER_PREFIX

__all__ = [
    "SEARCH_HISTORY_DIRNAME",
    "SearchRecord",
    "append_search_record",
    "load_search_history",
    "search_history_dir",
]

# One folder per session holds the accumulating history. The search_ prefix gives
# it a magnifier icon in the download tree (generated_files.download_folder_icon).
SEARCH_HISTORY_DIRNAME = f"{SEARCH_FOLDER_PREFIX}history"
_HISTORY_FILE = "search_history.jsonl"
_HISTORY_CSV = "search_history.csv"
_MAX_RECORDS = 200
_CSV_COLUMNS = (
    "timestamp_utc",
    "index_folder",
    "index_run",
    "embedding_model",
    "query",
    "search_type",
    "top_k",
    "fetch_k",
    "mmr_lambda",
    "score_threshold",
    "source_filter",
    "result_count",
    "top_score",
)


@dataclass(frozen=True)
class SearchRecord:
    """One semantic search: what was asked, against which index, with what result."""

    timestamp_utc: str
    index_folder: str
    index_run: str
    embedding_model: str
    query: str
    search_type: str
    top_k: int
    fetch_k: int
    mmr_lambda: float
    score_threshold: float
    source_filter: tuple[str, ...] = ()
    result_count: int = 0
    top_score: float | None = None


def search_history_dir(session_root: Path | str) -> Path:
    """Return the per-session ``search_history/`` folder path."""
    return Path(session_root) / SEARCH_HISTORY_DIRNAME


def load_search_history(session_root: Path | str) -> list[SearchRecord]:
    """Return saved records newest-first, skipping malformed lines."""
    records = _read_records(search_history_dir(session_root) / _HISTORY_FILE)
    records.reverse()
    return records


def append_search_record(session_root: Path | str, record: SearchRecord) -> None:
    """Append *record*, keep only the most recent records, and refresh the CSV."""
    directory = search_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    records = _read_records(directory / _HISTORY_FILE)
    records.append(record)
    kept = records[-_MAX_RECORDS:]
    _write_jsonl(directory / _HISTORY_FILE, kept)
    _write_csv(directory / _HISTORY_CSV, kept)


def _read_records(path: Path) -> list[SearchRecord]:
    if not path.is_file():
        return []
    records: list[SearchRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        record = _record_from_payload(payload)
        if record is not None:
            records.append(record)
    return records


def _write_jsonl(path: Path, records: list[SearchRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = asdict(record)
            payload["source_filter"] = list(record.source_filter)
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")


def _write_csv(path: Path, records: list[SearchRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_COLUMNS)
        for record in records:
            writer.writerow(
                [
                    record.timestamp_utc,
                    record.index_folder,
                    record.index_run,
                    record.embedding_model,
                    record.query,
                    record.search_type,
                    record.top_k,
                    record.fetch_k,
                    f"{record.mmr_lambda:.2f}",
                    f"{record.score_threshold:.2f}",
                    ", ".join(record.source_filter),
                    record.result_count,
                    "" if record.top_score is None else f"{record.top_score:.4f}",
                ]
            )


def _record_from_payload(payload: object) -> SearchRecord | None:
    if not isinstance(payload, dict):
        return None
    try:
        top_score = payload.get("top_score")
        return SearchRecord(
            timestamp_utc=str(payload["timestamp_utc"]),
            index_folder=str(payload.get("index_folder", "")),
            index_run=str(payload.get("index_run", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            query=str(payload["query"]),
            search_type=str(payload.get("search_type", "similarity")),
            top_k=int(payload.get("top_k", 0)),
            fetch_k=int(payload.get("fetch_k", 0)),
            mmr_lambda=float(payload.get("mmr_lambda", 0.0)),
            score_threshold=float(payload.get("score_threshold", 0.0)),
            source_filter=tuple(str(source) for source in payload.get("source_filter", []) or []),
            result_count=int(payload.get("result_count", 0)),
            top_score=None if top_score in (None, "") else float(top_score),
        )
    except (KeyError, TypeError, ValueError):
        return None
