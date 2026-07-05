"""Pure option/summary helpers for the Simple RAG Q&A page (Step 4).

Kept separate from the Streamlit rendering so they are unit-testable without a
running app, mirroring the split in ``llm_form_ui`` and ``vector_form_ui``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crawl4md_streamlit.qa_history import QaRecord
from crawl4md_streamlit.settings import get_settings

__all__ = [
    "TokenTotals",
    "token_totals",
    "tone_choices",
]

_settings = get_settings()
_TONE_ORDER = tuple(tone.strip() for tone in _settings.rag_qa_tones.split(",") if tone.strip())
_DEFAULT_TONE = _settings.rag_qa_default_tone


def tone_choices() -> tuple[list[str], int]:
    """Return the offered tones and the default-selected index (.env-configured)."""
    tones = list(_TONE_ORDER) or [_DEFAULT_TONE]
    default_index = tones.index(_DEFAULT_TONE) if _DEFAULT_TONE in tones else 0
    return tones, default_index


@dataclass(frozen=True)
class TokenTotals:
    """Session-wide input/output/total token counts across QA history."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


def token_totals(records: Sequence[QaRecord]) -> TokenTotals:
    """Sum token usage across *records*, treating missing counts as zero."""
    return TokenTotals(
        input_tokens=sum(record.input_tokens or 0 for record in records),
        output_tokens=sum(record.output_tokens or 0 for record in records),
        total_tokens=sum(record.total_tokens or 0 for record in records),
    )
