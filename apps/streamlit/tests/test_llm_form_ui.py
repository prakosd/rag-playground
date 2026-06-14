from __future__ import annotations

from rag_engine import CHAT_MODEL_OPTIONS, DEFAULT_CHAT_MODEL, ECHO_MODEL

from crawl4md_streamlit.i18n import STRINGS_EN
from crawl4md_streamlit.llm_form_ui import (
    chat_model_info_for,
    chat_model_label,
    chat_model_options,
)


def test_options_match_catalog() -> None:
    assert chat_model_options() == [info.model_id for info in CHAT_MODEL_OPTIONS]
    assert DEFAULT_CHAT_MODEL in chat_model_options()
    assert ECHO_MODEL in chat_model_options()


def test_label_tags_offline_and_cloud() -> None:
    echo_label = chat_model_label(ECHO_MODEL, STRINGS_EN)
    assert STRINGS_EN["RAG_LLM_TAG_OFFLINE"] in echo_label

    cloud_label = chat_model_label("gpt-4o", STRINGS_EN)
    assert STRINGS_EN["RAG_LLM_TAG_CLOUD"] in cloud_label


def test_label_unknown_model_returns_id() -> None:
    assert chat_model_label("unknown/model", STRINGS_EN) == "unknown/model"


def test_info_for_unknown_returns_open_fallback() -> None:
    info = chat_model_info_for("unknown/model")

    assert info.model_id == ""
    assert info.kind == "cloud"


def test_info_for_echo_is_local() -> None:
    info = chat_model_info_for(ECHO_MODEL)

    assert info.kind == "local"
    assert not info.requires_api_key
