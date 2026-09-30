"""Language + session-selection controls extracted from ``streamlit_app.py``.

Owns choosing/creating/loading/extending the active session, restoring the UI
language, and rendering the session-controls + language-selector row. Reads/writes
``st.session_state`` directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _ICON_BUTTON_WIDTH_PX,
    _SESSIONS_ROOT,
    _STATE_IDLE,
)
from app_support.focus import focus_widget
from app_support.i18n import CATALOG, Strings, get_strings
from app_support.session_reset import clear_transient_result_state
from app_support.settings import get_settings
from app_support.shell.assets import (
    _LANGUAGE_SELECTOR_CSS,
    _LANGUAGE_SELECTOR_WRAP_KEY,
)
from app_support.shell.constants import (
    _CREATE_TOAST_STATE,
    _DIALOG_LOAD_SESSION_TITLE,
    _EXTEND_TOAST_FAILED,
    _EXTEND_TOAST_STATE,
    _EXTEND_TOAST_SUCCESS,
    _LOAD_TOAST_STATE,
    _SWITCH_TOAST_STATE,
    _TOAST_PAGE_FAIL_ICON,
    _TOAST_PAGE_SUCCESS_ICON,
)
from app_support.shell.session_storage import (
    _browser_session_records,
    _cached_normalize_session_records,
)
from app_support.support import (
    SessionRecord,
    create_session_record,
    latest_session_id,
    serialize_session_records,
    session_dir,
    session_exists,
    session_time_remaining,
    touch_session,
    validate_safe_id,
)


def _normalize_language(value: object) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in CATALOG else _DEFAULT_LANGUAGE


def _language_widget_key() -> str:
    session_id = str(st.session_state.get("session_id", "")).strip()
    return f"language_selector_{session_id or 'bootstrap'}"


def _sync_language_widget_state() -> str:
    widget_key = _language_widget_key()
    language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.session_state.language = language
    # Keep the selector pinned to a valid language so it never renders unselected
    # (segmented_control is deselectable and can bootstrap empty on Streamlit Cloud).
    if st.session_state.get(widget_key) not in CATALOG:
        st.session_state[widget_key] = language
    return widget_key


def _select_session_id(session_id: str, *, restore_language: bool = True) -> None:
    if not session_id:
        return
    records = _browser_session_records()
    known_ids = {record.session_id for record in records}
    if session_id not in known_ids:
        return
    if st.session_state.session_id != session_id:
        st.session_state.preview_file_relative_path = ""
        st.session_state.latest_event = {}
        st.session_state.progress_chart_history = []
        st.session_state.active_output_dir = ""
        st.session_state.activity_log_latest_line = None
        st.session_state.last_elapsed = ""
        st.session_state.job = None
        st.session_state.job_state = _STATE_IDLE
        st.session_state.started_at = None
        st.session_state.prev_successful_pages = 0
        st.session_state.prev_failed_pages = 0
        st.session_state.prev_discovered_pages = 0
        # Detach any vector-index job too, so the newly selected session reattaches
        # its own active indexing run (if any) instead of showing a stale one.
        st.session_state.vector_index_job = None
        st.session_state.vector_index_id = ""
        st.session_state.vector_index_state = _STATE_IDLE
        st.session_state.vector_index_progress = {}
        st.session_state.vector_index_stage = ""
        st.session_state.vector_index_result = {}
        st.session_state.vector_index_started_at = None
        # Drop Step 3/4 search hits and generated answer so the switched-to
        # session starts clean instead of showing the previous one's results.
        clear_transient_result_state(st.session_state)
        # Persist the newly selected session id back to browser storage only on change.
        st.session_state.pending_selected_session_id = session_id
    st.session_state.session_id = session_id
    st.session_state.preferred_session_id = session_id
    if not restore_language:
        return
    for record in records:
        if record.session_id == session_id:
            st.session_state.language = _normalize_language(record.language)
            break


def _commit_session_record(record: SessionRecord) -> None:
    """Merge *record* into browser session state and stage it for localStorage write."""
    records = _cached_normalize_session_records(
        [
            *serialize_session_records(_browser_session_records()),
            *serialize_session_records([record]),
        ]
    )
    pending_records = _cached_normalize_session_records(
        [
            *st.session_state.pending_browser_session_records,
            *serialize_session_records([record]),
        ]
    )
    st.session_state.browser_session_records = records
    st.session_state.pending_browser_session_records = serialize_session_records(pending_records)
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False


def _create_new_session() -> None:
    record = create_session_record()
    st.session_state.language = record.language
    _commit_session_record(record)
    _select_session_id(record.session_id)
    st.session_state[_CREATE_TOAST_STATE] = True
    st.rerun()


def _register_and_select_session(session_id: str) -> None:
    """Register an externally known session into local browser records and select it."""
    mtime = session_dir(_SESSIONS_ROOT, session_id).stat().st_mtime
    created_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
    touch_session(_SESSIONS_ROOT, session_id)
    current_language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    record = create_session_record(session_id=session_id, language=current_language, now=created_at)
    _commit_session_record(record)
    st.session_state.session_load_dialog_open = False
    st.session_state[_LOAD_TOAST_STATE] = record.session_id
    _select_session_id(record.session_id, restore_language=False)
    st.rerun()


def _on_load_session_dismiss() -> None:
    st.session_state.session_load_dialog_open = False
    st.session_state["_load_session_enter"] = False


@st.dialog(_DIALOG_LOAD_SESSION_TITLE, width="small", on_dismiss=_on_load_session_dismiss)
def _load_session_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _on_input_commit() -> None:
        st.session_state["_load_session_enter"] = True

    session_id_input = st.text_input(
        label=strings["DIALOG_LOAD_SESSION_ID_LABEL"],
        placeholder=strings["DIALOG_LOAD_SESSION_ID_PLACEHOLDER"],
        help=strings["DIALOG_LOAD_SESSION_ID_HELP"],
        key="load_session_id_input",
        on_change=_on_input_commit,
    )
    if st.session_state.pop("_focus_session_id", False):
        focus_widget("load_session_id_input")
    error_slot = st.empty()
    cancel_col, _, load_col = st.columns([2, 5, 3])
    with cancel_col:
        if st.button(strings["DIALOG_LOAD_BTN_CANCEL"], key="load_session_cancel"):
            st.session_state["_load_session_enter"] = False
            st.session_state.session_load_dialog_open = False
            st.rerun()
    with load_col, st.container(horizontal_alignment="right"):
        load_clicked = st.button(
            strings["DIALOG_LOAD_BTN_LOAD"],
            type="primary",
            icon=":material/folder_open:",
            key="load_session_confirm",
        )
    enter_submitted = st.session_state.get("_load_session_enter", False)
    st.session_state["_load_session_enter"] = False
    if load_clicked or enter_submitted:
        stripped = session_id_input.strip()
        if not stripped:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        try:
            validate_safe_id(stripped)
        except ValueError:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        known_ids = {r.session_id for r in _browser_session_records()}
        if stripped in known_ids:
            st.session_state[_SWITCH_TOAST_STATE] = stripped
            st.session_state.session_load_dialog_open = False
            _select_session_id(stripped)
            st.rerun()
        if not session_exists(_SESSIONS_ROOT, stripped):
            error_slot.error(strings["DIALOG_LOAD_SESSION_NOT_FOUND"].format(id=stripped))
            return
        _register_and_select_session(stripped)


def _ensure_selected_session() -> None:
    records = _browser_session_records()
    if records:
        known_ids = {record.session_id for record in records}
        preferred_session_id = str(st.session_state.get("preferred_session_id", ""))
        current_session_id = str(st.session_state.get("session_id", ""))
        selected_session_id = current_session_id
        if preferred_session_id in known_ids:
            selected_session_id = preferred_session_id
        elif current_session_id not in known_ids:
            selected_session_id = latest_session_id(records)
        restore_language = (
            selected_session_id != current_session_id
            or str(st.session_state.get("language", "")).strip().upper() not in CATALOG
        )
        _select_session_id(
            selected_session_id,
            restore_language=restore_language,
        )
        return

    record = create_session_record()
    st.session_state.browser_session_records = [record]
    st.session_state.pending_browser_session_records = serialize_session_records([record])
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False
    _select_session_id(record.session_id)
    st.rerun()


def _on_language_change(widget_key: str) -> None:
    new_lang = _normalize_language(st.session_state.get(widget_key, _DEFAULT_LANGUAGE))
    st.session_state.language = new_lang
    # The on_change callback can fire before _init_state runs (hot-reload/bootstrap), so
    # read session_id defensively; with no active session there's no record to re-tag yet.
    session_id = st.session_state.get("session_id", "")
    if not session_id:
        return
    records = _browser_session_records()
    updated = [
        SessionRecord(r.session_id, r.created_at, new_lang) if r.session_id == session_id else r
        for r in records
    ]
    st.session_state.browser_session_records = updated
    updated_record = next((r for r in updated if r.session_id == session_id), None)
    if updated_record is not None:
        pending = _cached_normalize_session_records(
            [
                *st.session_state.pending_browser_session_records,
                *serialize_session_records([updated_record]),
            ]
        )
        st.session_state.pending_browser_session_records = serialize_session_records(pending)


def _session_options() -> list[str]:
    return [record.session_id for record in _browser_session_records()]


def _session_selector_index(options: list[str]) -> int:
    if st.session_state.session_id in options:
        return options.index(st.session_state.session_id)
    return 0


def _render_session_controls(
    *,
    fields_disabled: bool,
    language_widget_key: str,
    strings: Strings,
) -> None:
    session_options = _session_options()
    session_controls_col, language_col = st.columns([5, 1], vertical_alignment="top")
    with session_controls_col:
        extend_toast = st.session_state.pop(_EXTEND_TOAST_STATE, None)
        if extend_toast == _EXTEND_TOAST_SUCCESS:
            st.toast(strings["TOAST_SESSION_EXTENDED"], icon=_TOAST_PAGE_SUCCESS_ICON)
        elif extend_toast == _EXTEND_TOAST_FAILED:
            st.toast(strings["TOAST_SESSION_EXTEND_FAILED"], icon=_TOAST_PAGE_FAIL_ICON)
        with st.container(gap="xxsmall"):
            with st.container(horizontal=True, vertical_alignment="bottom", gap="xxsmall"):
                with st.container(
                    horizontal=True, vertical_alignment="center", width="content", gap="xxsmall"
                ):
                    st.markdown(strings["SESSION_SELECTOR_LABEL"])
                    selected_session = st.selectbox(
                        label=strings["SESSION_SELECTOR_LABEL"],
                        options=session_options,
                        index=_session_selector_index(session_options),
                        key=f"session_selector_{st.session_state.session_id}",
                        label_visibility="collapsed",
                        width=240,
                        disabled=fields_disabled,
                    )
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_create_button",
                    icon=":material/add:",
                    help=strings["SESSION_CREATE_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    _create_new_session()
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_load_button",
                    icon=":material/folder_open:",
                    help=strings["SESSION_LOAD_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    st.session_state.session_load_dialog_open = True
                    st.session_state["_focus_session_id"] = True
                    st.rerun()
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_extend_button",
                    icon=":material/more_time:",
                    help=strings["SESSION_EXTEND_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    try:
                        touch_session(_SESSIONS_ROOT, st.session_state.session_id)
                        st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_SUCCESS
                    except (OSError, ValueError):
                        st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_FAILED
                    st.rerun()
            days_left, hours_left = session_time_remaining(
                _SESSIONS_ROOT,
                st.session_state.session_id,
                retention_days=get_settings().session_retention_days,
            )
            if days_left == 0:
                if hours_left == 0:
                    expiry_key = "SESSION_EXPIRY_CAPTION_SOON"
                elif hours_left == 1:
                    expiry_key = "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR"
                else:
                    expiry_key = "SESSION_EXPIRY_CAPTION_HOURS"
            elif hours_left == 0:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_SINGULAR"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION"
                )
            elif hours_left == 1:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_DAY_HOUR"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION_DAYS_HOUR"
                )
            else:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_DAY_HOURS"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION_DAYS_HOURS"
                )
            st.caption(strings[expiry_key].format(days=days_left, hours=hours_left))
        if selected_session != st.session_state.session_id:
            _select_session_id(str(selected_session))
            st.rerun()
    with (
        language_col,
        st.container(horizontal_alignment="right", gap=None, key=_LANGUAGE_SELECTOR_WRAP_KEY),
    ):
        st.markdown(_LANGUAGE_SELECTOR_CSS, unsafe_allow_html=True)
        language_default = (
            _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
            if language_widget_key not in st.session_state
            else None
        )
        st.segmented_control(
            label=strings["LANG_SELECTOR_LABEL"],
            options=list(CATALOG.keys()),
            key=language_widget_key,
            default=language_default,
            label_visibility="visible",
            disabled=fields_disabled,
            on_change=_on_language_change,
            args=(language_widget_key,),
        )
