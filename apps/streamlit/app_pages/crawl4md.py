"""Step 1 content area for the crawl4md Streamlit workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st

from crawl4md_streamlit.form_ui import render_crawl_form
from crawl4md_streamlit.i18n import get_strings


@dataclass(frozen=True)
class CrawlPageContext:
    """Callbacks supplied by the shared app shell for the crawler content area."""

    current_runtime: Callable[[], tuple[Any, str, bool, bool]]
    start_job: Callable[[dict[str, Any]], None]
    stop_confirmation_dialog: Callable[[], None]
    render_ready_result_panel: Callable[[], None]
    render_live_area: Callable[[], None]
    render_downloads: Callable[[], None]
    default_language: str


def render_page(context: CrawlPageContext) -> None:
    """Render the crawler page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    current_job, current_state, job_alive, fields_disabled = context.current_runtime()

    values = render_crawl_form(
        fields_disabled=fields_disabled,
        expanded=not fields_disabled,
        state=current_state,
        job_alive=job_alive,
        strings=strings,
        defaults=st.session_state.form_defaults,
        activity_log_size=int(st.session_state.activity_log_size),
    )
    if values["submitted"]:
        st.session_state.stop_confirmation_open = False
        if current_job is not None and current_job.thread.is_alive():
            st.warning(strings["ERROR_CRAWL_ALREADY_RUNNING"])
        else:
            context.start_job(values)
    elif values["stop_submitted"]:
        st.session_state.stop_confirmation_open = True

    if st.session_state.stop_confirmation_open and not job_alive:
        st.session_state.stop_confirmation_open = False

    if st.session_state.stop_confirmation_open:
        context.stop_confirmation_dialog()

    context.render_ready_result_panel()
    st.subheader(strings["PROGRESS_HEADER"])
    st.caption(strings["PROGRESS_CAPTION"])
    context.render_live_area()
    context.render_downloads()
