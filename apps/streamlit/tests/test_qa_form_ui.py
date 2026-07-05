from __future__ import annotations

from crawl4md_streamlit.qa_form_ui import TokenTotals, token_totals, tone_choices
from crawl4md_streamlit.qa_history import QaRecord


def test_tone_choices_defaults_to_neutral() -> None:
    tones, index = tone_choices()

    assert "Neutral" in tones
    assert tones[index] == "Neutral"


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
