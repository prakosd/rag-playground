"""Shared placeholder content for RAG workflow pages."""

from __future__ import annotations

import streamlit as st

from crawl4md_streamlit.i18n import get_strings
from crawl4md_streamlit.pages import page_spec_by_id
from crawl4md_streamlit.support import DEFAULT_SESSION_LANGUAGE


def render_placeholder_page(page_id: str) -> None:
    """Render the temporary content area for a workflow page."""
    strings = get_strings(st.session_state.get("language", DEFAULT_SESSION_LANGUAGE))
    page_spec = page_spec_by_id(page_id)
    if page_spec.placeholder_key is None:
        return
    st.subheader(strings["PLACEHOLDER_SECTION_HEADER"], anchor="crawl4md-header")
    st.caption(strings["PLACEHOLDER_SECTION_CAPTION"])
    with st.expander(strings["PLACEHOLDER_EXPANDER_LABEL"], expanded=True):
        st.write(strings[page_spec.placeholder_key])
