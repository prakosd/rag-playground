from __future__ import annotations

from pathlib import Path

from crawl4md_streamlit.qa_history import (
    QA_HISTORY_DIRNAME,
    QaRecord,
    append_qa_record,
    load_qa_history,
)


def _record(**overrides: object) -> QaRecord:
    base: dict[str, object] = {
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
        "index_folder": "vector_1",
        "index_run": "2026-07-04_10-00-00",
        "embedding_model": "titan",
        "llm_model": "echo",
        "tone": "Neutral",
        "top_k": 5,
        "question": "What is X?",
        "prompt": "You are a retrieval-augmented AI assistant. …",
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 1.23,
    }
    base.update(overrides)
    return QaRecord(**base)  # type: ignore[arg-type]


def test_append_and_load_round_trip_newest_first(tmp_path: Path) -> None:
    append_qa_record(tmp_path, _record(question="first"))
    append_qa_record(tmp_path, _record(question="second"))

    records = load_qa_history(tmp_path)

    assert [record.question for record in records] == ["second", "first"]
    assert (tmp_path / QA_HISTORY_DIRNAME / "qa_history.csv").is_file()


def test_optional_tokens_round_trip_as_none(tmp_path: Path) -> None:
    append_qa_record(tmp_path, _record(input_tokens=None, output_tokens=None, total_tokens=None))

    record = load_qa_history(tmp_path)[0]

    assert record.input_tokens is None
    assert record.total_tokens is None
    assert record.latency_seconds == 1.23


def test_load_skips_malformed_lines(tmp_path: Path) -> None:
    directory = tmp_path / QA_HISTORY_DIRNAME
    directory.mkdir(parents=True)
    (directory / "qa_history.jsonl").write_text("not json\n", encoding="utf-8")

    assert load_qa_history(tmp_path) == []


def test_load_empty_when_no_history(tmp_path: Path) -> None:
    assert load_qa_history(tmp_path) == []
