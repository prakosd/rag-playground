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
    st.markdown(
        f'<h3 id="semantic-search-header" style="margin-bottom:0;padding-bottom:0;padding-top:0">'
        f"{strings['SEARCH_SECTION_HEADER']}</h3>"
        f'<p style="opacity:0.6;font-size:0.875rem;margin:0">'
        f"{strings['SEARCH_SECTION_CAPTION']}</p>",
        unsafe_allow_html=True,
    )

    index = select_index(strings, list(context.list_indexes()), key="semantic_search_index")
    if index is not None:
        render_index_metadata(strings, index)

    with st.form("semantic_search_form", enter_to_submit=True, border=True):
        query_col, top_n_col = st.columns([0.8, 0.2])
        with query_col:
            query = st.text_input(
                strings["SEARCH_QUERY_LABEL"],
                placeholder=strings["SEARCH_QUERY_PLACEHOLDER"],
                disabled=index is None,
            )
        with top_n_col:
            top_n = st.number_input(
                strings["SEARCH_TOP_N_LABEL"],
                min_value=1,
                max_value=20,
                value=_DEFAULT_TOP_N,
                step=1,
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
