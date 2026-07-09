"""Step 3 content area for semantic search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from rag_engine import RagConfig, retrieve

from crawl4md_streamlit.focus import entered_page, focus_widget
from crawl4md_streamlit.i18n import Strings, get_strings
from crawl4md_streamlit.index_catalog import IndexRef
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    find_index,
    index_option_label,
    kv_grid_html,
    local_time_label,
    render_index_metadata,
    render_messages,
    render_results_panel,
    select_index,
    stacked_label_value_html,
)
from crawl4md_streamlit.search_history import (
    SearchRecord,
    append_search_record,
    load_search_history,
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
_INITIAL_MODE = _DEFAULT_MODE if _DEFAULT_MODE in _SEARCH_MODES else _DEFAULT_SEARCH_MODE

# Widget keys let a history replay pre-fill the form; the replay keys carry a
# pending re-run request across the st.rerun() boundary.
_QUERY_KEY = "semantic_search_query"
_TOP_N_KEY = "semantic_search_top_n"
_MODE_KEY = "semantic_search_mode"
_MMR_LAMBDA_KEY = "semantic_search_mmr_lambda"
_FETCH_K_KEY = "semantic_search_fetch_k"
_MIN_SCORE_KEY = "semantic_search_min_score"
_SOURCES_KEY = "semantic_search_sources"
_INDEX_KEY = "semantic_search_index"
_REPLAY_KEY = "semantic_search_replay"
_REPLAY_EXECUTE_KEY = "semantic_search_replay_execute"
# The last search's hits persist here so the results panel survives reruns; the
# expand flag is a one-shot that opens the panel only right after a fresh search.
_RESULTS_KEY = "semantic_search_results"
_RESULTS_EXPAND_KEY = "semantic_search_results_expanded"
# One-shot flag: a history replay sets it so focus moves to the query field.
_FOCUS_QUERY_KEY = "semantic_search_focus_query"


def render_page(context: RagPageContext) -> None:
    """Render the semantic search page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    session_root = context.session_root()
    indexes = list(context.list_indexes())

    # Focus the query field once when the user lands on this page (not on later
    # reruns), so they can start typing straight away.
    if entered_page("semantic_search"):
        st.session_state[_FOCUS_QUERY_KEY] = True

    st.subheader(strings["SEARCH_SECTION_HEADER"], anchor="semantic-search-header")
    st.caption(strings["SEARCH_SECTION_CAPTION"])

    # Apply a pending history replay before the widgets render so the form shows
    # the replayed query and options; the search itself runs from the form below.
    replay = st.session_state.pop(_REPLAY_KEY, None)
    if replay is not None:
        _apply_replay_widget_state(strings, indexes, replay)
        st.session_state[_REPLAY_EXECUTE_KEY] = replay

    # Seed first-run widget values in session state so a replay can overwrite them
    # without Streamlit warning about a default value also set via Session State.
    st.session_state.setdefault(_QUERY_KEY, "")
    st.session_state.setdefault(_TOP_N_KEY, _DEFAULT_TOP_N)
    st.session_state.setdefault(_MODE_KEY, _INITIAL_MODE)
    st.session_state.setdefault(_MMR_LAMBDA_KEY, _DEFAULT_MMR_LAMBDA)
    st.session_state.setdefault(_FETCH_K_KEY, _DEFAULT_FETCH_K)
    st.session_state.setdefault(_MIN_SCORE_KEY, _DEFAULT_MIN_SCORE_PERCENT)
    st.session_state.setdefault(_SOURCES_KEY, [])

    with st.container(border=True):
        index = select_index(strings, indexes, key=_INDEX_KEY)
        if index is not None:
            render_index_metadata(strings, index)

    with st.form("semantic_search_form", enter_to_submit=True, border=True):
        query_col, top_n_col = st.columns([0.8, 0.2])
        with query_col:
            query = st.text_input(
                strings["SEARCH_QUERY_LABEL"],
                placeholder=strings["SEARCH_QUERY_PLACEHOLDER"],
                disabled=index is None,
                key=_QUERY_KEY,
            )
        with top_n_col:
            top_n = st.number_input(
                strings["SEARCH_TOP_N_LABEL"],
                min_value=1,
                max_value=20,
                step=1,
                help=strings["SEARCH_TOP_N_HELP"],
                disabled=index is None,
                key=_TOP_N_KEY,
            )

        # Place the collapsible search options inside the form so they
        # appear directly above the Search button and are included in the
        # form state on submit.
        with st.expander(strings["SEARCH_OPTIONS_EXPANDER"]):
            mode_col, diversity_col = st.columns(2)
            with mode_col:
                search_mode = st.segmented_control(
                    strings["SEARCH_MODE_LABEL"],
                    options=_SEARCH_MODES,
                    format_func=lambda mode: (
                        strings["SEARCH_MODE_MMR"]
                        if mode == "mmr"
                        else strings["SEARCH_MODE_SIMILARITY"]
                    ),
                    help=strings["SEARCH_MODE_HELP"],
                    disabled=index is None,
                    key=_MODE_KEY,
                )
            with diversity_col:
                mmr_lambda = st.slider(
                    strings["SEARCH_MMR_LAMBDA_LABEL"],
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    help=strings["SEARCH_MMR_LAMBDA_HELP"],
                    disabled=index is None,
                    key=_MMR_LAMBDA_KEY,
                )
            pool_col, min_score_col = st.columns(2)
            with pool_col:
                fetch_k = st.number_input(
                    strings["SEARCH_FETCH_K_LABEL"],
                    min_value=1,
                    max_value=200,
                    step=5,
                    help=strings["SEARCH_FETCH_K_HELP"],
                    disabled=index is None,
                    key=_FETCH_K_KEY,
                )
            with min_score_col:
                min_score_percent = st.slider(
                    strings["SEARCH_MIN_SCORE_LABEL"],
                    min_value=0,
                    max_value=100,
                    step=5,
                    format="%d%%",
                    help=strings["SEARCH_MIN_SCORE_HELP"],
                    disabled=index is None,
                    key=_MIN_SCORE_KEY,
                )
            source_options = list(index.manifest.indexed_sources) if index is not None else []
            _prune_stale_sources(source_options)
            selected_sources = st.multiselect(
                strings["SEARCH_SOURCE_FILTER_LABEL"],
                options=source_options,
                help=strings["SEARCH_SOURCE_FILTER_HELP"],
                placeholder=strings["SEARCH_SOURCE_FILTER_PLACEHOLDER"],
                disabled=index is None or not source_options,
                key=_SOURCES_KEY,
            )

        submitted = st.form_submit_button(
            strings["SEARCH_BUTTON"],
            type="primary",
            icon=":material/search:",
            disabled=index is None,
        )

    # A history replay pre-fills the query across the rerun; move focus there so
    # the user can edit and re-run it straight away.
    if st.session_state.pop(_FOCUS_QUERY_KEY, False):
        focus_widget(_QUERY_KEY)

    # Resolve the search to run: a history replay takes precedence over a submit.
    request: tuple[IndexRef, str, RagConfig] | None = None
    replay_execute = st.session_state.pop(_REPLAY_EXECUTE_KEY, None)
    if replay_execute is not None:
        ref = find_index(
            indexes,
            str(replay_execute.get("index_folder", "")),
            str(replay_execute.get("index_run", "")),
        )
        if ref is None:
            st.warning(strings["SEARCH_HISTORY_INDEX_GONE"])
        else:
            request = (
                ref,
                str(replay_execute.get("query", "")),
                _config_from_record(replay_execute),
            )
    elif submitted and index is not None and query.strip():
        request = (
            index,
            query.strip(),
            RagConfig(
                top_k=int(top_n),
                score_threshold=min_score_percent / 100,
                search_type=search_mode or _DEFAULT_SEARCH_MODE,
                fetch_k=int(fetch_k),
                lambda_mult=float(mmr_lambda),
                source_filter=tuple(selected_sources),
            ),
        )

    if request is not None:
        ref, query_text, config = request
        with st.spinner(strings["SEARCH_SEARCHING"]):
            result = retrieve(ref.run_dir, query_text, config)
        render_messages(strings, result.warnings, result.errors)
        scores = [chunk.score for chunk in result.chunks]
        append_search_record(
            session_root,
            SearchRecord(
                timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                index_folder=ref.vector_folder,
                index_run=ref.run_name,
                embedding_model=ref.manifest.embedding_model_used or "",
                query=query_text,
                search_type=config.search_type,
                top_k=config.top_k,
                fetch_k=config.fetch_k,
                mmr_lambda=config.lambda_mult,
                score_threshold=config.score_threshold,
                source_filter=tuple(config.source_filter),
                result_count=len(result.chunks),
                top_score=max(scores) if scores else None,
            ),
        )
        # Persist the hits so the results panel survives later reruns; only a
        # fresh search opens it — it stays collapsed on reload and other reruns.
        st.session_state[_RESULTS_KEY] = list(result.chunks)
        st.session_state[_RESULTS_EXPAND_KEY] = True

    # The results panel is always rendered so its gap to the history panel stays
    # constant. Before the first search it invites one; a search that returned
    # nothing says so instead.
    stored_chunks = st.session_state.get(_RESULTS_KEY)
    empty_hint = (
        strings["SEARCH_NO_RESULTS"]
        if _RESULTS_KEY in st.session_state
        else strings["SEARCH_RESULTS_EMPTY"]
    )
    render_results_panel(
        strings,
        stored_chunks or [],
        empty_hint=empty_hint,
        default_tab=_DEFAULT_RESULT_TAB,
        expanded=st.session_state.pop(_RESULTS_EXPAND_KEY, False),
    )

    _render_search_history(strings, session_root, indexes)

    context.render_downloads()


def _apply_replay_widget_state(strings: Strings, indexes: Sequence[IndexRef], replay: dict) -> None:
    """Pre-fill the search widgets from a stored history record before they render."""
    st.session_state[_QUERY_KEY] = str(replay.get("query", ""))
    st.session_state[_TOP_N_KEY] = int(replay.get("top_k", _DEFAULT_TOP_N))
    st.session_state[_MODE_KEY] = str(replay.get("search_type", _DEFAULT_SEARCH_MODE))
    st.session_state[_MMR_LAMBDA_KEY] = float(replay.get("mmr_lambda", _DEFAULT_MMR_LAMBDA))
    st.session_state[_FETCH_K_KEY] = int(replay.get("fetch_k", _DEFAULT_FETCH_K))
    st.session_state[_MIN_SCORE_KEY] = round(float(replay.get("score_threshold", 0.0)) * 100)
    ref = find_index(indexes, str(replay.get("index_folder", "")), str(replay.get("index_run", "")))
    if ref is not None:
        st.session_state[_INDEX_KEY] = index_option_label(strings, ref)
        st.session_state[_SOURCES_KEY] = [
            str(source) for source in replay.get("source_filter", []) or []
        ]


def _prune_stale_sources(source_options: list[str]) -> None:
    """Drop any selected source no longer offered by the current index.

    The multiselect is keyed so a replay can pre-fill it; without this guard,
    switching to an index with different sources would raise on a stale value.
    """
    selected = st.session_state.get(_SOURCES_KEY)
    if selected:
        st.session_state[_SOURCES_KEY] = [source for source in selected if source in source_options]


def _config_from_record(record: dict) -> RagConfig:
    return RagConfig(
        top_k=int(record.get("top_k", _DEFAULT_TOP_N)),
        score_threshold=float(record.get("score_threshold", 0.0)),
        search_type=str(record.get("search_type", _DEFAULT_SEARCH_MODE)),
        fetch_k=int(record.get("fetch_k", _DEFAULT_FETCH_K)),
        lambda_mult=float(record.get("mmr_lambda", _DEFAULT_MMR_LAMBDA)),
        source_filter=tuple(str(source) for source in record.get("source_filter", []) or []),
    )


def _options_summary(strings: Strings, record: SearchRecord) -> str:
    """Build a compact one-line summary of a record's search options."""
    mode_label = (
        strings["SEARCH_MODE_MMR"]
        if record.search_type == "mmr"
        else strings["SEARCH_MODE_SIMILARITY"]
    )
    parts = [
        mode_label,
        strings["SEARCH_HISTORY_OPT_TOP"].format(n=record.top_k),
        strings["SEARCH_HISTORY_OPT_MIN"].format(n=round(record.score_threshold * 100)),
    ]
    if record.search_type == "mmr":
        parts.append(
            strings["SEARCH_HISTORY_OPT_DIVERSITY"].format(value=f"{record.mmr_lambda:.2f}")
        )
        parts.append(strings["SEARCH_HISTORY_OPT_POOL"].format(n=record.fetch_k))
    if record.source_filter:
        parts.append(strings["SEARCH_HISTORY_OPT_SOURCES"].format(n=len(record.source_filter)))
    return " · ".join(parts)


def _index_detail_rows(
    strings: Strings, record: SearchRecord, ref: IndexRef | None
) -> list[tuple[str, str]]:
    """Return the (label, value) index-detail pairs for a search-history card.

    Enriched from the live manifest so the card mirrors the index Details panel;
    only the embedding model survives on the record when the index is gone, so the
    remaining fields show a dash without a live manifest.
    """
    manifest = ref.manifest if ref is not None else None

    def _text(value: object) -> str:
        return "—" if value in (None, "") else str(value)

    model = record.embedding_model
    if manifest is not None and manifest.embedding_model_used:
        model = manifest.embedding_model_used
    dimension = _text(manifest.embedding_dimension if manifest else None)
    chunks = _text(manifest.indexed_chunk_count if manifest else None)
    chunk_size = _text(manifest.chunk_size if manifest else None)
    overlap = _text(manifest.chunk_overlap if manifest else None)
    return [
        (strings["SEARCH_META_MODEL"], _text(model)),
        (strings["SEARCH_META_LANGUAGE"], _text(manifest.language if manifest else None)),
        (strings["SEARCH_META_DIMENSION_CHUNKS"], f"{dimension} / {chunks}"),
        (strings["SEARCH_META_CHUNK_SIZE_OVERLAP"], f"{chunk_size} / {overlap}"),
    ]


def _render_search_history(
    strings: Strings, session_root: Path, indexes: Sequence[IndexRef]
) -> None:
    """Render the collapsible search history as a tidy card list.

    Each card leads with the query + a replay button, then a collapsed Details
    expander holding a 4-column label/value grid (time, result count, source
    index, search options, and the index fields broken out — embedding model,
    language, dimension, chunk size, chunks, overlap — enriched from the live
    manifest when the index still exists), matching the index Details panel.
    """
    records = load_search_history(session_root)
    with st.expander(strings["SEARCH_HISTORY_EXPANDER"], expanded=False):
        if not records:
            st.caption(strings["SEARCH_HISTORY_EMPTY"])
            return
        for position, record in enumerate(records):
            ref = find_index(indexes, record.index_folder, record.index_run)
            with st.container(border=True):
                head, action = st.columns([0.85, 0.15], vertical_alignment="center")
                head.markdown(
                    stacked_label_value_html(strings["SEARCH_HISTORY_LABEL_QUERY"], record.query),
                    unsafe_allow_html=True,
                )
                with action, st.container(horizontal_alignment="right"):
                    if st.button(
                        ":material/replay:",
                        key=f"search_history_replay_{position}",
                        help=strings["SEARCH_HISTORY_REPLAY_HELP"],
                    ):
                        st.session_state[_REPLAY_KEY] = asdict(record)
                        st.session_state[_FOCUS_QUERY_KEY] = True
                        st.rerun()
                with st.expander(strings["SEARCH_HISTORY_LABEL_DETAILS"], expanded=False):
                    st.markdown(_search_history_grid(strings, record, ref), unsafe_allow_html=True)


def _search_history_grid(strings: Strings, record: SearchRecord, ref: IndexRef | None) -> str:
    """Build the 4-column label/value grid summarising one search-history record.

    Leads with the query facts (time, results, index, options), then the index
    details broken out into their own fields — mirroring the index Details panel.
    """
    rows = [
        (strings["SEARCH_HISTORY_LABEL_TIME"], local_time_label(record.timestamp_utc)),
        (
            strings["SEARCH_HISTORY_LABEL_RESULTS"],
            strings["SEARCH_HISTORY_RESULT_COUNT"].format(n=record.result_count),
        ),
        (strings["SEARCH_HISTORY_LABEL_INDEX_NAME"], record.index_folder),
        (strings["SEARCH_HISTORY_LABEL_INDEX_DATE"], record.index_run),
        (strings["SEARCH_HISTORY_LABEL_OPTIONS"], _options_summary(strings, record)),
        *_index_detail_rows(strings, record, ref),
    ]
    return kv_grid_html(rows, columns=4, margin_bottom=True)
