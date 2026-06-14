from __future__ import annotations

from rag_engine.catalog import (
    CHAT_MODEL_OPTIONS,
    DEFAULT_CHAT_MODEL,
    ECHO_MODEL,
    get_chat_model_info,
)


def test_default_model_is_in_options() -> None:
    assert any(info.model_id == DEFAULT_CHAT_MODEL for info in CHAT_MODEL_OPTIONS)


def test_echo_model_is_local_and_keyless() -> None:
    info = get_chat_model_info(ECHO_MODEL)

    assert info is not None
    assert info.kind == "local"
    assert not info.requires_api_key


def test_unknown_model_returns_none() -> None:
    assert get_chat_model_info("nope/model") is None


def test_cloud_models_require_a_key() -> None:
    for info in CHAT_MODEL_OPTIONS:
        if info.kind == "cloud":
            assert info.requires_api_key


def test_lookup_ignores_surrounding_whitespace() -> None:
    assert get_chat_model_info(f"  {ECHO_MODEL}  ") is not None
