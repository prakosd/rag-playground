"""Step-2 vector-index background-job orchestration extracted from ``streamlit_app.py``.

Owns the vector-index job lifecycle: start/stop (+ confirmation dialog), re-attaching a
running index job on session switch, and the crawl-result / existing-index list helpers
the Step-2 page uses. Reads/writes ``st.session_state`` directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st
from artifact_store.crawl_results import list_crawl_result_files
from pydantic import ValidationError
from vector_indexer import IndexingConfig

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _SESSIONS_ROOT,
    _STATE_CANCEL_REQUESTED,
    _STATE_RUNNING,
    _session_root,
)
from app_support.dialog_ui import render_confirm_dialog
from app_support.i18n import get_strings
from app_support.progress_ui import _apply_vector_index_event
from app_support.rag_shared.index_catalog import list_session_indexes
from app_support.session_manager import generate_vector_id, next_vector_sequence
from app_support.vector_index.vector_index_jobs import (
    get_active_vector_job_snapshot,
    start_vector_index_job,
)
from app_support.vector_index.vector_index_jobs import request_cancel as request_vector_cancel


def _reattach_selected_session_vector_job() -> None:
    """Restore a running indexing job from the process-local registry after refresh.

    Mirrors `_reattach_selected_session_job` for Step 2 so a second browser tab (or
    a reloaded page) shows the in-progress indexing and keeps the form locked while
    it runs. Does nothing if a vector job is already attached to this session.
    """
    if st.session_state.vector_index_job is not None:
        return
    session_id = st.session_state.session_id
    if not session_id:
        return
    snapshot = get_active_vector_job_snapshot(session_id)
    if snapshot is None:
        return
    st.session_state.vector_index_job = snapshot.job
    st.session_state.vector_index_id = snapshot.vector_id
    st.session_state.vector_index_state = snapshot.job_state
    st.session_state.vector_index_started_at = snapshot.started_at
    st.session_state.vector_index_progress = {}
    st.session_state.vector_index_stage = ""
    st.session_state.vector_index_result = {}
    # Replay the latest event so the reattached page shows the current stage,
    # chunk progress, or terminal result without waiting for the next emit.
    if snapshot.latest_event:
        _apply_vector_index_event(snapshot.latest_event)


def _crawl_result_files() -> list[Any]:
    return list(list_crawl_result_files(_session_root()))


def _list_session_indexes() -> list[Any]:
    return list_session_indexes(_session_root())


def _start_vector_index_job(values: dict[str, Any]) -> None:
    # Guard: if the registry already has an alive indexing job for this session
    # (e.g. a second tab started one), reattach instead of launching a duplicate.
    if get_active_vector_job_snapshot(st.session_state.session_id) is not None:
        _reattach_selected_session_vector_job()
        return st.rerun()
    try:
        config = IndexingConfig(
            chunk_size=values["chunk_size"],
            chunk_overlap=values["chunk_overlap"],
            embedding_model=values["embedding_model"],
            embedding_dimension=values["embedding_dimension"],
            language=values["language"],
            index_workers=values["index_workers"],
        )
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    uploads = [(file.name, file.getvalue()) for file in values["uploaded_files"]]
    vector_id = generate_vector_id(
        seq=next_vector_sequence(_SESSIONS_ROOT, st.session_state.session_id)
    )
    job = start_vector_index_job(
        session_id=st.session_state.session_id,
        vector_id=vector_id,
        config=config,
        selected_paths=values["selected_paths"],
        uploads=uploads,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.vector_index_job = job
    st.session_state.vector_index_id = vector_id
    st.session_state.vector_index_state = _STATE_RUNNING
    st.session_state.vector_index_progress = {}
    st.session_state.vector_index_stage = ""
    st.session_state.vector_index_result = {}
    st.session_state.vector_index_started_at = datetime.now(timezone.utc)
    st.rerun()


def _stop_vector_index_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.get("vector_index_job")
    if job is not None and job.thread.is_alive():
        st.session_state.vector_index_state = _STATE_CANCEL_REQUESTED
        request_vector_cancel(job)
        return st.rerun()
    st.warning(strings["VEC_ERROR_NO_ACTIVE_INDEX"])


def _on_vector_stop_dismiss() -> None:
    st.session_state.vector_index_stop_confirmation_open = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_vector_stop_dismiss)
def _vector_index_stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _cancel() -> None:
        st.session_state.vector_index_stop_confirmation_open = False
        st.rerun()

    def _confirm() -> None:
        st.session_state.vector_index_stop_confirmation_open = False
        _stop_vector_index_job()

    render_confirm_dialog(
        body=strings["VEC_DIALOG_STOP_BODY"],
        cancel_label=strings["DIALOG_BTN_KEEP"],
        cancel_key="vector_stop_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["VEC_DIALOG_BTN_STOP"],
        confirm_key="vector_stop_confirm_button",
        confirm_icon=":material/stop_circle:",
        on_confirm=_confirm,
    )
