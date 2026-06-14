"""UI-independent retrieval-augmented generation over persisted vector indexes.

``rag_engine`` powers Steps 3-5 of the app: semantic search, single-turn QA, and
conversational (history-aware) RAG. It reopens an index built by ``vector_indexer``
using the same embedding model, retrieves relevant chunks, and generates answers
with a chat model resolved through LangChain's ``init_chat_model`` (with an
offline echo fallback). It does not depend on Streamlit or any other UI.
"""

from __future__ import annotations

from rag_engine.catalog import (
    CHAT_MODEL_OPTIONS,
    DEFAULT_CHAT_MODEL,
    ECHO_MODEL,
    ChatModelInfo,
    get_chat_model_info,
)
from rag_engine.chat import (
    chat_answer,
    condense_question,
    generate_chat_answer,
    stream_chat_answer,
)
from rag_engine.config import RagConfig
from rag_engine.llm import (
    ChatModelUnavailable,
    ResolvedChatModel,
    resolve_chat_model,
)
from rag_engine.models import ChatTurn, RagAnswer, RetrievedChunk
from rag_engine.qa import answer_question, generate_answer, stream_answer
from rag_engine.retrieval import RetrievalResult, retrieve

__all__ = [
    "CHAT_MODEL_OPTIONS",
    "DEFAULT_CHAT_MODEL",
    "ECHO_MODEL",
    "ChatModelInfo",
    "ChatModelUnavailable",
    "ChatTurn",
    "RagAnswer",
    "RagConfig",
    "ResolvedChatModel",
    "RetrievalResult",
    "RetrievedChunk",
    "answer_question",
    "chat_answer",
    "condense_question",
    "generate_answer",
    "generate_chat_answer",
    "get_chat_model_info",
    "resolve_chat_model",
    "retrieve",
    "stream_answer",
    "stream_chat_answer",
]
