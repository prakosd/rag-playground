"""Step 2 content area for vector indexing."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import streamlit as st
from artifact_store.crawl_results import CrawlResultFile

from app_support.i18n import get_strings
from app_support.vector_index.vector_form_ui import has_index_inputs, render_vector_index_form


@dataclass(frozen=True)
class VectorIndexPageContext:
    """Callbacks supplied by the shared app shell for the vector-index area."""

    current_runtime: Callable[[], tuple[Any, str, bool, bool]]
    crawl_result_files: Callable[[], Sequence[CrawlResultFile]]
    start_job: Callable[[dict[str, Any]], None]
    stop_confirmation_dialog: Callable[[], None]
    render_live_area: Callable[[], None]
    render_downloads: Callable[[], None]
    default_language: str


def render_page(context: VectorIndexPageContext) -> None:
    """Render the vector index page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    current_job, current_state, job_alive, fields_disabled = context.current_runtime()
    st.subheader(strings["VEC_SECTION_HEADER"], anchor="vector-index-header")
    st.caption(strings["VEC_SECTION_CAPTION"])
    values = render_vector_index_form(
        fields_disabled=fields_disabled,
        state=current_state,
        job_alive=job_alive,
        strings=strings,
        crawl_result_files=context.crawl_result_files(),
    )
    if values["submitted"]:
        st.session_state.vector_index_stop_confirmation_open = False
        if current_job is not None and current_job.thread.is_alive():
            st.warning(strings["VEC_ERROR_ALREADY_RUNNING"])
        elif not has_index_inputs(values["selected_paths"], len(values["uploaded_files"])):
            st.warning(strings["VEC_ERROR_NO_INPUTS"])
        else:
            context.start_job(values)
    elif values["stop_submitted"]:
        st.session_state.vector_index_stop_confirmation_open = True

    if st.session_state.vector_index_stop_confirmation_open and not job_alive:
        st.session_state.vector_index_stop_confirmation_open = False

    if st.session_state.vector_index_stop_confirmation_open:
        context.stop_confirmation_dialog()

    context.render_live_area()
    context.render_downloads()
