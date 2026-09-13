"""Step 5 Token usage panel: per-process token totals + a transaction breakdown.

Builds the shared :class:`TokenPanelData` from the conversation's per-turn stage
usage (each turn records the tokens its decomposition / re-ranking / answer /
follow-ups / answerability / state LLM calls reported) and renders it with the
shared panel, one transaction row per process. Repeated same-(process, model)
calls in a turn (e.g. the per-sub-question answerability probe) are merged into a
single row with an N× marker. Pure aggregation over records plus a Streamlit
render, so the page module stays thin.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple

from app_support.conversational_rag.conversational_rag_history import (
    ConversationalStageUsage,
    ConversationalTurnRecord,
)
from app_support.i18n._types import Strings
from app_support.model_pricing import estimate_cost, get_model_price
from app_support.rag_shared.rag_ui import local_time_label
from app_support.rag_shared.token_usage_ui import (
    TokenPanelData,
    format_cost,
    render_token_usage_panel,
)
from app_support.settings import get_settings

__all__ = ["conversational_token_panel_data", "render_conversational_token_panel"]

_TXN_CSV_FILENAME = "conversational_rag_transactions.csv"
# Stage process key -> its i18n display-name key.
_PROCESS_LABEL_KEYS = {
    "decomposition": "CONV_PROCESS_DECOMPOSITION",
    "reranking": "CONV_PROCESS_RERANKING",
    "answer": "CONV_PROCESS_ANSWER",
    "followups": "CONV_PROCESS_FOLLOWUPS",
    "answerability": "CONV_PROCESS_ANSWERABILITY",
    "state": "CONV_PROCESS_STATE",
}


class _MergedStage(NamedTuple):
    """A turn's stages for one (process, model), collapsed into a single row."""

    process: str
    model: str
    count: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


def _sum_opt(values: Iterable[int | None]) -> int | None:
    """Sum the reported token counts; None only when every value was unreported."""
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _merge_record_stages(record: ConversationalTurnRecord) -> list[_MergedStage]:
    """Collapse a turn's stages sharing a (process, model) into one entry each.

    The answerability probe runs once per sub-question, so a turn can report
    several identical (process, model) stages; merging keeps the transaction
    table one row per logical process. Entries stay in first-seen order and their
    token fields are summed (None only when every merged stage was echo/unpriced).
    """
    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[ConversationalStageUsage]] = {}
    for stage in record.token_usage:
        key = (stage.process, stage.model)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(stage)
    merged: list[_MergedStage] = []
    for process, model in order:
        stages = groups[(process, model)]
        merged.append(
            _MergedStage(
                process=process,
                model=model,
                count=len(stages),
                input_tokens=_sum_opt(stage.input_tokens for stage in stages),
                output_tokens=_sum_opt(stage.output_tokens for stage in stages),
                total_tokens=_sum_opt(stage.total_tokens for stage in stages),
            )
        )
    return merged


def _ordered_merged(
    records: Sequence[ConversationalTurnRecord],
) -> list[tuple[ConversationalTurnRecord, _MergedStage]]:
    """Return (record, merged-stage) pairs, newest turn first, one per process."""
    ordered = sorted(records, key=lambda record: record.timestamp_utc, reverse=True)
    return [(record, merged) for record in ordered for merged in _merge_record_stages(record)]


def _sum_costs(costs: Iterable[float | None]) -> float | None:
    """Sum the priced costs; None when nothing could be priced."""
    priced = [cost for cost in costs if cost is not None]
    return sum(priced) if priced else None


def _process_label(strings: Strings, process: str, count: int = 1) -> str:
    """Return the localized display name for a stage *process* (raw key fallback).

    ``count`` > 1 prefixes a repeat marker (e.g. '3× Answerability check') when
    several same-process stages of a turn were merged into one row.
    """
    key = _PROCESS_LABEL_KEYS.get(process)
    label = strings[key] if key else process
    if count > 1:
        return strings["CONV_PROCESS_MULTI"].format(count=count, process=label)
    return label


def conversational_token_panel_data(
    strings: Strings, records: Sequence[ConversationalTurnRecord]
) -> TokenPanelData:
    """Aggregate the conversation's per-process token usage into shared panel data."""
    settings = get_settings()
    pairs = _ordered_merged(records)
    na = strings["BASIC_QA_TOKEN_NA"]
    rows: list[dict[str, object]] = []
    for record, merged in pairs:
        price = get_model_price(merged.model)
        rows.append(
            {
                strings["BASIC_QA_TXN_COL_TIME"]: local_time_label(
                    record.timestamp_utc, abbreviate_month=True, with_seconds=True
                ),
                strings["CONV_TXN_COL_CONVERSATION"]: record.conversation_id or "—",
                strings["CONV_TXN_COL_TRANSACTION"]: record.transaction_id or "—",
                strings["BASIC_QA_TXN_COL_PROCESS"]: _process_label(
                    strings, merged.process, merged.count
                ),
                strings["BASIC_QA_HISTORY_META_MODEL"]: merged.model or "—",
                strings["BASIC_QA_TXN_COL_PROVIDER"]: price.provider if price else na,
                strings["BASIC_QA_TXN_COL_CLOUD"]: price.cloud_service if price else na,
                strings["BASIC_QA_SUMMARY_INPUT_LABEL"]: na
                if merged.input_tokens is None
                else merged.input_tokens,
                strings["BASIC_QA_SUMMARY_OUTPUT_LABEL"]: na
                if merged.output_tokens is None
                else merged.output_tokens,
                strings["BASIC_QA_SUMMARY_TOTAL_LABEL"]: na
                if merged.total_tokens is None
                else merged.total_tokens,
                strings["BASIC_QA_TXN_COL_COST"]: format_cost(
                    strings,
                    estimate_cost(
                        merged.model, merged.input_tokens or 0, merged.output_tokens or 0
                    ),
                ),
            }
        )
    data = TokenPanelData(
        input_tokens=sum(merged.input_tokens or 0 for _, merged in pairs),
        output_tokens=sum(merged.output_tokens or 0 for _, merged in pairs),
        total_tokens=sum(merged.total_tokens or 0 for _, merged in pairs),
        input_cost=_sum_costs(
            estimate_cost(merged.model, merged.input_tokens or 0, 0) for _, merged in pairs
        ),
        output_cost=_sum_costs(
            estimate_cost(merged.model, 0, merged.output_tokens or 0) for _, merged in pairs
        ),
        total_cost=_sum_costs(
            estimate_cost(merged.model, merged.input_tokens or 0, merged.output_tokens or 0)
            for _, merged in pairs
        ),
        token_quota=settings.conv_rag_session_token_quota,
        cost_quota=settings.conv_rag_session_cost_quota,
        rows=rows,
        csv_filename=_TXN_CSV_FILENAME,
    )
    return data


def render_conversational_token_panel(
    strings: Strings, records: Sequence[ConversationalTurnRecord]
) -> None:
    """Render the Step 5 Token usage panel aggregated over the conversation."""
    render_token_usage_panel(strings, conversational_token_panel_data(strings, records))
