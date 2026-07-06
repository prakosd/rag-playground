from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.prompts import RAG_PROMPT_TEMPLATE

from crawl4md_streamlit import qa_form_ui
from crawl4md_streamlit.qa_form_ui import (
    TokenTotals,
    apply_maximized_prompt,
    resolve_qa_prompt_template,
    token_totals,
    tone_choices,
    usage_percent,
)
from crawl4md_streamlit.qa_history import QaRecord


def test_tone_choices_defaults_to_neutral() -> None:
    tones, index = tone_choices()

    assert "Neutral" in tones
    assert tones[index] == "Neutral"


def test_shipped_prompt_template_file_matches_builtin_default() -> None:
    # The committed template file must reproduce the built-in default so the
    # deployed prompt is unchanged until an operator edits the file.
    assert resolve_qa_prompt_template() == RAG_PROMPT_TEMPLATE


def test_resolve_prompt_template_returns_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = "Custom {question} {start}{knowledge}{end} {tone}"
    (tmp_path / "custom.txt").write_text(custom, encoding="utf-8")
    monkeypatch.setattr(qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(qa_form_ui._settings, "rag_qa_prompt_template_file", "custom.txt")

    assert resolve_qa_prompt_template() == custom


def test_resolve_prompt_template_falls_back_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(qa_form_ui._settings, "rag_qa_prompt_template_file", "nope.txt")

    assert resolve_qa_prompt_template() == RAG_PROMPT_TEMPLATE


def test_resolve_prompt_template_falls_back_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty.txt").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(qa_form_ui._settings, "rag_qa_prompt_template_file", "empty.txt")

    assert resolve_qa_prompt_template() == RAG_PROMPT_TEMPLATE


def test_apply_maximized_prompt_copies_source_to_target() -> None:
    state: dict[str, object] = {"src": "edited prompt"}

    apply_maximized_prompt(state, source_key="src", target_key="dst")

    assert state["dst"] == "edited prompt"
    assert state["src"] == "edited prompt"  # the source is left intact


def test_apply_maximized_prompt_is_noop_when_source_missing() -> None:
    state: dict[str, object] = {"dst": "keep"}

    apply_maximized_prompt(state, source_key="src", target_key="dst")

    assert state == {"dst": "keep"}


def _record(**tokens: object) -> QaRecord:
    return QaRecord(
        timestamp_utc="t",
        index_folder="f",
        index_run="r",
        embedding_model="e",
        llm_model="echo",
        tone="Neutral",
        top_k=5,
        question="q",
        prompt="p",
        **tokens,  # type: ignore[arg-type]
    )


def test_token_totals_sums_and_treats_missing_as_zero() -> None:
    records = [
        _record(input_tokens=10, output_tokens=5, total_tokens=15),
        _record(input_tokens=None, output_tokens=None, total_tokens=None),
        _record(input_tokens=3, output_tokens=2, total_tokens=5),
    ]

    totals = token_totals(records)

    assert totals == TokenTotals(input_tokens=13, output_tokens=7, total_tokens=20)


def test_token_totals_empty() -> None:
    assert token_totals([]) == TokenTotals(0, 0, 0)


def test_usage_percent_floors_to_whole_percent() -> None:
    assert usage_percent(1234, 100000) == 1  # 1.234% floored
    assert usage_percent(4999, 100000) == 4  # 4.999% floored


def test_usage_percent_zero_or_negative_quota_is_zero() -> None:
    assert usage_percent(500, 0) == 0
    assert usage_percent(500, -10) == 0


def test_usage_percent_at_and_over_budget() -> None:
    assert usage_percent(100000, 100000) == 100
    assert usage_percent(150000, 100000) == 150
