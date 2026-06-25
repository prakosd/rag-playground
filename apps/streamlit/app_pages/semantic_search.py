"""Step 3 content area for semantic search."""

from __future__ import annotations

import streamlit as st
from rag_engine import RagConfig, retrieve

from crawl4md_streamlit.i18n import get_strings
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    mmr_controls_enabled,
    render_index_metadata,
    render_messages,
    render_ranked_results,
    select_index,
)
from crawl4md_streamlit.settings import get_settings

_settings = get_settings()
_DEFAULT_TOP_N = _settings.semantic_search_top_n
_DEFAULT_RESULT_TAB = _settings.semantic_search_default_tab
_DEFAULT_MODE = _settings.semantic_search_default_mode
_DEFAULT_MIN_SCORE_PERCENT = _settings.semantic_search_min_score_percent
_DEFAULT_FETCH_K = _settings.semantic_search_fetch_k
_DEFAULT_MMR_LAMBDA = _settings.semantic_search_mmr_lambda
_SEARCH_MODES = ("similarity", "mmr")
_DEFAULT_SEARCH_MODE = _SEARCH_MODES[0]

# Pin the Search-mode segmented control to its natural width so the row's three
# controls stay evenly spaced (Diversity / Candidate pool absorb the slack)
# instead of leaving a widening gap after Search mode on large screens.
_SEARCH_MODE_COLUMN_CSS = (
    "<style>"
    "/* Pin the Search-mode column to its natural width */"
    "div[data-testid=\"stColumn\"]:has(.st-key-semantic_search_mode){flex:0 0 auto!important;width:auto!important;max-width:none!important;padding-right:0!important;margin-right:0!important;}"
    "/* Remove any right-side padding/margin from the element container and its immediate children */"
    "div.st-key-semantic_search_mode[data-testid=\"stElementContainer\"],"
    "div.st-key-semantic_search_mode[data-testid=\"stElementContainer\"] > *{padding-right:0!important;margin-right:0!important;}"
    "/* Ensure the inner button-group doesn't add extra right spacing */"
    "div.st-key-semantic_search_mode .stButtonGroup,"
    "div.st-key-semantic_search_mode .stButtonGroup > *{padding-right:0!important;margin-right:0!important;}"
    "</style>"
)


def render_page(context: RagPageContext) -> None:
    """Render the semantic search page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    st.markdown(
        f'<h3 id="semantic-search-header" style="margin-bottom:0;padding-bottom:0;padding-top:0">'
        f"{strings['SEARCH_SECTION_HEADER']}</h3>"
        f'<p style="opacity:0.6;font-size:0.875rem;margin:0;margin-bottom:1rem">'
        f"{strings['SEARCH_SECTION_CAPTION']}</p>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        index = select_index(strings, list(context.list_indexes()), key="semantic_search_index")
        if index is not None:
            render_index_metadata(strings, index)

    # Move the search options into the form so they're rendered just above
    # the submit button and included in the form state on submit.

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

        # Place the collapsible search options inside the form so they
        # appear directly above the Search button and are included in the
        # form state on submit.
        with st.expander(strings["SEARCH_OPTIONS_EXPANDER"]):
            st.markdown(_SEARCH_MODE_COLUMN_CSS, unsafe_allow_html=True)
            mode_col, diversity_col, pool_col = st.columns(3)
            with mode_col:
                search_mode = st.segmented_control(
                    strings["SEARCH_MODE_LABEL"],
                    options=_SEARCH_MODES,
                    default=_DEFAULT_MODE if _DEFAULT_MODE in _SEARCH_MODES else _DEFAULT_SEARCH_MODE,
                    format_func=lambda mode: (
                        strings["SEARCH_MODE_MMR"]
                        if mode == "mmr"
                        else strings["SEARCH_MODE_SIMILARITY"]
                    ),
                    help=strings["SEARCH_MODE_HELP"],
                    disabled=index is None,
                    key="semantic_search_mode",
                )
            mmr_enabled = mmr_controls_enabled(search_mode or _DEFAULT_SEARCH_MODE)
            with diversity_col:
                mmr_lambda = st.slider(
                    strings["SEARCH_MMR_LAMBDA_LABEL"],
                    min_value=0.0,
                    max_value=1.0,
                    value=_DEFAULT_MMR_LAMBDA,
                    step=0.05,
                    help=strings["SEARCH_MMR_LAMBDA_HELP"],
                    disabled=index is None or not mmr_enabled,
                )
            with pool_col:
                fetch_k = st.number_input(
                    strings["SEARCH_FETCH_K_LABEL"],
                    min_value=1,
                    max_value=200,
                    value=_DEFAULT_FETCH_K,
                    step=5,
                    help=strings["SEARCH_FETCH_K_HELP"],
                    disabled=index is None or not mmr_enabled,
                )
            min_score_percent = st.slider(
                strings["SEARCH_MIN_SCORE_LABEL"],
                min_value=0,
                max_value=100,
                value=_DEFAULT_MIN_SCORE_PERCENT,
                step=5,
                format="%d%%",
                help=strings["SEARCH_MIN_SCORE_HELP"],
                disabled=index is None,
            )
            source_options = list(index.manifest.indexed_sources) if index is not None else []
            selected_sources = st.multiselect(
                strings["SEARCH_SOURCE_FILTER_LABEL"],
                options=source_options,
                help=strings["SEARCH_SOURCE_FILTER_HELP"],
                placeholder=strings["SEARCH_SOURCE_FILTER_PLACEHOLDER"],
                disabled=index is None or not source_options,
            )

        submitted = st.form_submit_button(
            strings["SEARCH_BUTTON"],
            type="primary",
            icon=":material/search:",
            disabled=index is None,
        )

    if submitted and index is not None and query.strip():
        config = RagConfig(
            top_k=int(top_n),
            score_threshold=min_score_percent / 100,
            search_type=search_mode or _DEFAULT_SEARCH_MODE,
            fetch_k=int(fetch_k),
            lambda_mult=float(mmr_lambda),
            source_filter=tuple(selected_sources),
        )
        with st.spinner(strings["SEARCH_SEARCHING"]):
            result = retrieve(index.run_dir, query.strip(), config)
        render_messages(strings, result.warnings, result.errors)
        if result.chunks:
            render_ranked_results(strings, result.chunks, default_tab=_DEFAULT_RESULT_TAB)
        elif not result.errors:
            st.info(strings["SEARCH_NO_RESULTS"])

    context.render_downloads()
