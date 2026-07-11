from __future__ import annotations

from rag_engine import CHAT_MODEL_OPTIONS, ECHO_MODEL

from app_support.i18n import STRINGS_EN
from app_support.rag_shared.llm_form_ui import (
    chat_model_info_for,
    chat_model_label,
    chat_model_options,
    resolve_chat_model_choices,
)
from app_support.settings import get_settings


def test_options_are_env_curated_and_catalogued() -> None:
    options = chat_model_options()
    catalog_ids = {info.model_id for info in CHAT_MODEL_OPTIONS}

    assert set(options) <= catalog_ids  # only catalogued models are offered
    assert get_settings().rag_default_llm_model in options
    assert ECHO_MODEL not in options  # echo is the silent fallback, never offered


def test_resolve_chat_model_choices_curates_and_orders() -> None:
    options, index = resolve_chat_model_choices(["b", "x", "a"], ["a", "b", "c"], "a")

    assert options == ["b", "a"]  # "x" dropped (uncatalogued); order follows configured
    assert options[index] == "a"


def test_resolve_chat_model_choices_falls_back_to_all_when_none_valid() -> None:
    options, index = resolve_chat_model_choices(["x"], ["a", "b"], "b")

    assert options == ["a", "b"]
    assert options[index] == "b"


def test_label_tags_offline_and_cloud() -> None:
    echo_label = chat_model_label(ECHO_MODEL, STRINGS_EN)
    assert STRINGS_EN["RAG_LLM_TAG_OFFLINE"] in echo_label

    cloud_label = chat_model_label("gpt-4o", STRINGS_EN)
    assert STRINGS_EN["RAG_LLM_TAG_CLOUD"] in cloud_label


def test_label_unknown_model_returns_id() -> None:
    assert chat_model_label("unknown/model", STRINGS_EN) == "unknown/model"


def test_label_includes_model_size() -> None:
    # gpt-4o-mini is a small model; its size label appears in the picker text.
    assert STRINGS_EN["RAG_LLM_SIZE_SMALL"] in chat_model_label("gpt-4o-mini", STRINGS_EN)


def test_info_for_unknown_returns_open_fallback() -> None:
    info = chat_model_info_for("unknown/model")

    assert info.model_id == ""
    assert info.kind == "cloud"


def test_info_for_echo_is_local() -> None:
    info = chat_model_info_for(ECHO_MODEL)

    assert info.kind == "local"
    assert not info.requires_api_key
