from __future__ import annotations

import pytest

from rag_engine import messages
from rag_engine.catalog import DEFAULT_CHAT_MODEL, ECHO_MODEL
from rag_engine.llm import (
    ChatModelUnavailable,
    build_chat_model,
    build_echo_chat_model,
    resolve_chat_model,
)


def test_echo_model_builds_and_echoes_offline() -> None:
    from langchain_core.messages import HumanMessage

    model = build_echo_chat_model()
    response = model.invoke([HumanMessage("hello world")])

    assert "hello world" in response.content


def test_unknown_model_is_unavailable() -> None:
    with pytest.raises(ChatModelUnavailable):
        build_chat_model("nope/model")


def test_bedrock_without_credentials_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ChatModelUnavailable):
        build_chat_model(DEFAULT_CHAT_MODEL)


def test_openai_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ChatModelUnavailable):
        build_chat_model("gpt-4o-mini")


def test_resolve_falls_back_to_echo() -> None:
    sentinel = object()

    def failing_build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        raise ChatModelUnavailable("no credentials")

    resolved, warnings = resolve_chat_model(
        "gpt-4o", build=failing_build, echo_build=lambda: sentinel
    )

    assert resolved.model_id == ECHO_MODEL
    assert resolved.model is sentinel
    assert any(w.code == messages.CODE_MODEL_FALLBACK_ECHO for w in warnings)


def test_resolve_available_model_has_no_warnings() -> None:
    sentinel = object()

    def build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        return sentinel

    resolved, warnings = resolve_chat_model("gpt-4o", build=build, echo_build=lambda: object())

    assert resolved.model is sentinel
    assert resolved.model_id == "gpt-4o"
    assert warnings == []


def test_resolve_echo_request_failure_raises() -> None:
    def failing_build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        raise ChatModelUnavailable("echo broken")

    with pytest.raises(ChatModelUnavailable):
        resolve_chat_model(ECHO_MODEL, build=failing_build, echo_build=lambda: object())


def test_thinking_disabled_kwargs_targets_only_bedrock_qwen() -> None:
    from rag_engine.llm import thinking_disabled_model_kwargs

    qwen = thinking_disabled_model_kwargs("apac.qwen.qwen3-32b-v1:0", "bedrock_converse")
    assert qwen == {
        "additional_model_request_fields": {"chat_template_kwargs": {"enable_thinking": False}}
    }
    assert thinking_disabled_model_kwargs("apac.amazon.nova-lite-v1:0", "bedrock_converse") == {}
    assert thinking_disabled_model_kwargs("gpt-4o-mini", "openai") == {}
    assert thinking_disabled_model_kwargs(ECHO_MODEL, "echo") == {}
