"""Step 5 content area: advanced conversational RAG with a glass-box inspector.

The page is thin — it collects controls, calls ``rag_engine.conversational_answer``
(planning → multi-query retrieval → re-ranking → answer → validated follow-ups →
state), then renders each turn with a metadata strip, an optional per-turn
inspection expander, and clickable follow-up buttons. All persistence and turn
rendering reuse the pure ``conversational_rag`` helpers and shared rag_shared UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

import streamlit as st
from artifact_store import LibraryMessage
from rag_engine import ChatTurn, ConversationalAnswer, ConversationState, conversational_answer

from app_support.app_runtime import _ICON_BUTTON_WIDTH_PX
from app_support.conversational_rag.conversation_manager import (
    ConversationSummary,
    conversation_summaries,
    conversation_turns,
    new_conversation_id,
    new_transaction_id,
)
from app_support.conversational_rag.conversational_rag_form_ui import (
    build_conversational_config,
    render_advanced_controls,
    render_followup_buttons,
    render_turn_inspection,
)
from app_support.conversational_rag.conversational_rag_history import (
    ConversationalStageUsage,
    ConversationalTurnRecord,
    append_conversational_rag_record,
    load_conversational_rag_history,
)
from app_support.conversational_rag.conversational_token_ui import (
    render_conversational_token_panel,
)
from app_support.conversational_rag.followup_cache import get_cached_chunks, replace_followups
from app_support.i18n import get_strings, localize_message
from app_support.rag_shared.rag_ui import RagPageContext, render_messages
from app_support.rag_shared.result_snapshot import stored_results
from app_support.settings import get_settings

_TURNS_KEY = "conversational_rag_turns"
_STATE_KEY = "conversational_rag_state"
_CACHE_KEY = "conversational_rag_followup_cache"
_PENDING_KEY = "conversational_rag_pending"
_CONV_ID_KEY = "conversational_rag_current_id"
_USER_TURN_KEY_PREFIX = "conv-user-"
# Right-align the user's chat bubbles (messenger style); the assistant stays left.
_CHAT_ALIGN_CSS = (
    "<style>"
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
    "{flex-direction:row-reverse;width:fit-content;max-width:80%;margin-left:auto}"
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessageContent']"
    "{text-align:right}"
    "</style>"
)


def render_page(context: RagPageContext) -> None:
    """Render the conversational RAG page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    st.subheader(strings["CHAT_SECTION_HEADER"], anchor="conversational-rag-header")
    st.caption(strings["CHAT_SECTION_CAPTION"])
    st.html(_CHAT_ALIGN_CSS)

    controls = render_advanced_controls(
        strings, "conversational_rag", list(context.list_indexes()), context.session_root()
    )
    index = controls.index

    records = load_conversational_rag_history(context.session_root())
    summaries = conversation_summaries(records)
    _ensure_active_conversation(records, summaries)
    _render_conversation_controls(strings, records, summaries)

    turns: list[dict] = st.session_state[_TURNS_KEY]
    state: ConversationState = st.session_state[_STATE_KEY]
    cache: dict = st.session_state[_CACHE_KEY]

    if not turns:
        st.info(strings["CHAT_EMPTY_HINT"])

    default_tab = get_settings().semantic_search_default_tab
    for turn in turns:
        _render_user_message(turn["question"], turn["turn_id"])
        with st.chat_message("assistant"):
            answer: ConversationalAnswer = turn["answer"]
            render_messages(strings, answer.warnings, answer.errors)
            if answer.answer:
                st.write(answer.answer)
            if controls.inspect:
                render_turn_inspection(strings, answer, default_tab=default_tab)

    if turns:
        latest = turns[-1]
        clicked = render_followup_buttons(strings, latest["answer"].follow_ups, latest["turn_id"])
        if clicked:
            st.session_state[_PENDING_KEY] = clicked
            st.rerun()

    render_conversational_token_panel(strings, records)
    context.render_downloads()

    pending = st.session_state.pop(_PENDING_KEY, None)
    typed = st.chat_input(strings["CHAT_INPUT_PLACEHOLDER"], disabled=index is None)
    question = (pending or typed or "").strip()
    if not (question and index is not None):
        return

    config = build_conversational_config(controls, context.session_root())
    history = _history_from_turns(turns)
    cached = get_cached_chunks(cache, question)

    _render_user_message(question, len(turns))
    with st.chat_message("assistant"):
        status = st.status(strings["RAG_GENERATING"])

        def _report_progress(message: LibraryMessage) -> None:
            status.update(label=localize_message(strings, message.as_dict()))

        start = perf_counter()
        answer = conversational_answer(
            index.run_dir,
            question,
            state,
            config,
            history=history,
            cached_chunks=cached,
            progress_callback=_report_progress,
        )
        elapsed = perf_counter() - start

    turns.append({"question": question, "answer": answer, "turn_id": len(turns)})
    st.session_state[_STATE_KEY] = answer.state
    replace_followups(cache, answer.follow_ups)
    _append_history(
        context.session_root(),
        st.session_state[_CONV_ID_KEY],
        index,
        config,
        question,
        answer,
        elapsed,
    )
    st.rerun()


def _ensure_active_conversation(
    records: list[ConversationalTurnRecord], summaries: list[ConversationSummary]
) -> None:
    """Pick the active conversation on first load or after a session switch.

    Defaults to the most recently active saved conversation (rehydrated from
    disk) or a fresh empty one, materializing its turns/state into session state.
    A later rerun keeps the existing id, so live full-fidelity turns are never
    overwritten by their display-adequate disk replay. The shell clears
    ``_CONV_ID_KEY`` when switching sessions, which re-triggers this.
    """
    if _CONV_ID_KEY in st.session_state:
        return
    if summaries:
        _activate_conversation(summaries[0].conversation_id, records)
    else:
        _start_new_conversation()


def _activate_conversation(conversation_id: str, records: list[ConversationalTurnRecord]) -> None:
    """Load a saved conversation's turns (display-adequate) into session state."""
    turns = conversation_turns(records, conversation_id)
    st.session_state[_CONV_ID_KEY] = conversation_id
    st.session_state[_TURNS_KEY] = turns
    st.session_state[_STATE_KEY] = turns[-1]["answer"].state if turns else ConversationState()
    st.session_state[_CACHE_KEY] = {}
    st.session_state.pop(_PENDING_KEY, None)


def _start_new_conversation() -> None:
    """Begin a fresh, empty conversation with a new id."""
    st.session_state[_CONV_ID_KEY] = new_conversation_id()
    st.session_state[_TURNS_KEY] = []
    st.session_state[_STATE_KEY] = ConversationState()
    st.session_state[_CACHE_KEY] = {}
    st.session_state.pop(_PENDING_KEY, None)


def _render_conversation_controls(
    strings,
    records: list[ConversationalTurnRecord],
    summaries: list[ConversationSummary],
) -> None:
    """Render the New-conversation button and a picker over saved conversations."""
    current_id = st.session_state[_CONV_ID_KEY]
    option_ids = [summary.conversation_id for summary in summaries]
    if current_id not in option_ids:
        option_ids = [current_id, *option_ids]  # the unsaved, in-progress conversation
    titles = {summary.conversation_id: summary.title for summary in summaries}

    def _label(conversation_id: str) -> str:
        title = titles.get(conversation_id) or strings["CHAT_NEW_CONVERSATION"]
        return f"{conversation_id} · {title}" if conversation_id else title

    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        if st.button(
            "",
            width=_ICON_BUTTON_WIDTH_PX,
            icon=":material/add:",
            help=strings["CHAT_NEW_CONVERSATION"],
            key="conversational_rag_new",
        ):
            _start_new_conversation()
            st.rerun()
        selected = st.selectbox(
            strings["CHAT_CONVERSATION_SELECT"],
            options=option_ids,
            index=option_ids.index(current_id),
            format_func=_label,
            width=360,
        )
    if selected != current_id:
        _activate_conversation(selected, records)
        st.rerun()


def _render_user_message(question: str, turn_id: int) -> None:
    """Render the user's turn as a right-aligned (messenger-style) chat bubble."""
    with st.container(key=f"{_USER_TURN_KEY_PREFIX}{turn_id}"), st.chat_message("user"):
        st.write(question)


def _history_from_turns(turns: list[dict]) -> list[ChatTurn]:
    history: list[ChatTurn] = []
    for turn in turns:
        history.append(ChatTurn(role="user", content=turn["question"]))
        history.append(ChatTurn(role="assistant", content=turn["answer"].answer))
    return history


def _append_history(
    session_root,
    conversation_id: str,
    index,
    config,
    question: str,
    answer: ConversationalAnswer,
    elapsed: float,
) -> None:
    timings = answer.timings
    manifest = index.manifest
    embedding_model = (
        getattr(manifest, "embedding_model_used", "")
        or getattr(manifest, "embedding_model_requested", "")
        or ""
    )
    record = ConversationalTurnRecord(
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        index_folder=index.vector_folder,
        index_run=index.run_name,
        embedding_model=embedding_model,
        llm_model=answer.model_used or config.rag.llm_model,
        aux_model=answer.aux_model_used or "",
        reranker=answer.reranker_used or config.reranker,
        raw_question=question,
        sub_questions=tuple(answer.plan.sub_questions),
        answer=answer.answer,
        plan_seconds=timings.get("plan", 0.0),
        retrieve_seconds=timings.get("retrieve", 0.0),
        rerank_seconds=timings.get("rerank", 0.0),
        answer_seconds=timings.get("answer", 0.0),
        followups_seconds=timings.get("followups", 0.0),
        state_seconds=timings.get("state", 0.0),
        total_seconds=elapsed,
        results=stored_results(answer.sources),
        token_usage=tuple(
            ConversationalStageUsage(
                process=stage.process,
                model=stage.model_id,
                input_tokens=stage.usage.input_tokens,
                output_tokens=stage.usage.output_tokens,
                total_tokens=stage.usage.total_tokens,
            )
            for stage in answer.token_usage
        ),
        follow_ups_shown=tuple(item.question for item in answer.follow_ups),
        conversation_id=conversation_id,
        transaction_id=new_transaction_id(),
        state_summary=answer.state.summary,
    )
    append_conversational_rag_record(session_root, record)
