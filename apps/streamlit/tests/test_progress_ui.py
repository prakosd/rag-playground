from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from app_support import progress_ui


# Risk: activity-log lines are rendered as raw HTML; unescaped markup would be an
# injection vector. Verify HTML is escaped. Type: unit.
def test_linkify_log_line_escapes_html() -> None:
    result = progress_ui._linkify_log_line("<script>alert(1)</script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


# Risk: URLs in the log should become safe new-tab links (noopener). Type: unit.
def test_linkify_log_line_wraps_urls_as_safe_links() -> None:
    result = progress_ui._linkify_log_line("see https://example.com/x for details")
    assert '<a href="https://example.com/x"' in result
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result


# Risk: every Step 1 progress metric shows a leading icon (Streamlit 1.61 icon=)
# so the cards stay scannable. Type: unit.
def test_render_progress_metrics_all_have_icons(monkeypatch: pytest.MonkeyPatch) -> None:
    class _State(dict):
        __getattr__ = dict.get  # type: ignore[assignment]

    fake_st = MagicMock()
    fake_st.session_state = _State(language="EN", started_at=None, job_state="completed")
    monkeypatch.setattr(progress_ui, "st", fake_st)

    progress_ui.render_progress_and_files(
        processed=1, successful=1, failed=0, discovered=2, limit=10, state="completed"
    )

    column_metric = fake_st.columns.return_value.__getitem__.return_value.metric
    column_icons = [call.kwargs.get("icon") for call in column_metric.call_args_list]
    assert column_icons and all(column_icons)
    # A non-running state renders through st.metric with the status emoji as icon.
    state_icons = [call.kwargs.get("icon") for call in fake_st.metric.call_args_list]
    assert state_icons and all(state_icons)


# Risk: a progress event must update the per-chunk counters that drive the bar and
# caption. Type: unit.
def test_apply_vector_index_event_progress_sets_chunk_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)

    progress_ui._apply_vector_index_event(
        {"event": "progress", "processed_chunks": 3, "total_chunks": 10}
    )

    assert state.vector_index_state == "running"
    assert state.vector_index_progress == {"processed": 3, "total": 10}


# Risk: a stage-only progress event must set the stage (for the indeterminate
# caption) without overwriting chunk counts. Type: unit.
def test_apply_vector_index_event_progress_sets_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)

    progress_ui._apply_vector_index_event({"event": "progress", "stage": "embedding"})

    assert state.vector_index_stage == "embedding"
    assert not hasattr(state, "vector_index_progress")


# Risk: a terminal event must capture the final counts into the result panel.
# Type: unit.
def test_apply_vector_index_event_terminal_builds_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)
    clear_caches = MagicMock()
    monkeypatch.setattr(progress_ui, "_clear_generated_file_caches", clear_caches)

    progress_ui._apply_vector_index_event(
        {
            "event": "completed",
            "indexed_file_count": 2,
            "indexed_chunk_count": 40,
            "skipped_file_count": 1,
            "warnings": [],
            "errors": [],
        }
    )

    assert state.vector_index_state == "completed"
    assert state.vector_index_result["state"] == "completed"
    assert state.vector_index_result["indexed_file_count"] == 2
    # The terminal transition drops the stale file-listing cache so the new
    # vector_<id> folder shows without a manual browser refresh.
    clear_caches.assert_called_once()
    assert state.vector_index_result["indexed_chunk_count"] == 40
    assert state.vector_index_result["skipped_file_count"] == 1


def _render_progress(
    *,
    state: str = "running",
    processed: int = 5,
    discovered: int = 10,
    round_num: int | None = None,
    seed_count: int = 1,
    limit: int = 20,
) -> None:
    # Self-contained render for AppTest.from_function (isolated namespace).
    from datetime import UTC, datetime

    import streamlit as st

    from app_support.progress_ui import render_progress_and_files

    st.session_state["language"] = "EN"
    st.session_state["started_at"] = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    st.session_state["job_state"] = state
    st.session_state["last_elapsed"] = "00:05"
    st.session_state["latest_event"] = {"eta_remaining_seconds": 12.0}
    render_progress_and_files(
        processed=processed,
        successful=4,
        failed=1,
        discovered=discovered,
        limit=limit,
        state=state,
        round_num=round_num,
        seed_count=seed_count,
    )


# Risk: the running-card / banner / retry branches of the progress panel are untested.
# Type: unit (AppTest).
@pytest.mark.parametrize("state", ["running", "failed", "cancel_requested", "stopped"])
def test_render_progress_and_files_renders_across_states(state: str) -> None:
    app = AppTest.from_function(_render_progress, kwargs={"state": state}).run()
    assert not app.exception
    assert len(app.metric) >= 5  # 6 metrics (the running state swaps one for an st.html card)


# Risk: the retry phase (processed > discovered) swaps the progress copy + processed delta.
# Type: unit (AppTest).
def test_render_progress_and_files_retry_phase() -> None:
    app = AppTest.from_function(
        _render_progress, kwargs={"state": "running", "processed": 15, "discovered": 10}
    ).run()
    assert not app.exception


# Risk: the Page-attempts badge must render a retry round without error. Type: unit (AppTest).
def test_render_progress_and_files_shows_retry_round() -> None:
    app = AppTest.from_function(_render_progress, kwargs={"state": "running", "round_num": 3}).run()
    assert not app.exception


# Risk: the Limit card shows a plain number for one start URL but 'N × limit' for several, so
# multi-site crawls surface the effective per-URL budget. Type: unit.
def test_limit_value_text() -> None:
    assert progress_ui._limit_value_text(1, 10) == "10"
    assert progress_ui._limit_value_text(2, 10) == "2 × 10"
    assert progress_ui._limit_value_text(3, 1000) == "3 × 1,000"


# Risk: a multi-seed crawl must render the N×limit Limit card without error. Type: unit (AppTest).
def test_render_progress_and_files_multi_seed_limit() -> None:
    app = AppTest.from_function(
        _render_progress, kwargs={"state": "running", "seed_count": 2, "limit": 10}
    ).run()
    assert not app.exception
    assert "2 × 10" in [metric.value for metric in app.metric]


# Risk: the Successful/Failed badges show the share of attempts; guard a zero-attempt
# divide and confirm the ratio. Type: unit.
@pytest.mark.parametrize(
    ("part", "total", "expected"),
    [(0, 0, 0.0), (5, 0, 0.0), (1, 4, 25.0), (801, 920, 87.065)],
)
def test_attempt_percentage(part: int, total: int, expected: float) -> None:
    assert progress_ui._attempt_percentage(part, total) == pytest.approx(expected, abs=0.01)


# Risk: the Page-attempts badge names the active round; round 1/None = initial, later
# rounds are retries numbered from 1. Type: unit.
def test_round_badge_text() -> None:
    strings = progress_ui.get_strings("EN")
    initial = strings["METRIC_PROCESSED_DELTA_ROUND_INITIAL"]
    retry = strings["METRIC_PROCESSED_DELTA_ROUND_RETRY"]
    assert progress_ui._round_badge_text(strings, None) == initial
    assert progress_ui._round_badge_text(strings, 1) == initial
    assert progress_ui._round_badge_text(strings, 2) == retry.format(n=1)
    assert progress_ui._round_badge_text(strings, 3) == retry.format(n=2)


# Risk: with a very large page limit the Limit line dominates the y-axis and flattens
# the real series, so it must stay hidden until discovery nears the cap. Type: unit.
@pytest.mark.parametrize(
    ("discovered", "page_limit", "expected"),
    [
        (80, 100, True),  # exactly at the 80% ratio
        (95, 100, True),
        (79, 100, False),  # just below the ratio
        (10, 999_999, False),  # the zoom-out case: tiny discovery vs huge limit
    ],
)
def test_should_show_limit_line_ratio(discovered: int, page_limit: int, expected: bool) -> None:
    rows = [{"discovered_pages": discovered, "page_limit": page_limit}]
    assert progress_ui._should_show_limit_line(rows) is expected


# Risk: no rows or a non-positive limit must not draw (or divide by) the limit. Type: unit.
def test_should_show_limit_line_guards_empty_and_zero_limit() -> None:
    assert progress_ui._should_show_limit_line([]) is False
    assert progress_ui._should_show_limit_line([{"discovered_pages": 5, "page_limit": 0}]) is False


def _chart_rows(discovered: int, page_limit: int) -> list[dict[str, float]]:
    return [
        {
            "elapsed_time": 1.0,
            "discovered_pages": discovered,
            "successful_pages": discovered,
            "processed_pages": discovered,
            "page_limit": page_limit,
        }
    ]


# Risk: the Limit layer must be dropped below the ratio and present at/above it, so the
# legend and y-axis match the drawn series. Type: unit.
def test_build_cumulative_progress_chart_hides_limit_below_ratio() -> None:
    strings = progress_ui.get_strings("EN")
    chart = progress_ui._build_cumulative_progress_chart(_chart_rows(10, 999_999), strings)
    assert len(chart.layer) == 3  # discovered + successful + failed, no limit


def test_build_cumulative_progress_chart_shows_limit_at_ratio() -> None:
    strings = progress_ui.get_strings("EN")
    chart = progress_ui._build_cumulative_progress_chart(_chart_rows(80, 100), strings)
    assert len(chart.layer) == 4  # the Limit line is added once discovery nears the cap


# Risk: at crawl start the only sample is all-zero at t≈0, which collapses the auto-scaled
# axes to a degenerate sliver; the axes must anchor to a sensible initial span, then
# auto-scale from 0 once data arrives. Type: unit.
def test_axis_scale_anchors_initial_span_then_autoscales() -> None:
    empty = progress_ui._axis_scale(0.0, 10.0).to_dict()
    assert empty["domain"] == [0, 10.0]
    grown = progress_ui._axis_scale(42.0, 10.0).to_dict()
    assert "domain" not in grown
    assert grown["domainMin"] == 0


def test_build_cumulative_progress_chart_initial_zero_rows_render_cleanly() -> None:
    strings = progress_ui.get_strings("EN")
    rows = [
        {
            "elapsed_time": 0.0,
            "discovered_pages": 0,
            "successful_pages": 0,
            "processed_pages": 0,
            "page_limit": 100,
        }
    ]
    chart = progress_ui._build_cumulative_progress_chart(rows, strings)
    assert len(chart.layer) == 3  # no limit line yet (discovered 0 < 80% of limit)
    y_scale = chart.layer[0].to_dict()["encoding"]["y"]["scale"]
    assert y_scale["domain"] == [0, 10.0]  # y anchored to the initial span, not 0..0


# Risk: the live panel re-reads progress history every few seconds; the cache must reuse
# the parse while the file is unchanged but refresh when it grows. Type: unit.
def test_persisted_progress_history_reuses_cache_until_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    progress_ui._cached_progress_history.clear()
    calls: list[int] = []
    real = progress_ui.load_persisted_progress_history

    def _counting(root: object) -> list[dict[str, object]]:
        calls.append(1)
        return real(root)

    monkeypatch.setattr(progress_ui, "load_persisted_progress_history", _counting)

    logs = tmp_path / "logs"
    logs.mkdir()
    history = logs / "progress_history.jsonl"
    history.write_text('{"event": "a", "round": 1, "timestamp": "t1"}\n', encoding="utf-8")

    first = progress_ui._persisted_progress_history(tmp_path)
    second = progress_ui._persisted_progress_history(tmp_path)
    assert first == second
    assert len(calls) == 1  # an unchanged file is served from cache

    history.write_text(
        '{"event": "a", "round": 1, "timestamp": "t1"}\n'
        '{"event": "b", "round": 1, "timestamp": "t2"}\n',
        encoding="utf-8",
    )
    progress_ui._persisted_progress_history(tmp_path)
    assert len(calls) == 2  # a grown file is re-read
