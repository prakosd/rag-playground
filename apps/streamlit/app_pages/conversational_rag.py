"""Step 5 content area for conversational, history-aware RAG."""

from __future__ import annotations

import streamlit as st
from rag_engine import RagConfig, chat_answer

from crawl4md_streamlit.i18n import get_strings
from crawl4md_streamlit.llm_form_ui import render_llm_controls
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    render_messages,
    render_model_caption,
    render_sources,
    select_index,
    to_chat_turns,
)

_HISTORY_KEY = "conversational_rag_history"


def render_page(context: RagPageContext) -> None:
    """Render the conversational RAG page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    st.subheader(strings["CHAT_SECTION_HEADER"], anchor="conversational-rag-header")
    st.caption(strings["CHAT_SECTION_CAPTION"])

    index = select_index(strings, list(context.list_indexes()), key="conversational_rag_index")
    model, top_k = render_llm_controls(
        strings=strings, key_prefix="conversational_rag", disabled=index is None
    )

    history: list[dict] = st.session_state.setdefault(_HISTORY_KEY, [])
    if st.button(
        strings["CHAT_CLEAR_BUTTON"],
        icon=":material/delete:",
        disabled=not history,
    ):
        st.session_state[_HISTORY_KEY] = []
        st.rerun()

    if not history:
        st.info(strings["CHAT_EMPTY_HINT"])
    for message in history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if message["role"] == "assistant":
                render_model_caption(strings, message.get("model_used"))
                render_sources(strings, message.get("sources", []))

    question = st.chat_input(strings["CHAT_INPUT_PLACEHOLDER"], disabled=index is None)
    if not (question and index is not None):
        return

    prior_turns = to_chat_turns(history)
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    config = RagConfig(llm_model=model, top_k=int(top_k))
    with st.chat_message("assistant"):
        with st.spinner(strings["RAG_GENERATING"]):
            answer = chat_answer(index.run_dir, question, prior_turns, config)
        render_messages(strings, answer.warnings, answer.errors)
        if answer.answer:
            st.write(answer.answer)
            render_model_caption(strings, answer.model_used)
            render_sources(strings, answer.sources)

    history.append(
        {
            "role": "assistant",
            "content": answer.answer,
            "model_used": answer.model_used,
            "sources": answer.sources,
        }
    )
