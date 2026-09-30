"""Step-1 crawl background-job orchestration extracted from ``streamlit_app.py``.

Owns the crawl job lifecycle: start/stop (+ confirmation dialog), draining background
events into session state, re-attaching a running job on session switch, progress
toasts, and the auto-refresh event loop. Reads/writes ``st.session_state`` directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st
from pydantic import ValidationError

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _SESSIONS_ROOT,
    _STATE_CANCEL_REQUESTED,
    _STATE_CANCELLED,
    _STATE_RUNNING,
    _STATE_STOPPED,
    _TERMINAL_STATES,
    _auto_refresh_fragment,
    _clear_generated_file_caches,
    _crawl_job_active,
)
from app_support.auth.store import resolve_http_secret_headers
from app_support.crawl.form_defaults import form_state_from_submitted
from app_support.dialog_ui import render_confirm_dialog
from app_support.i18n import Strings, get_strings
from app_support.progress_chart import append_live_progress_sample
from app_support.settings import get_settings
from app_support.shell.constants import (
    _REFRESH_FORM_STATES,
    _TOAST_PAGE_DISCOVERED_ICON,
    _TOAST_PAGE_FAIL_ICON,
    _TOAST_PAGE_SUCCESS_ICON,
)
from app_support.support import (
    CrawlJob,
    build_configs,
    drain_events,
    generate_crawl_id,
    get_active_job_snapshot,
    job_state_from_event,
    next_crawl_sequence,
    request_cancel,
    session_dir,
    start_crawl_job,
)


def _drain_job_events(job: CrawlJob | None) -> bool:
    """Apply worker events to the Streamlit-facing crawl state."""
    if job is None:
        return False
    state_changed = False
    for event in drain_events(job):
        event_name = str(event.get("event", ""))
        st.session_state.latest_event.update(event)
        chart_history = st.session_state.get("progress_chart_history")
        if not isinstance(chart_history, list):
            chart_history = []
        st.session_state.progress_chart_history = append_live_progress_sample(
            chart_history,
            event,
            started_at=st.session_state.started_at,
        )
        output_dir = str(event.get("output_dir", ""))
        if output_dir:
            st.session_state.active_output_dir = output_dir
        next_state = job_state_from_event(event_name)
        # Keep the UI in Stop-pending state if older worker events arrive late.
        if st.session_state.job_state == _STATE_CANCEL_REQUESTED and next_state in {
            _STATE_RUNNING,
            _STATE_CANCEL_REQUESTED,
        }:
            next_state = _STATE_CANCEL_REQUESTED
        elif next_state == _STATE_CANCELLED:
            next_state = _STATE_STOPPED
        if next_state != st.session_state.job_state:
            state_changed = True
        st.session_state.job_state = next_state
        if next_state in _TERMINAL_STATES:
            started_at = st.session_state.started_at
            if started_at is not None:
                elapsed = datetime.now(timezone.utc) - started_at
                st.session_state.last_elapsed = str(elapsed).split(".")[0]
            st.session_state.started_at = None
            st.session_state.job = None
            # The final initial/ + final/ folders were just written; drop the
            # stale listing cache so this terminal rerun shows them immediately.
            _clear_generated_file_caches()
    return state_changed


def _reattach_selected_session_job() -> None:
    """Restore a running crawl job from the process-local registry after browser refresh.

    Called after session selection so that `st.session_state.session_id` is already set.
    Does nothing if a job is already attached to this Streamlit session.
    """
    if st.session_state.job is not None:
        return
    session_id = st.session_state.session_id
    if not session_id:
        return
    snapshot = get_active_job_snapshot(session_id)
    if snapshot is None:
        return
    st.session_state.job = snapshot.job
    st.session_state.crawl_id = snapshot.crawl_id
    st.session_state.job_state = snapshot.job_state
    st.session_state.started_at = snapshot.started_at
    st.session_state.activity_log_size = snapshot.activity_log_size
    st.session_state.latest_event = dict(snapshot.latest_event)
    st.session_state.active_output_dir = snapshot.active_output_dir
    # Seed page-count deltas so the first drain doesn't fire spurious toast messages.
    st.session_state.prev_successful_pages = int(snapshot.latest_event.get("successful_pages", 0))
    st.session_state.prev_failed_pages = int(snapshot.latest_event.get("failed_pages", 0))
    st.session_state.prev_discovered_pages = int(
        snapshot.latest_event.get("queued_discovered_urls", 0)
    )
    st.session_state.progress_chart_history = []
    if snapshot.latest_event:
        st.session_state.progress_chart_history = append_live_progress_sample(
            st.session_state.progress_chart_history,
            snapshot.latest_event,
            started_at=snapshot.started_at,
        )


def _start_job(values: dict[str, Any]) -> None:
    # Guard: if the registry already has an alive job for this session (e.g. a
    # second tab opened the same session), reattach instead of starting a new crawl.
    if get_active_job_snapshot(st.session_state.session_id) is not None:
        _reattach_selected_session_job()
        return st.rerun()
    try:
        crawler_config, page_config, activity_log_size = build_configs(values)
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    # Apply the best-matching stored HTTP credential as a secret Authorization
    # header so protected pages can be crawled. It never enters the form values or
    # the run metadata written to output files (CrawlerConfig.secret_headers).
    crawler_config.secret_headers = resolve_http_secret_headers(
        session_dir(_SESSIONS_ROOT, st.session_state.session_id),
        get_settings().zip_signing_secret,
        st.session_state.session_id,
        crawler_config.urls,
    )
    crawl_id = generate_crawl_id(
        seq=next_crawl_sequence(_SESSIONS_ROOT, st.session_state.session_id)
    )
    job = start_crawl_job(
        session_id=st.session_state.session_id,
        crawl_id=crawl_id,
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.job = job
    st.session_state.crawl_id = crawl_id
    st.session_state.job_state = _STATE_RUNNING
    st.session_state.started_at = datetime.now(timezone.utc)
    st.session_state.last_elapsed = ""
    st.session_state.latest_event = {"limit": crawler_config.limit}
    st.session_state.progress_chart_history = []
    st.session_state.prev_successful_pages = 0
    st.session_state.prev_failed_pages = 0
    st.session_state.prev_discovered_pages = 0
    st.session_state.active_output_dir = ""
    st.session_state.activity_log_size = activity_log_size
    st.session_state.activity_log_latest_line = None
    # Keep the user's entries in the disabled form during the crawl and after it
    # finishes, instead of snapping back to defaults when the expander collapses.
    st.session_state.form_defaults = form_state_from_submitted(values)
    st.rerun()


def _stop_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    if job is not None and job.thread.is_alive():
        st.session_state.job_state = _STATE_CANCEL_REQUESTED
        request_cancel(job)
        return st.rerun()
    st.warning(strings["ERROR_NO_ACTIVE_CRAWL"])


def _on_stop_dismiss() -> None:
    st.session_state.stop_confirmation_open = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_stop_dismiss)
def _stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _cancel() -> None:
        st.session_state.stop_confirmation_open = False
        st.rerun()

    def _confirm() -> None:
        st.session_state.stop_confirmation_open = False
        _stop_job()

    render_confirm_dialog(
        body=strings["DIALOG_STOP_BODY"],
        cancel_label=strings["DIALOG_BTN_KEEP"],
        cancel_key="stop_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["DIALOG_BTN_STOP"],
        confirm_key="stop_confirm_button",
        confirm_icon=":material/stop_circle:",
        on_confirm=_confirm,
    )


def _emit_crawl_progress_toasts(strings: Strings) -> None:
    """Emit app-wide crawl progress toasts from the shared shell only."""
    latest = st.session_state.latest_event
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    new_success = successful_pages - int(st.session_state.get("prev_successful_pages", 0))
    new_fail = failed_pages - int(st.session_state.get("prev_failed_pages", 0))
    new_discovered = discovered_pages - int(st.session_state.get("prev_discovered_pages", 0))
    if not st.session_state.get("preview_file_relative_path", ""):
        if new_success > 0:
            st.toast(
                strings["TOAST_SUCCESS"].format(n=successful_pages),
                icon=_TOAST_PAGE_SUCCESS_ICON,
            )
        if new_fail > 0:
            st.toast(
                strings["TOAST_FAILED"].format(n=failed_pages),
                icon=_TOAST_PAGE_FAIL_ICON,
            )
        if new_discovered > 0:
            st.toast(
                strings["TOAST_DISCOVERED"].format(n=discovered_pages),
                icon=_TOAST_PAGE_DISCOVERED_ICON,
            )
    st.session_state.prev_successful_pages = successful_pages
    st.session_state.prev_failed_pages = failed_pages
    st.session_state.prev_discovered_pages = discovered_pages


def _crawl_event_loop_body() -> None:
    """Drain crawl events and emit shell-owned toasts on every workflow page."""
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    state_changed = _drain_job_events(st.session_state.job)
    if state_changed and st.session_state.job_state in _REFRESH_FORM_STATES:
        st.rerun()
    _emit_crawl_progress_toasts(strings)


def _render_crawl_event_loop() -> None:
    """Auto-rerun the crawl event loop only while a crawl job is active."""
    _auto_refresh_fragment(_crawl_event_loop_body, active=_crawl_job_active())
