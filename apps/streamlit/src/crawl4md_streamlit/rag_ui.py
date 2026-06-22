"""Shared UI building blocks for the RAG pages (Steps 3-5).

Holds the page context the shell injects plus the render helpers common to
semantic search, QA, and conversational RAG: the index picker, the source list,
localized library messages, and chat-history conversion. Page modules stay thin
by composing these with ``rag_engine`` calls.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import streamlit as st
from artifact_store import LibraryMessage
from rag_engine import ChatTurn, RetrievedChunk
from vector_indexer import IndexManifest

from crawl4md_streamlit.i18n import Strings, localize_message
from crawl4md_streamlit.index_catalog import IndexRef

__all__ = [
    "RagPageContext",
    "format_score_percent",
    "index_metadata_rows",
    "render_index_metadata",
    "render_messages",
    "render_model_caption",
    "render_ranked_results",
    "render_sources",
    "result_detail_caption",
    "select_index",
    "sort_results_by_score",
    "to_chat_turns",
]


@dataclass(frozen=True)
class RagPageContext:
    """Shell-provided services for the RAG content areas (Steps 3-5)."""

    default_language: str
    list_indexes: Callable[[], Sequence[IndexRef]]
    render_downloads: Callable[[], None]


def select_index(strings: Strings, indexes: Sequence[IndexRef], *, key: str) -> IndexRef | None:
    """Render the index picker; return the chosen index or ``None`` when empty."""
    if not indexes:
        st.info(strings["RAG_NO_INDEX_HINT"])
        return None
    labels: dict[str, IndexRef] = {}
    for ref in indexes:
        label = strings["RAG_INDEX_OPTION"].format(
            folder=ref.vector_folder,
            run=ref.run_name,
            model=ref.manifest.embedding_model_used or "?",
            chunks=ref.manifest.indexed_chunk_count,
        )
        labels[label] = ref
    chosen = st.selectbox(
        strings["RAG_INDEX_LABEL"],
        options=list(labels),
        help=strings["RAG_INDEX_HELP"],
        key=key,
    )
    return labels.get(chosen)


def render_sources(
    strings: Strings,
    sources: Sequence[RetrievedChunk],
    *,
    header_key: str = "RAG_SOURCES_HEADER",
) -> None:
    """Render retrieved chunks as labelled, expandable source snippets."""
    if not sources:
        return
    st.markdown(f"**{strings[header_key]}**")
    for index, chunk in enumerate(sources, start=1):
        caption = strings["RAG_SOURCE_CAPTION"].format(
            source=chunk.source or "?", score=round(chunk.score, 3)
        )
        with st.expander(f"{index}. {caption}"):
            st.write(chunk.text)


def format_score_percent(score: float) -> int:
    """Clamp a 0-1 similarity to an integer percentage for display."""
    return round(max(0.0, min(1.0, score)) * 100)


def sort_results_by_score(chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    """Return chunks ordered by similarity score, highest first."""
    return sorted(chunks, key=lambda chunk: chunk.score, reverse=True)


def index_metadata_rows(strings: Strings, manifest: IndexManifest) -> list[tuple[str, str]]:
    """Return ordered (label, value) pairs describing an index for compact display."""
    return [
        (strings["SEARCH_META_CREATED"], _format_created_at(manifest.created_at)),
        (
            strings["SEARCH_META_MODEL"],
            manifest.embedding_model_used or manifest.embedding_model_requested or "—",
        ),
        (strings["SEARCH_META_DIMENSION"], _value_or_dash(manifest.embedding_dimension)),
        (strings["SEARCH_META_LANGUAGE"], manifest.language or "—"),
        (strings["SEARCH_META_CHUNK_SIZE"], _value_or_dash(manifest.chunk_size)),
        (strings["SEARCH_META_OVERLAP"], _value_or_dash(manifest.chunk_overlap)),
        (strings["SEARCH_META_FILES"], str(manifest.indexed_file_count)),
        (strings["SEARCH_META_CHUNKS"], str(manifest.indexed_chunk_count)),
        (strings["SEARCH_META_SKIPPED"], str(manifest.skipped_file_count)),
        (strings["SEARCH_META_COLLECTION"], manifest.collection_name),
    ]


def _value_or_dash(value: object) -> str:
    return "—" if value is None else str(value)


def _format_created_at(created_at: str | None) -> str:
    """Format an ISO-8601 manifest timestamp as a compact ``YYYY-MM-DD HH:MM UTC``."""
    if not created_at:
        return "—"
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError:
        return created_at
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def result_detail_caption(strings: Strings, chunk: RetrievedChunk) -> str:
    """Build the per-result detail line: chunk id, character size, and language."""
    chunk_index = chunk.metadata.get("chunk_index", "?")
    parts = [
        strings["SEARCH_RESULT_ID"].format(id=f"{chunk.source or '?'}#{chunk_index}"),
        strings["SEARCH_RESULT_SIZE"].format(size=len(chunk.text)),
    ]
    language = chunk.metadata.get("language")
    if language:
        parts.append(strings["SEARCH_RESULT_LANGUAGE"].format(language=language))
    return " · ".join(parts)


def render_index_metadata(strings: Strings, index: IndexRef) -> None:
    """Show the selected index's manifest details as a compact key/value list."""
    rows = "".join(
        '<div style="display:flex;justify-content:space-between;gap:1rem;'
        'padding:1px 0;font-size:0.875rem">'
        f'<span style="opacity:0.65">{html.escape(label)}</span>'
        f'<span style="text-align:right">{html.escape(value)}</span></div>'
        for label, value in index_metadata_rows(strings, index.manifest)
    )
    with st.container(border=True):
        st.markdown(f":material/database: **{strings['SEARCH_META_HEADER']}**")
        st.markdown(rows, unsafe_allow_html=True)


def render_ranked_results(strings: Strings, chunks: Sequence[RetrievedChunk]) -> None:
    """Render search hits as ranked cards.

    Each card shows a source + similarity header row, then the chunk text in a
    Preview/Raw tabbed card, then the chunk's id and character size.
    """
    ranked = sort_results_by_score(chunks)
    if not ranked:
        return
    st.markdown(f"**{strings['SEARCH_RESULTS_HEADER']}**")
    st.caption(strings["SEARCH_RESULTS_SUMMARY"].format(count=len(ranked)))
    for rank, chunk in enumerate(ranked, start=1):
        with st.container(border=True):
            title_col, score_col = st.columns([0.7, 0.3], vertical_alignment="center")
            title_col.markdown(
                strings["SEARCH_RESULT_HEADER"].format(rank=rank, source=chunk.source or "?")
            )
            score_col.metric(
                strings["SEARCH_RESULT_SIMILARITY"], f"{format_score_percent(chunk.score)}%"
            )
            with st.container(border=True):
                preview_tab, raw_tab = st.tabs(
                    [strings["SEARCH_RESULT_TAB_PREVIEW"], strings["SEARCH_RESULT_TAB_RAW"]]
                )
                with preview_tab:
                    st.markdown(chunk.text)
                with raw_tab:
                    st.code(chunk.text, language="markdown")
            st.caption(result_detail_caption(strings, chunk))


def render_messages(
    strings: Strings,
    warnings: Sequence[LibraryMessage],
    errors: Sequence[LibraryMessage],
) -> None:
    """Localize and display library warnings (yellow) and errors (red)."""
    for warning in warnings:
        st.warning(localize_message(strings, warning.as_dict()))
    for error in errors:
        st.error(localize_message(strings, error.as_dict()))


def render_model_caption(strings: Strings, model_used: str | None) -> None:
    """Show which chat model produced the answer."""
    if model_used:
        st.caption(strings["RAG_MODEL_USED_CAPTION"].format(model=model_used))


def to_chat_turns(history: Sequence[dict]) -> list[ChatTurn]:
    """Convert stored chat messages into ``ChatTurn`` objects for retrieval."""
    return [ChatTurn(role=message["role"], content=message["content"]) for message in history]
