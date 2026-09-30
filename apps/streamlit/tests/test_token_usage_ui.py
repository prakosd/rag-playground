"""AppTest coverage for the shared Token usage panel render path (Steps 4-5).

``render_token_usage_panel`` is pure ``st.*`` rendering, so it is exercised through
Streamlit's ``AppTest.from_function`` harness rather than by calling it directly.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _render_token_panel(
    *, with_rows: bool = True, quota: int = 10_000, total_cost: float | None = 0.0015
) -> None:
    # Self-contained: AppTest runs this as a fresh script, so imports stay local.
    from app_support.i18n import get_strings
    from app_support.rag_shared.token_usage_ui import (
        TokenPanelData,
        render_token_usage_panel,
    )

    rows = [{"Process": "answer", "Input tokens": 100, "Output tokens": 50}] if with_rows else []
    data = TokenPanelData(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        input_cost=0.001,
        output_cost=0.0005,
        total_cost=total_cost,
        token_quota=quota,
        cost_quota=1.0,
        rows=rows,
        csv_filename="tokens.csv",
    )
    render_token_usage_panel(get_strings("EN"), data)


# Risk: the shared token panel render path (five metrics + transaction table) is untested.
# Type: unit (AppTest).
def test_token_panel_renders_metrics_and_transaction_table() -> None:
    app = AppTest.from_function(_render_token_panel).run()
    assert not app.exception
    assert len(app.metric) == 5  # Input / Output / Total / Quota / Usage
    assert len(app.dataframe) == 1  # the nested per-transaction table


# Risk: the empty-transaction branch (caption, no table) must render cleanly.
# Type: unit (AppTest).
def test_token_panel_renders_empty_transaction_history() -> None:
    app = AppTest.from_function(_render_token_panel, kwargs={"with_rows": False}).run()
    assert not app.exception
    assert len(app.dataframe) == 0


# Risk: a zero quota / missing cost must not divide-by-zero or crash the panel.
# Type: unit (AppTest).
def test_token_panel_handles_zero_quota_and_missing_cost() -> None:
    app = AppTest.from_function(_render_token_panel, kwargs={"quota": 0, "total_cost": None}).run()
    assert not app.exception
    assert len(app.metric) == 5
