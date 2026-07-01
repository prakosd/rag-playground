"""Tests for the per-session semantic-search history log."""

from __future__ import annotations

import csv
from pathlib import Path

from crawl4md_streamlit.search_history import (
    SEARCH_HISTORY_DIRNAME,
    SearchRecord,
    append_search_record,
    load_search_history,
    search_history_dir,
)


def _record(query: str, **overrides: object) -> SearchRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-01T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-01_09-00-00",
        "embedding_model": "amazon.titan-embed-text-v2:0",
        "query": query,
        "search_type": "mmr",
        "top_k": 5,
        "fetch_k": 20,
        "mmr_lambda": 0.5,
        "score_threshold": 0.25,
        "source_filter": ("a.md", "b.md"),
        "result_count": 3,
        "top_score": 0.8123,
    }
    values.update(overrides)
    return SearchRecord(**values)  # type: ignore[arg-type]


def test_load_history_empty_when_missing(tmp_path: Path) -> None:
    assert load_search_history(tmp_path) == []


def test_search_history_dir_uses_search_prefix(tmp_path: Path) -> None:
    assert search_history_dir(tmp_path) == tmp_path / SEARCH_HISTORY_DIRNAME
    assert SEARCH_HISTORY_DIRNAME.startswith("search_")


def test_append_then_load_is_newest_first(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("first"))
    append_search_record(tmp_path, _record("second"))

    history = load_search_history(tmp_path)

    assert [record.query for record in history] == ["second", "first"]


def test_record_round_trips_all_fields(tmp_path: Path) -> None:
    original = _record("weather today")
    append_search_record(tmp_path, original)

    (loaded,) = load_search_history(tmp_path)

    assert loaded == original
    assert loaded.source_filter == ("a.md", "b.md")
    assert loaded.top_score == 0.8123


def test_history_is_capped_to_recent_records(tmp_path: Path) -> None:
    for index in range(230):
        append_search_record(tmp_path, _record(f"q{index}"))

    history = load_search_history(tmp_path)

    assert len(history) == 200
    # Newest-first: the most recent query is q229; the oldest kept is q30.
    assert history[0].query == "q229"
    assert history[-1].query == "q30"


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("valid"))
    history_file = search_history_dir(tmp_path) / "search_history.jsonl"
    history_file.write_text(
        history_file.read_text(encoding="utf-8") + "not json\n", encoding="utf-8"
    )

    history = load_search_history(tmp_path)

    assert [record.query for record in history] == ["valid"]


def test_csv_companion_has_header_and_rows(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("alpha"))
    append_search_record(tmp_path, _record("beta", top_score=None))

    csv_path = search_history_dir(tmp_path) / "search_history.csv"
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))

    assert [row["query"] for row in rows] == ["alpha", "beta"]
    assert rows[0]["source_filter"] == "a.md, b.md"
    assert rows[0]["top_score"] == "0.8123"
    assert rows[1]["top_score"] == ""
