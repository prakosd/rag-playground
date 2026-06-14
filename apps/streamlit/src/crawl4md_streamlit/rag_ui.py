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

from crawl4md_streamlit.i18n import Strings, localize_message
from crawl4md_streamlit.index_catalog import IndexRef

__all__ = [
    "RagPageContext",
    "render_messages",
    "render_model_caption",
    "render_sources",
    "select_index",
    "to_chat_turns",
]


@dataclass(frozen=True)
class RagPageContext:
    """Shell-provided services for the RAG content areas (Steps 3-5)."""

    default_language: str
    list_indexes: Callable[[], Sequence[IndexRef]]


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
