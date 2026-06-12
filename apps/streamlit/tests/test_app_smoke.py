from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest
from vector_indexer import DEFAULT_LOCAL_MODEL, EMBEDDING_MODEL_OPTIONS

from crawl4md_streamlit.pages import APP_PAGE_SPECS, DEFAULT_PAGE_ID
from crawl4md_streamlit.support import (
    CrawlJob,
    JobSnapshot,
    SessionRecord,
    normalize_session_records,
    serialize_session_records,
)

_STREAMLIT_APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
_CONVERSATIONAL_PAGE_PATH = "app_pages/conversational_rag.py"
_EVENT_PAGE_PROCESSED = "page_processed"


def _page_path_from_module(module_name: str) -> str:
    return f"{module_name.replace('.', '/')}.py"


def _running_fake_job(session_id: str, output_base: Path) -> tuple[CrawlJob, Event, Thread]:
    gate = Event()
    thread = Thread(target=gate.wait)
    thread.daemon = True
    thread.start()
    job = CrawlJob(
        session_id=session_id,
        crawl_id="cr_toast",
        output_base=output_base,
        events=Queue(),
        cancel_event=Event(),
        thread=thread,
    )
    return job, gate, thread


def _queue_progress_event(
    job: CrawlJob,
    *,
    output_base: Path,
    successful: int,
    failed: int,
    discovered: int,
) -> None:
    job.events.put(
        {
            "event": _EVENT_PAGE_PROCESSED,
            "output_dir": str(output_base),
            "successful_pages": successful,
            "failed_pages": failed,
            "queued_discovered_urls": discovered,
            "processed_pages": successful + failed,
            "limit": 10,
        }
    )


def _storage_component_factory(
    *_component_args: object,
    initial_records: list[dict[str, str]] | None = None,
    freeze_records: bool = False,
    acknowledge_stored_records: bool = True,
    initial_portfolio_modal_last_shown_at: str | None = None,
    initial_portfolio_modal_last_dismissed_at: str | None = None,
    **_component_options: object,
):
    """Mock component factory. freeze_records=True simulates stale component state where
    'records' stays frozen at the hydration-time value after a new session is created."""
    browser_records: list[dict[str, str]] = list(initial_records or [])
    hydration_snapshot: list[dict[str, str]] = list(browser_records)

    def render(*, data: dict[str, object], **_kwargs: object) -> SimpleNamespace:
        nonlocal browser_records
        pending_records = data.get("pendingRecords", [])
        if not isinstance(pending_records, list):
            pending_records = []

        stored_records = None
        if pending_records:
            browser_records = serialize_session_records(
                normalize_session_records([*browser_records, *pending_records])
            )
            if acknowledge_stored_records:
                stored_records = browser_records

        return SimpleNamespace(
            hydrated=True,
            records=hydration_snapshot if freeze_records else browser_records,
            stored_records=stored_records,
            storage_write_failed=False,
            portfolio_modal_last_shown_at=initial_portfolio_modal_last_shown_at,
            portfolio_modal_last_dismissed_at=initial_portfolio_modal_last_dismissed_at,
        )

    return render


# Risk: the app can fail during import/bootstrap even when unit helpers pass. Type: smoke.
def test_streamlit_app_starts_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _storage_component_factory):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception


# Risk: registry entries can point at pages that fail only after navigation.
# Type: workflow smoke.
def test_streamlit_app_switches_through_registered_workflow_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _storage_component_factory):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        assert not app.exception

        for page_spec in APP_PAGE_SPECS:
            if page_spec.page_id == DEFAULT_PAGE_ID:
                continue
            app.switch_page(_page_path_from_module(page_spec.module_name))
            app.run(timeout=10)
            assert not app.exception


# Risk: browser-storage hydration must preserve portfolio modal timestamps separately from
# session records so the prompt does not reappear too often. Type: integration regression.
def test_session_storage_hydrates_portfolio_modal_timestamps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "modal_ts"
    last_shown_at = "2026-05-20T12:00:00Z"
    last_dismissed_at = "2026-05-20T12:01:00Z"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))]
    )
    (tmp_path / "outputs" / "streamlit_sessions" / f"session_{session_id}").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(
            _storage_component_factory,
            initial_records=initial_records,
            initial_portfolio_modal_last_shown_at=last_shown_at,
            initial_portfolio_modal_last_dismissed_at=last_dismissed_at,
        ),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
    assert app.session_state["portfolio_modal_last_shown_at"] == last_shown_at
    assert app.session_state["portfolio_modal_last_dismissed_at"] == last_dismissed_at


# Risk: long single-line preview content can become unreadable if wrapping or horizontal scrolling regresses. Type: UI-flow smoke.
def test_streamlit_preview_keeps_long_lines_unwrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "preview"
    session_root = tmp_path / "outputs" / "streamlit_sessions" / f"session_{session_id}"
    session_root.mkdir(parents=True)
    preview_name = "long_line.txt"
    long_line = "A" * 400
    (session_root / preview_name).write_text(long_line, encoding="utf-8")
    initial_records = serialize_session_records(
        [
            SessionRecord(
                session_id,
                datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
                "EN",
            )
        ]
    )

    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(_storage_component_factory, initial_records=initial_records),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        app.session_state.preview_file_relative_path = preview_name
        app.run(timeout=10)

    assert not app.exception
    assert any(code.value == long_line and code.wrap_lines is False for code in app.code)


# Risk: moving source inputs outside the inner form can break Step 2 submission or model
# rerender behavior even when the page still loads. Type: workflow smoke.
def test_vector_index_page_model_change_and_no_input_start_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from crawl4md_streamlit.i18n import get_strings

    selected_model = next(
        model for model in EMBEDDING_MODEL_OPTIONS if model != DEFAULT_LOCAL_MODEL
    )
    strings = get_strings("EN")

    def render() -> None:
        from importlib import import_module

        streamlit_module = import_module("streamlit")
        i18n_module = import_module("crawl4md_streamlit.i18n")
        vector_form_module = import_module("crawl4md_streamlit.vector_form_ui")

        strings = i18n_module.get_strings("EN")
        values = vector_form_module.render_vector_index_form(
            fields_disabled=False,
            state="idle",
            job_alive=False,
            strings=strings,
            crawl_result_files=[],
        )
        streamlit_module.session_state["vector_form_values"] = values
        if values["submitted"] and not vector_form_module.has_index_inputs(
            values["selected_paths"], len(values["uploaded_files"])
        ):
            streamlit_module.warning(strings["VEC_ERROR_NO_INPUTS"])

    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(render)
    app.run(timeout=10)

    next(
        selectbox for selectbox in app.selectbox if selectbox.key == "vector_index_embedding_model"
    ).set_value(selected_model)
    app.run(timeout=10)

    next(button for button in app.button if button.key == "vector_start").click()
    app.run(timeout=10)

    assert not app.exception
    assert app.session_state["vector_index_embedding_model"] == selected_model
    assert app.session_state["vector_form_values"]["submitted"] is True
    assert app.session_state["vector_form_values"]["embedding_model"] == selected_model
    assert app.session_state["vector_form_values"]["selected_paths"] == []
    assert len(app.warning) == 1
    assert [warning.value for warning in app.warning] == [strings["VEC_ERROR_NO_INPUTS"]]


# Risk: stale component 'records' with empty pending overwrites browser_session_records,
# causing session_id to revert to old session when Start is clicked. Type: critical flow regression.
def test_new_session_not_reverted_when_component_records_are_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_session_id = "old_abc"
    initial_records = serialize_session_records(
        [SessionRecord(old_session_id, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    )
    (tmp_path / "outputs" / "streamlit_sessions" / f"session_{old_session_id}").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(_storage_component_factory, initial_records=initial_records, freeze_records=True),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        assert not app.exception
        assert app.session_state.session_id == old_session_id

        # Simulate what _create_new_session() sets in state (without clicking the real button,
        # which also triggers st.rerun and a pending-confirmation round that clears pending).
        new_session_id = "new_xyz"
        new_record = SessionRecord(
            new_session_id, datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        )
        existing_records = getattr(app.session_state, "browser_session_records", [])
        app.session_state.browser_session_records = normalize_session_records(
            serialize_session_records([new_record, *existing_records])
        )
        app.session_state.session_id = new_session_id
        app.session_state.preferred_session_id = new_session_id
        app.session_state.pending_browser_session_records = []

        # Next run: component returns stale records=[old_abc], pending=[]. Without the fix
        # browser_session_records is overwritten to [old_abc] and session_id reverts.
        app.run(timeout=10)
        assert not app.exception
        assert app.session_state.session_id == new_session_id, (
            f"session_id reverted to old session: got {app.session_state.session_id!r}"
        )


# Risk: a missed stored_records callback can leave bootstrap pending forever even after
# localStorage already contains the new session. Type: critical flow regression.
def test_pending_session_clears_when_component_records_already_include_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "pending_ack"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 5, 30, tzinfo=timezone.utc))]
    )
    (tmp_path / "outputs" / "streamlit_sessions" / f"session_{session_id}").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(
            _storage_component_factory,
            initial_records=initial_records,
            acknowledge_stored_records=False,
        ),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        assert not app.exception

        app.session_state.pending_browser_session_records = initial_records
        app.session_state.pending_bootstrap_session_id = session_id
        app.session_state.session_storage_write_failed = False
        app.run(timeout=10)

    assert not app.exception
    assert app.session_state.pending_browser_session_records == []
    assert app.session_state.pending_bootstrap_session_id == ""
    assert app.session_state.session_storage_write_failed is False


# Risk: browser refresh causes a fresh st.session_state (job=None) even if the crawl
# thread is still alive — the registry must be consulted to reattach. Type: critical flow.
def test_refresh_reattaches_running_crawl_from_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "sess_reattach"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 6, 1, tzinfo=timezone.utc))]
    )

    # output_base must be inside the app's sessions root so ensure_within_root passes.
    sessions_root = tmp_path / "outputs" / "streamlit_sessions"
    output_base = sessions_root / f"session_{session_id}" / "crawl_1_reattach"
    gate = Event()
    t = Thread(target=gate.wait)
    t.daemon = True
    t.start()
    fake_job = CrawlJob(
        session_id=session_id,
        crawl_id="cr_reattach",
        output_base=output_base,
        events=Queue(),
        cancel_event=Event(),
        thread=t,
    )
    snapshot = JobSnapshot(
        job=fake_job,
        crawl_id=fake_job.crawl_id,
        started_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        activity_log_size=50,
        job_state="running",
        latest_event={"successful_pages": 3, "failed_pages": 0, "queued_discovered_urls": 5},
        active_output_dir=str(output_base),
    )
    fake_registry = {session_id: snapshot}
    (sessions_root / f"session_{session_id}").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    try:
        with (
            patch(
                "streamlit.components.v2.component",
                partial(_storage_component_factory, initial_records=initial_records),
            ),
            patch("crawl4md_streamlit.crawl_jobs._JOB_REGISTRY", fake_registry),
        ):
            app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
            app.run(timeout=10)

        assert not app.exception
        assert app.session_state.session_id == session_id
        assert app.session_state.job is fake_job
        assert app.session_state.job_state == "running"
        assert app.session_state.crawl_id == "cr_reattach"
        assert app.session_state.prev_successful_pages == 3
    finally:
        gate.set()
        t.join(timeout=2)


# Risk: crawl progress notifications are missed when a user leaves the crawl page.
# Type: critical flow regression.
def test_crawl_progress_toasts_emit_from_shell_on_other_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "toast_cross_page"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 6, 3, tzinfo=timezone.utc))]
    )
    sessions_root = tmp_path / "outputs" / "streamlit_sessions"
    output_base = sessions_root / f"session_{session_id}" / "crawl_1_toast"
    (sessions_root / f"session_{session_id}").mkdir(parents=True)
    fake_job, gate, thread = _running_fake_job(session_id, output_base)
    _queue_progress_event(
        fake_job,
        output_base=output_base,
        successful=2,
        failed=1,
        discovered=4,
    )
    toast_calls: list[tuple[object, str | None]] = []

    def capture_toast(body: object, *, icon: str | None = None, **_: object) -> None:
        toast_calls.append((body, icon))

    monkeypatch.chdir(tmp_path)
    try:
        with patch(
            "streamlit.components.v2.component",
            partial(_storage_component_factory, initial_records=initial_records),
        ):
            app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
            app.run(timeout=10)
            app.switch_page(_CONVERSATIONAL_PAGE_PATH)
            app.run(timeout=10)
            app.session_state.job = fake_job
            app.session_state.job_state = "running"
            app.session_state.started_at = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
            app.session_state.latest_event = {}
            app.session_state.prev_successful_pages = 0
            app.session_state.prev_failed_pages = 0
            app.session_state.prev_discovered_pages = 0

            with patch("streamlit.toast", capture_toast):
                app.run(timeout=10)

        assert not app.exception
        assert len(toast_calls) == 3
        assert fake_job.events.empty()
        assert app.session_state.latest_event["successful_pages"] == 2
        assert app.session_state.prev_successful_pages == 2
        assert app.session_state.prev_failed_pages == 1
        assert app.session_state.prev_discovered_pages == 4
    finally:
        gate.set()
        thread.join(timeout=2)


# Risk: counters from a previous crawl can suppress early toasts for a fresh crawl.
# Type: critical flow regression.
def test_starting_new_crawl_resets_progress_toast_counters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "toast_second_crawl"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 6, 5, tzinfo=timezone.utc))]
    )
    sessions_root = tmp_path / "outputs" / "streamlit_sessions"
    output_base = sessions_root / f"session_{session_id}" / "crawl_2_toast"
    (sessions_root / f"session_{session_id}").mkdir(parents=True)
    fake_job, gate, thread = _running_fake_job(session_id, output_base)
    toast_calls: list[tuple[object, str | None]] = []

    def fake_start_crawl_job(**_: object) -> CrawlJob:
        return fake_job

    def capture_toast(body: object, *, icon: str | None = None, **_: object) -> None:
        toast_calls.append((body, icon))

    monkeypatch.chdir(tmp_path)
    try:
        with (
            patch(
                "streamlit.components.v2.component",
                partial(_storage_component_factory, initial_records=initial_records),
            ),
            patch("crawl4md_streamlit.support.start_crawl_job", fake_start_crawl_job),
        ):
            app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
            app.run(timeout=10)
            app.session_state.prev_successful_pages = 9
            app.session_state.prev_failed_pages = 2
            app.session_state.prev_discovered_pages = 12

            next(button for button in app.button if button.key == "Start").click()
            app.run(timeout=10)

            assert app.session_state.prev_successful_pages == 0
            assert app.session_state.prev_failed_pages == 0
            assert app.session_state.prev_discovered_pages == 0

            _queue_progress_event(
                fake_job,
                output_base=output_base,
                successful=1,
                failed=0,
                discovered=1,
            )
            with patch("streamlit.toast", capture_toast):
                app.run(timeout=10)

        assert not app.exception
        assert len(toast_calls) == 2
        assert app.session_state.prev_successful_pages == 1
        assert app.session_state.prev_failed_pages == 0
        assert app.session_state.prev_discovered_pages == 1
    finally:
        gate.set()
        thread.join(timeout=2)


# Risk: moving progress toasts to the shell could ignore the existing file-preview guard.
# Type: integration regression.
def test_crawl_progress_toasts_are_suppressed_during_file_preview(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "toast_preview"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 6, 4, tzinfo=timezone.utc))]
    )
    sessions_root = tmp_path / "outputs" / "streamlit_sessions"
    output_base = sessions_root / f"session_{session_id}" / "crawl_1_toast"
    (sessions_root / f"session_{session_id}").mkdir(parents=True)
    fake_job, gate, thread = _running_fake_job(session_id, output_base)
    _queue_progress_event(
        fake_job,
        output_base=output_base,
        successful=1,
        failed=0,
        discovered=3,
    )
    toast_calls: list[tuple[object, str | None]] = []

    def capture_toast(body: object, *, icon: str | None = None, **_: object) -> None:
        toast_calls.append((body, icon))

    monkeypatch.chdir(tmp_path)
    try:
        with patch(
            "streamlit.components.v2.component",
            partial(_storage_component_factory, initial_records=initial_records),
        ):
            app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
            app.run(timeout=10)
            app.switch_page(_CONVERSATIONAL_PAGE_PATH)
            app.run(timeout=10)
            app.session_state.job = fake_job
            app.session_state.job_state = "running"
            app.session_state.started_at = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
            app.session_state.latest_event = {}
            app.session_state.preview_file_relative_path = "preview.md"
            app.session_state.prev_successful_pages = 0
            app.session_state.prev_failed_pages = 0
            app.session_state.prev_discovered_pages = 0

            with patch("streamlit.toast", capture_toast):
                app.run(timeout=10)

        assert not app.exception
        assert toast_calls == []
        assert fake_job.events.empty()
        assert app.session_state.prev_successful_pages == 1
        assert app.session_state.prev_failed_pages == 0
        assert app.session_state.prev_discovered_pages == 3
    finally:
        gate.set()
        thread.join(timeout=2)


# Risk: progress chart rendering can crash when cumulative history is present.
# Type: integration smoke.
def test_progress_chart_renders_with_cumulative_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "chart_schema"
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 6, 2, tzinfo=timezone.utc))]
    )
    (tmp_path / "outputs" / "streamlit_sessions" / f"session_{session_id}").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(_storage_component_factory, initial_records=initial_records),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        app.session_state.progress_chart_history = [
            {
                "elapsed_seconds": 0.0,
                "page_limit": 10,
                "discovered_pages": 0,
                "successful_pages": 0,
                "failed_pages": 0,
                "processed_pages": 0,
            },
            {
                "elapsed_seconds": 4.0,
                "page_limit": 10,
                "discovered_pages": 4,
                "successful_pages": 3,
                "failed_pages": 1,
                "processed_pages": 4,
            },
        ]
        app.session_state.job_state = "running"
        app.run(timeout=10)

    assert not app.exception
    assert len(app.get("vega_lite_chart")) == 1
