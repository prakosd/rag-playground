"""Shared UI building blocks for the RAG pages (Steps 3-5).

Holds the page context the shell injects plus the render helpers common to
semantic search, QA, and conversational RAG: the index picker, the source list,
localized library messages, and chat-history conversion. Page modules stay thin
by composing these with ``rag_engine`` calls.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import streamlit as st
from artifact_store import LibraryMessage
from rag_engine import ChatTurn, RetrievedChunk
from vector_indexer import IndexManifest

from crawl4md_streamlit.i18n import Strings, localize_message
from crawl4md_streamlit.index_catalog import IndexRef

__all__ = [
    "RagPageContext",
    "format_score_percent",
    "index_metadata_caption",
    "render_index_metadata",
    "render_messages",
    "render_model_caption",
    "render_ranked_results",
    "render_sources",
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


def index_metadata_caption(strings: Strings, manifest: IndexManifest) -> str:
    """Build the one-line caption summarising an index's embedding settings."""
    return strings["SEARCH_META_CAPTION"].format(
        model=manifest.embedding_model_used or manifest.embedding_model_requested or "?",
        language=manifest.language or "?",
        overlap=manifest.chunk_overlap if manifest.chunk_overlap is not None else "?",
        collection=manifest.collection_name,
    )


def _result_meta_caption(strings: Strings, chunk: RetrievedChunk) -> str:
    parts: list[str] = []
    chunk_index = chunk.metadata.get("chunk_index")
    if chunk_index:
        parts.append(strings["SEARCH_RESULT_CHUNK"].format(index=chunk_index))
    language = chunk.metadata.get("language")
    if language:
        parts.append(strings["SEARCH_RESULT_LANGUAGE"].format(language=language))
    return " · ".join(parts)


def render_index_metadata(strings: Strings, index: IndexRef) -> None:
    """Show the selected index's useful manifest details below the picker."""
    manifest = index.manifest
    with st.container(border=True):
        st.markdown(f"**{strings['SEARCH_META_HEADER']}**")
        dimension_col, files_col, chunks_col, size_col = st.columns(4)
        dimension_col.metric(strings["SEARCH_META_DIMENSION"], manifest.embedding_dimension or "—")
        files_col.metric(strings["SEARCH_META_FILES"], manifest.indexed_file_count)
        chunks_col.metric(strings["SEARCH_META_CHUNKS"], manifest.indexed_chunk_count)
        size_col.metric(strings["SEARCH_META_CHUNK_SIZE"], manifest.chunk_size or "—")
        st.caption(index_metadata_caption(strings, manifest))


def render_ranked_results(strings: Strings, chunks: Sequence[RetrievedChunk]) -> None:
    """Render search hits as ranked cards, each with a similarity progress bar."""
    ranked = sort_results_by_score(chunks)
    if not ranked:
        return
    st.markdown(f"**{strings['SEARCH_RESULTS_HEADER']}**")
    st.caption(strings["SEARCH_RESULTS_SUMMARY"].format(count=len(ranked)))
    for rank, chunk in enumerate(ranked, start=1):
        with st.container(border=True):
            st.markdown(
                strings["SEARCH_RESULT_HEADER"].format(rank=rank, source=chunk.source or "?")
            )
            percent = format_score_percent(chunk.score)
            st.progress(percent / 100, text=strings["SEARCH_RESULT_SCORE"].format(score=percent))
            st.write(chunk.text)
            meta = _result_meta_caption(strings, chunk)
            if meta:
                st.caption(meta)


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
