"""Tests for the Basic RAG Q&A page's pure helpers."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path

from pytest import MonkeyPatch
from rag_engine.models import TokenUsage

from app_support.basic_rag_qa.basic_rag_qa_history import BasicQaRecord
from app_support.i18n import STRINGS_EN

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.basic_rag_qa")


def _record(**overrides: object) -> BasicQaRecord:
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
    return BasicQaRecord(**values)  # type: ignore[arg-type]


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
    assert STRINGS_EN["BASIC_QA_TOKEN_NA"] in caption
    assert "1.0s" in caption


def test_history_stats_caption_uses_record_fields(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._history_stats_caption(STRINGS_EN, _record())

    assert "Amazon Nova Lite" in caption
    assert "120" in caption
    assert "45" in caption
    assert "165" in caption
    assert "2.3s" in caption


def test_tokens_value_uses_na_for_missing_counts(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    value = page._tokens_value(
        STRINGS_EN, _record(input_tokens=None, output_tokens=None, total_tokens=None)
    )

    assert STRINGS_EN["BASIC_QA_TOKEN_NA"] in value


def test_history_grid_includes_model_tone_and_tokens(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._history_grid(STRINGS_EN, _record())

    assert "apac.amazon.nova-lite-v1:0" in grid
    assert "Neutral" in grid
    assert "vector_01_weather" in grid
    assert "2026-07-04_09-00-00" in grid
    assert "120 in" in grid
    assert STRINGS_EN["BASIC_QA_HISTORY_LABEL_TIME"] in grid


def test_apply_replay_repopulates_question_and_prompt(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {}
    monkeypatch.setattr(page.st, "session_state", state)

    page._apply_replay(
        STRINGS_EN, [], asdict(_record(question="Why sky blue?", prompt="FULL PROMPT BODY"))
    )

    assert state[page._QUESTION_KEY] == "Why sky blue?"
    assert state[page._PROMPT_KEY] == "FULL PROMPT BODY"
