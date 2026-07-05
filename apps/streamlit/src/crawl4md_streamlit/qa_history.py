"""Per-session Simple RAG Q&A history stored as a downloadable log.

Every prompt sent on Step 4 appends a :class:`QaRecord` to
``rag_qa_history/qa_history.jsonl`` inside the browser session's output folder,
with a companion CSV for easy download. Like :mod:`search_history`, this module
is pure I/O and parsing (no Streamlit dependency) so the page stays thin and the
logic is unit-testable. Records are capped at the most recent :data:`_MAX_RECORDS`.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from artifact_store.naming import RAG_QA_FOLDER_PREFIX

__all__ = [
    "QA_HISTORY_DIRNAME",
    "QaRecord",
    "append_qa_record",
    "load_qa_history",
    "qa_history_dir",
]

# One folder per session holds the accumulating history. The rag_qa_ prefix gives
# it a Q&A icon in the download tree (generated_files.download_folder_icon).
QA_HISTORY_DIRNAME = f"{RAG_QA_FOLDER_PREFIX}history"
_HISTORY_FILE = "qa_history.jsonl"
_HISTORY_CSV = "qa_history.csv"
_MAX_RECORDS = 200
_CSV_COLUMNS = (
    "timestamp_utc",
    "index_folder",
    "index_run",
    "embedding_model",
    "llm_model",
    "tone",
    "top_k",
    "question",
    "prompt",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "latency_seconds",
)


@dataclass(frozen=True)
class QaRecord:
    """One Step 4 request: the prompt sent, against which index, and its cost."""

    timestamp_utc: str
    index_folder: str
    index_run: str
    embedding_model: str
    llm_model: str
    tone: str
    top_k: int
    question: str
    prompt: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_seconds: float = 0.0


def qa_history_dir(session_root: Path | str) -> Path:
    """Return the per-session ``rag_qa_history/`` folder path."""
    return Path(session_root) / QA_HISTORY_DIRNAME


def load_qa_history(session_root: Path | str) -> list[QaRecord]:
    """Return saved records newest-first, skipping malformed lines."""
    records = _read_records(qa_history_dir(session_root) / _HISTORY_FILE)
    records.reverse()
    return records


def append_qa_record(session_root: Path | str, record: QaRecord) -> None:
    """Append *record*, keep only the most recent records, and refresh the CSV."""
    directory = qa_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    records = _read_records(directory / _HISTORY_FILE)
    records.append(record)
    kept = records[-_MAX_RECORDS:]
    _write_jsonl(directory / _HISTORY_FILE, kept)
    _write_csv(directory / _HISTORY_CSV, kept)


def _read_records(path: Path) -> list[QaRecord]:
    if not path.is_file():
        return []
    records: list[QaRecord] = []
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


def _write_jsonl(path: Path, records: list[QaRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False))
            handle.write("\n")


def _write_csv(path: Path, records: list[QaRecord]) -> None:
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
                    record.llm_model,
                    record.tone,
                    record.top_k,
                    record.question,
                    record.prompt,
                    "" if record.input_tokens is None else record.input_tokens,
                    "" if record.output_tokens is None else record.output_tokens,
                    "" if record.total_tokens is None else record.total_tokens,
                    f"{record.latency_seconds:.2f}",
                ]
            )


def _optional_int(value: object) -> int | None:
    return None if value in (None, "") else int(value)


def _record_from_payload(payload: object) -> QaRecord | None:
    if not isinstance(payload, dict):
        return None
    try:
        return QaRecord(
            timestamp_utc=str(payload["timestamp_utc"]),
            index_folder=str(payload.get("index_folder", "")),
            index_run=str(payload.get("index_run", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            llm_model=str(payload.get("llm_model", "")),
            tone=str(payload.get("tone", "")),
            top_k=int(payload.get("top_k", 0)),
            question=str(payload.get("question", "")),
            prompt=str(payload["prompt"]),
            input_tokens=_optional_int(payload.get("input_tokens")),
            output_tokens=_optional_int(payload.get("output_tokens")),
            total_tokens=_optional_int(payload.get("total_tokens")),
            latency_seconds=float(payload.get("latency_seconds", 0.0)),
        )
    except (KeyError, TypeError, ValueError):
        return None
