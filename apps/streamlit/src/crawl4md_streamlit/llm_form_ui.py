"""Chat-model selector helpers for the RAG pages (Steps 4-5).

Mirrors ``vector_form_ui``'s embedding selector: the pure option/label helpers
are unit-testable without Streamlit, and ``render_llm_controls`` renders the
model picker plus the "chunks to retrieve" control.
"""

from __future__ import annotations

import streamlit as st
from rag_engine import CHAT_MODEL_OPTIONS, ChatModelInfo, get_chat_model_info

from crawl4md_streamlit.i18n import Strings
from crawl4md_streamlit.settings import get_settings

__all__ = [
    "chat_model_info_for",
    "chat_model_label",
    "chat_model_options",
    "render_llm_controls",
]

_DEFAULT_TOP_K = get_settings().rag_top_k
_MAX_TOP_K = 20
_LLM_CONTROL_COLUMN_WIDTHS = (7, 3)

# Open fallback used only if a selected model is ever absent from the catalog;
# the catalog covers every id in ``chat_model_options()``.
_UNKNOWN_MODEL_INFO = ChatModelInfo(
    model_id="",
    provider="",
    label="",
    kind="cloud",
    requires_api_key=True,
)


def chat_model_options() -> list[str]:
    """Return the chat-model ids offered in the selector."""
    return [info.model_id for info in CHAT_MODEL_OPTIONS]


def chat_model_info_for(model_id: str) -> ChatModelInfo:
    """Return catalog metadata for *model_id*, or an open fallback."""
    return get_chat_model_info(model_id) or _UNKNOWN_MODEL_INFO


def chat_model_label(model_id: str, strings: Strings) -> str:
    """Return a selectbox label tagging a model as offline or cloud."""
    info = get_chat_model_info(model_id)
    if info is None:
        return model_id
    tag_key = "RAG_LLM_TAG_OFFLINE" if info.kind == "local" else "RAG_LLM_TAG_CLOUD"
    return f"{info.label} · {strings[tag_key]}"


def render_llm_controls(
    *, strings: Strings, key_prefix: str, disabled: bool = False
) -> tuple[str, int]:
    """Render the chat-model picker and retrieval depth; return (model, top_k)."""
    options = chat_model_options()
    with st.container(gap=None):
        cols = st.columns(_LLM_CONTROL_COLUMN_WIDTHS)
        with cols[0]:
            model = st.selectbox(
                strings["RAG_LLM_LABEL"],
                options=options,
                format_func=lambda model_id: chat_model_label(model_id, strings),
                help=strings["RAG_LLM_HELP"],
                disabled=disabled,
                key=f"{key_prefix}_llm_model",
            )
        with cols[1]:
            top_k = int(
                st.number_input(
                    strings["RAG_TOP_K_LABEL"],
                    min_value=1,
                    max_value=_MAX_TOP_K,
                    value=_DEFAULT_TOP_K,
                    step=1,
                    help=strings["RAG_TOP_K_HELP"],
                    disabled=disabled,
                    key=f"{key_prefix}_top_k",
                )
            )
        info = chat_model_info_for(model)
        if info.kind == "local":
            st.caption(strings["RAG_LLM_INDICATOR_OFFLINE"])
        else:
            st.caption(strings["RAG_LLM_INDICATOR_CLOUD"])
    return model, top_k
