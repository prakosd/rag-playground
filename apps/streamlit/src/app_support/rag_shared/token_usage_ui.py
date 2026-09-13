"""Shared Token usage panel for the RAG pages (Steps 4-5).

Renders the collapsible token panel — five budget metrics (Input/Output/Total/
Quota/Usage) over a nested Transaction history table — from data each page builds
from its own records. Display-only: the quotas never block a request. Page-specific
extras (e.g. a Pricing button) are injected via ``extra_txn_controls``.
"""

from __future__ import annotations

import csv
import html
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import streamlit as st

from app_support.i18n._types import Strings
from app_support.model_pricing import pricing_captured, pricing_sources

__all__ = ["TokenPanelData", "format_cost", "render_token_usage_panel"]

_COST_DECIMALS = 4
_COST_UNDER_MIN = 5e-5
# Keep each of the five metric values on one line so a six-figure count never wraps
# beside its icon. A hidden marker scopes the rule to this panel; its own element is
# hidden so it adds no vertical gap.
_TOKEN_PANEL_SCOPE_CLASS = "rag-token-panel"
_TOKEN_PANEL_CSS = f"""
<div class="{_TOKEN_PANEL_SCOPE_CLASS}" style="display:none"></div>
<style>
div[data-testid="stElementContainer"]:has(.{_TOKEN_PANEL_SCOPE_CLASS}) {{
    display: none;
}}
div[data-testid="stExpander"]:has(.{_TOKEN_PANEL_SCOPE_CLASS})
    div[data-testid="stMetricValue"] {{
    font-size: 1.4rem;
    white-space: nowrap;
}}
</style>
"""


@dataclass(frozen=True)
class TokenPanelData:
    """Everything the token panel needs, built by each page from its own records."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float | None
    output_cost: float | None
    total_cost: float | None
    token_quota: int
    cost_quota: float
    # Localized-key dicts for the Transaction history dataframe, newest first.
    rows: Sequence[dict[str, object]]
    csv_filename: str


def format_cost(strings: Strings, cost: float | None) -> str:
    """Render a USD cost estimate, the n/a dash, or a below-minimum hint."""
    if cost is None:
        return strings["BASIC_QA_TOKEN_NA"]
    if 0 < cost < _COST_UNDER_MIN:
        return strings["BASIC_QA_COST_UNDER_MIN"]
    return f"${cost:,.{_COST_DECIMALS}f}"


def _cost_delta(strings: Strings, cost: float | None) -> str | None:
    return None if cost is None else format_cost(strings, cost)


def _usage_percent(total: int, quota: int) -> float:
    return (total / quota * 100) if quota > 0 else 0.0


def _cost_usage_percent(cost: float | None, quota: float) -> float | None:
    return (cost / quota * 100) if (cost is not None and quota > 0) else None


def render_token_usage_panel(
    strings: Strings,
    data: TokenPanelData,
    *,
    extra_txn_controls: Callable[[], None] | None = None,
) -> None:
    """Render the collapsible Token usage panel from prepared *data*.

    Five equal metrics, each a token count on top and its USD figure below (a
    neutral delta): Input / Output / Total, then the static Quota (token / cost
    budget) and Usage (tokens ÷ token quota; cost ÷ cost quota). A nested
    Transaction history table breaks it down per request/process. Display-only:
    neither quota blocks a send.
    """
    percent = _usage_percent(data.total_tokens, data.token_quota)
    cost_percent = _cost_usage_percent(data.total_cost, data.cost_quota)
    with st.expander(strings["BASIC_QA_TOKEN_PANEL_TITLE"], expanded=False):
        st.markdown(_TOKEN_PANEL_CSS, unsafe_allow_html=True)
        input_col, output_col, total_col, quota_col, usage_col = st.columns(5)
        input_col.metric(
            strings["BASIC_QA_SUMMARY_INPUT_LABEL"],
            f"{data.input_tokens:,}",
            delta=_cost_delta(strings, data.input_cost),
            delta_color="off",
            icon=":material/login:",
        )
        output_col.metric(
            strings["BASIC_QA_SUMMARY_OUTPUT_LABEL"],
            f"{data.output_tokens:,}",
            delta=_cost_delta(strings, data.output_cost),
            delta_color="off",
            icon=":material/logout:",
        )
        total_col.metric(
            strings["BASIC_QA_SUMMARY_TOTAL_LABEL"],
            f"{data.total_tokens:,}",
            delta=_cost_delta(strings, data.total_cost),
            delta_color="off",
            icon=":material/functions:",
        )
        quota_col.metric(
            strings["BASIC_QA_SUMMARY_QUOTA_LABEL"],
            f"{data.token_quota:,}",
            delta=f"${data.cost_quota:,.2f}",
            delta_color="off",
            icon=":material/data_usage:",
        )
        usage_col.metric(
            strings["BASIC_QA_SUMMARY_USAGE_LABEL"],
            f"{percent:.2f}%",
            delta=None if cost_percent is None else f"{cost_percent:.2f}%",
            delta_color="off",
            icon=":material/percent:",
        )
        _render_transaction_history(strings, data, extra_txn_controls)


def _render_transaction_history(
    strings: Strings,
    data: TokenPanelData,
    extra_txn_controls: Callable[[], None] | None,
) -> None:
    """Render the nested per-request/process token log inside the panel."""
    with st.expander(strings["BASIC_QA_TXN_PANEL_TITLE"], expanded=False):
        rows = list(data.rows)
        if not rows:
            st.caption(strings["BASIC_QA_TXN_EMPTY"])
            return
        left_col, csv_col = st.columns(2, vertical_alignment="center")
        with left_col:
            if extra_txn_controls is not None:
                extra_txn_controls()
        with csv_col, st.container(horizontal_alignment="right"):
            st.download_button(
                strings["BASIC_QA_TXN_CSV_LABEL"],
                data=_transaction_csv(rows),
                file_name=data.csv_filename,
                mime="text/csv",
                icon=":material/download:",
                help=strings["BASIC_QA_TXN_CSV_HELP"],
            )
        st.dataframe(rows, hide_index=True, width="stretch", lazy=True)
        _render_cost_disclaimer(strings)


def _transaction_csv(rows: Sequence[dict[str, object]]) -> str:
    """Serialize the Transaction history rows to CSV text (localized headers)."""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _render_cost_disclaimer(strings: Strings) -> None:
    """Caption noting costs are estimates, citing the price sources."""
    captured = pricing_captured()
    sources = pricing_sources()
    if not captured and not sources:
        return
    links = ", ".join(
        f'<a href="{html.escape(source.url)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(source.name)}</a>'
        for source in sources
    )
    text = strings["BASIC_QA_COST_DISCLAIMER"].format(
        date=captured or strings["BASIC_QA_TOKEN_NA"],
        sources=links or strings["BASIC_QA_TOKEN_NA"],
    )
    st.markdown(
        f"<div style='margin-top:-0.75rem;margin-bottom:0.5rem;opacity:0.6;"
        f"font-size:0.875rem'>{text}</div>",
        unsafe_allow_html=True,
    )
