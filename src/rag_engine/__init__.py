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
    ConversationalGeneration,
    chat_answer,
    condense_question,
    conversational_answer,
    conversational_answer_stream,
    generate_chat_answer,
    generate_chat_answer_with_usage,
    stream_chat_answer,
)
from rag_engine.config import ConversationalConfig, ConversationalPrompts, RagConfig
from rag_engine.llm import (
    ChatModelUnavailable,
    ResolvedChatModel,
    resolve_auxiliary_model,
    resolve_chat_model,
)
from rag_engine.models import (
    ChatTurn,
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RagAnswer,
    RetrievedChunk,
    StageTokenUsage,
    TokenUsage,
    ValidatedFollowup,
)
from rag_engine.prompts import (
    CONVERSATIONAL_PROMPT_FIELDS,
    build_rag_prompt,
    format_knowledge,
    template_has_fields,
)
from rag_engine.qa import (
    PromptGeneration,
    answer_question,
    generate_answer,
    generate_from_prompt,
    stream_answer,
    stream_prompt,
)
from rag_engine.rerank import rerank_chunks
from rag_engine.retrieval import RetrievalResult, retrieve, retrieve_multi
from rag_engine.search import ChromaSearcher, SearchHit, VectorSearcher, open_searcher

__all__ = [
    "CHAT_MODEL_OPTIONS",
    "CONVERSATIONAL_PROMPT_FIELDS",
    "DEFAULT_CHAT_MODEL",
    "ECHO_MODEL",
    "ChatModelInfo",
    "ChatModelUnavailable",
    "ChatTurn",
    "ChromaSearcher",
    "ConversationState",
    "ConversationalAnswer",
    "ConversationalConfig",
    "ConversationalGeneration",
    "ConversationalPrompts",
    "PromptGeneration",
    "QueryPlan",
    "RagAnswer",
    "RagConfig",
    "ResolvedChatModel",
    "RetrievalResult",
    "RetrievedChunk",
    "SearchHit",
    "StageTokenUsage",
    "TokenUsage",
    "ValidatedFollowup",
    "VectorSearcher",
    "answer_question",
    "build_rag_prompt",
    "chat_answer",
    "condense_question",
    "conversational_answer",
    "conversational_answer_stream",
    "format_knowledge",
    "generate_answer",
    "generate_chat_answer",
    "generate_chat_answer_with_usage",
    "generate_from_prompt",
    "get_chat_model_info",
    "open_searcher",
    "resolve_auxiliary_model",
    "resolve_chat_model",
    "rerank_chunks",
    "retrieve",
    "retrieve_multi",
    "stream_answer",
    "stream_chat_answer",
    "stream_prompt",
    "template_has_fields",
]
