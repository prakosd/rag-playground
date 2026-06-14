"""Step 4 content area for single-turn RAG Q&A."""

from __future__ import annotations

import streamlit as st
from rag_engine import RagConfig, answer_question

from crawl4md_streamlit.i18n import get_strings
from crawl4md_streamlit.llm_form_ui import render_llm_controls
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    render_messages,
    render_model_caption,
    render_sources,
    select_index,
)


def render_page(context: RagPageContext) -> None:
    """Render the RAG Q&A page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    st.subheader(strings["QA_SECTION_HEADER"], anchor="rag-qa-header")
    st.caption(strings["QA_SECTION_CAPTION"])

    index = select_index(strings, list(context.list_indexes()), key="rag_qa_index")
    model, top_k = render_llm_controls(strings=strings, key_prefix="rag_qa", disabled=index is None)
    with st.form("rag_qa_form", enter_to_submit=False, border=True):
        question = st.text_area(
            strings["QA_QUESTION_LABEL"],
            placeholder=strings["QA_QUESTION_PLACEHOLDER"],
            disabled=index is None,
        )
        submitted = st.form_submit_button(
            strings["QA_BUTTON"],
            type="primary",
            icon=":material/send:",
            disabled=index is None,
        )

    if not (submitted and index is not None and question.strip()):
        return
    config = RagConfig(llm_model=model, top_k=int(top_k))
    with st.spinner(strings["RAG_GENERATING"]):
        answer = answer_question(index.run_dir, question.strip(), config)
    render_messages(strings, answer.warnings, answer.errors)
    if answer.answer:
        st.markdown(f"**{strings['QA_ANSWER_HEADER']}**")
        st.write(answer.answer)
        render_model_caption(strings, answer.model_used)
        render_sources(strings, answer.sources)
