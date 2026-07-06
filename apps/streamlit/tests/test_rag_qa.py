"""Tests for the Simple RAG Q&A page's pure helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

from pytest import MonkeyPatch
from rag_engine.models import TokenUsage

from crawl4md_streamlit.i18n import STRINGS_EN
from crawl4md_streamlit.qa_history import QaRecord

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.rag_qa")


def _record(**overrides: object) -> QaRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-04_09-00-00",
        "embedding_model": "titan",
        "llm_model": "apac.amazon.nova-lite-v1:0",
        "tone": "Neutral",
        "top_k": 5,
        "question": "What is X?",
        "prompt": "You are ...",
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "latency_seconds": 2.34,
    }
    values.update(overrides)
    return QaRecord(**values)  # type: ignore[arg-type]


def test_stats_caption_shows_counts_and_seconds(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._stats_caption(STRINGS_EN, TokenUsage(120, 45, 165), 2.34, "Nova Lite")

    assert "Nova Lite" in caption
    assert "120" in caption
    assert "45" in caption
    assert "165" in caption
    assert "2.3s" in caption


def test_stats_caption_shows_na_without_usage(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._stats_caption(STRINGS_EN, None, 1.0, "Echo")

    assert "Echo" in caption
    assert STRINGS_EN["QA_TOKEN_NA"] in caption
    assert "1.0s" in caption


def test_tokens_value_uses_na_for_missing_counts(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    value = page._tokens_value(
        STRINGS_EN, _record(input_tokens=None, output_tokens=None, total_tokens=None)
    )

    assert STRINGS_EN["QA_TOKEN_NA"] in value


def test_history_grid_includes_model_tone_and_tokens(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._history_grid(STRINGS_EN, _record())

    assert "apac.amazon.nova-lite-v1:0" in grid
    assert "Neutral" in grid
    assert "vector_01_weather / 2026-07-04_09-00-00" in grid
    assert "120 in" in grid
