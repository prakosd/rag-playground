"""Pure option/summary helpers for the Simple RAG Q&A page (Step 4).

Kept separate from the Streamlit rendering so they are unit-testable without a
running app, mirroring the split in ``llm_form_ui`` and ``vector_form_ui``.
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from log4py import get_logger
from rag_engine.prompts import RAG_PROMPT_TEMPLATE

from crawl4md_streamlit.qa_history import QaRecord
from crawl4md_streamlit.settings import get_settings

__all__ = [
    "TokenTotals",
    "apply_maximized_prompt",
    "resolve_qa_prompt_template",
    "token_totals",
    "tone_choices",
    "usage_percent",
]

_logger = get_logger(__name__)
_settings = get_settings()
_TONE_ORDER = tuple(tone.strip() for tone in _settings.rag_qa_tones.split(",") if tone.strip())
_DEFAULT_TONE = _settings.rag_qa_default_tone
# qa_form_ui.py lives at apps/streamlit/src/crawl4md_streamlit/; the repo root is
# four parents up (mirrors settings.py) and the template path resolves against it.
_REPO_ROOT = Path(__file__).resolve().parents[4]


def resolve_qa_prompt_template() -> str:
    """Return the Step 4 prompt template from the configured file.

    Reads the file named by ``RAG_QA_PROMPT_TEMPLATE_FILE`` (resolved against the
    repo root) so an operator can reword the generated prompt without a code
    change. Falls back to the built-in ``RAG_PROMPT_TEMPLATE`` when the file is
    missing, empty, or unreadable, so a bad path never breaks generation.
    """
    path = _REPO_ROOT / _settings.rag_qa_prompt_template_file
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _logger.warning(
            "RAG Q&A prompt template file not found at %s; using the built-in default.", path
        )
        return RAG_PROMPT_TEMPLATE
    if not text.strip():
        _logger.warning(
            "RAG Q&A prompt template file %s is empty; using the built-in default.", path
        )
        return RAG_PROMPT_TEMPLATE
    return text


def apply_maximized_prompt(
    state: MutableMapping[str, Any], *, source_key: str, target_key: str
) -> None:
    """Copy the prompt text from *source_key* to *target_key* in *state*.

    Keeps the inline editor and the maximized dialog in sync: the dialog is seeded
    from the inline value when opened and written back when closed. A no-op when
    *source_key* is absent, so a first open or an empty dialog never errors.
    """
    if source_key in state:
        state[target_key] = state[source_key]


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


def usage_percent(total: int, quota: int) -> int:
    """Return session token usage as a whole-number percent of *quota* (floored).

    Rounds down to whole percent for a stable, non-alarming readout and returns 0
    when *quota* is not positive, so a misconfigured budget never divides by zero.
    May exceed 100 when the session total is over budget.
    """
    if quota <= 0:
        return 0
    return total * 100 // quota
