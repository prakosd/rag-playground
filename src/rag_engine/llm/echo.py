"""Offline echo chat model: the universal fallback and a deterministic test double.

It generates no real answer — it repeats the last user message — so the RAG
workflow runs end-to-end without credentials. The ``BaseChatModel`` subclass is
built lazily so importing this module does not pull langchain-core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = ["build_echo_chat_model"]

_echo_cls: type | None = None

_ECHO_PREFIX = "Echo (offline model — no answer generated): "


def build_echo_chat_model() -> BaseChatModel:
    """Return an instance of the offline echo chat model."""
    return _echo_class()()


def _echo_class() -> type:
    global _echo_cls
    if _echo_cls is not None:
        return _echo_cls

    from langchain_core.language_models import SimpleChatModel

    class EchoChatModel(SimpleChatModel):
        """A deterministic offline model that echoes the last user message."""

        @property
        def _llm_type(self) -> str:
            return "echo"

        def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
            last_human = next(
                (
                    str(message.content)
                    for message in reversed(messages)
                    if getattr(message, "type", "") == "human"
                ),
                "",
            )
            return f"{_ECHO_PREFIX}{last_human}".strip()

    _echo_cls = EchoChatModel
    return _echo_cls
