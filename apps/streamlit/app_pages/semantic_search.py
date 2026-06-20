"""Step 3 content area for semantic search."""

from __future__ import annotations

import streamlit as st
from rag_engine import RagConfig, retrieve

from crawl4md_streamlit.i18n import get_strings
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    render_index_metadata,
    render_messages,
    render_ranked_results,
    select_index,
)
from crawl4md_streamlit.settings import get_settings

_DEFAULT_TOP_N = get_settings().semantic_search_top_n


def render_page(context: RagPageContext) -> None:
    """Render the semantic search page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    st.subheader(strings["SEARCH_SECTION_HEADER"], anchor="semantic-search-header")
    st.caption(strings["SEARCH_SECTION_CAPTION"])

    index = select_index(strings, list(context.list_indexes()), key="semantic_search_index")
    if index is not None:
        render_index_metadata(strings, index)

    with st.form("semantic_search_form", enter_to_submit=True, border=True):
        query = st.text_input(
            strings["SEARCH_QUERY_LABEL"],
            placeholder=strings["SEARCH_QUERY_PLACEHOLDER"],
            disabled=index is None,
        )
        top_n = st.slider(
            strings["SEARCH_TOP_N_LABEL"],
            min_value=1,
            max_value=20,
            value=_DEFAULT_TOP_N,
            help=strings["SEARCH_TOP_N_HELP"],
            disabled=index is None,
        )
        submitted = st.form_submit_button(
            strings["SEARCH_BUTTON"],
            type="primary",
            icon=":material/search:",
            disabled=index is None,
        )
    st.caption(strings["SEARCH_SEMANTIC_HINT"])

    if submitted and index is not None and query.strip():
        with st.spinner(strings["SEARCH_SEARCHING"]):
            result = retrieve(index.run_dir, query.strip(), RagConfig(top_k=int(top_n)))
        render_messages(strings, result.warnings, result.errors)
        if result.chunks:
            render_ranked_results(strings, result.chunks)
        elif not result.errors:
            st.info(strings["SEARCH_NO_RESULTS"])

    context.render_downloads()
