"""Step 5 content area: advanced conversational RAG with a glass-box inspector.

The page is thin — it collects controls, calls ``rag_engine.conversational_answer``
(planning → multi-query retrieval → re-ranking → answer → validated follow-ups →
state), then renders each turn as the user's question plus a compact answer bubble, an
optional per-turn inspection expander, and inline link-styled follow-up suggestions. All
persistence and turn rendering reuse the pure ``conversational_rag`` helpers and shared
rag_shared UI.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter

import streamlit as st
from artifact_store import LibraryMessage
from rag_engine import (
    ChatTurn,
    ConversationalAnswer,
    ConversationState,
    conversational_answer_stream,
)

from app_support.app_runtime import _ICON_BUTTON_WIDTH_PX
from app_support.conversational_rag.conversation_manager import (
    ConversationSummary,
    asked_questions_from_records,
    conversation_summaries,
    conversation_turns,
    new_conversation_id,
    new_transaction_id,
    trim_old_turn_payloads,
)
from app_support.conversational_rag.conversational_prompts import (
    pick_random_line,
    resolve_welcome_message,
)
from app_support.conversational_rag.conversational_rag_form_ui import (
    FOLLOWUP_BUBBLE_KEY_PREFIX,
    build_conversational_config,
    render_advanced_controls,
    render_followup_bubble,
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
from app_support.focus import entered_page, focus_chat_input, scroll_message_into_view
from app_support.i18n import answer_language_name, get_strings, localize_message
from app_support.rag_shared.rag_ui import RagPageContext, render_messages
from app_support.rag_shared.resource_cache import (
    cached_aux_resolver,
    cached_chat_resolver,
    cached_retriever,
)
from app_support.rag_shared.result_snapshot import stored_results
from app_support.settings import get_settings

_TURNS_KEY = "conversational_rag_turns"
_STATE_KEY = "conversational_rag_state"
_CACHE_KEY = "conversational_rag_followup_cache"
_PENDING_KEY = "conversational_rag_pending"
_CONV_ID_KEY = "conversational_rag_current_id"
_USER_TURN_KEY_PREFIX = "conv-user-"
_ASSISTANT_TURN_KEY_PREFIX = "conv-assistant-"
_STATUS_TURN_KEY_PREFIX = "conv-status-"
_CHAT_INPUT_KEY = "conversational_rag_input"
_CHAT_PANEL_KEY = "conversational_rag_panel"
_SCROLL_REQUESTED_KEY = "conversational_rag_scroll_bottom"
_FOCUS_INPUT_KEY = "conversational_rag_focus_input"
_INPUT_DOCK_KEY = "conversational_rag_input_dock"
# Fixed-height scrollable chat panel so the conversation reads like a messenger
# thread; follow-ups, token usage, and Output Files sit below it.
_CHAT_PANEL_HEIGHT_PX = 520
# Right-align the user's chat bubbles (messenger style); the assistant stays left.
_CHAT_ALIGN_CSS = (
    "<style>"
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
    "{flex-direction:row-reverse;width:fit-content;max-width:80%;margin-left:auto}"
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessageContent']"
    "{text-align:right}"
    "</style>"
)
# Give the model answer the same grey rounded bubble as the user's, but left-aligned.
# The fill matches Streamlit's own user-bubble colour (its secondary background,
# transparentized), which differs by theme — so it is chosen at render time.
# Scoped to the answer via the conv-assistant- container, so the streaming status
# and the inspection panel (both rendered outside it) stay unstyled.
_BUBBLE_FILL_DARK = "rgba(38, 39, 48, 0.5)"
_BUBBLE_FILL_LIGHT = "rgba(240, 242, 246, 0.5)"


def _assistant_bubble_css(fill: str) -> str:
    """Grey rounded bubble for the model answer, matching the user's bubble."""
    return (
        "<style>"
        f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
        f"{{width:fit-content;max-width:80%;background-color:{fill};"
        "padding-right:1rem;padding-bottom:0.5rem}"
        "</style>"
    )


# The streaming status ("Generating…"/"Finalizing…") renders as a hidden-avatar
# assistant message just under the answer, so its text lines up with the answer text.
# Strip the expander frame and vertical padding so it hugs the answer instead of
# boxing itself in a rounded rectangle.
_STATUS_BUBBLE_CSS = (
    "<style>"
    f"div[class*='st-key-{_STATUS_TURN_KEY_PREFIX}'] [data-testid^='stChatMessageAvatar']"
    "{visibility:hidden}"
    f"div[class*='st-key-{_STATUS_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
    "{padding-top:0;padding-bottom:0}"
    f"div[class*='st-key-{_STATUS_TURN_KEY_PREFIX}'] div[data-testid='stExpander']"
    "{border:0;background:transparent;box-shadow:none}"
    f"div[class*='st-key-{_STATUS_TURN_KEY_PREFIX}'] div[data-testid='stExpander'] details"
    "{border:0;background:transparent}"
    f"div[class*='st-key-{_STATUS_TURN_KEY_PREFIX}'] div[data-testid='stExpander'] summary"
    "{padding:0}"
    "</style>"
)
# The follow-up suggestions render as a continuation bubble right under the answer.
# The avatar is kept but hidden (visibility, not display) so the suggestions line
# up with the answer text; they lay out inline like a sentence (a wrapping row of
# tertiary buttons) and are styled as blue underlined links.
_FOLLOWUP_BUBBLE_CSS = (
    "<style>"
    f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] [data-testid^='stChatMessageAvatar']"
    "{visibility:hidden}"
    f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stChatMessage']"
    "{padding-top:0}"
    f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stHorizontalBlock']"
    "{flex-wrap:wrap;gap:0.1rem 0.75rem}"
    f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stButton'] button"
    "{padding:0;min-height:0;border:0;text-decoration:underline;color:#4a9eff}"
    "</style>"
)
# Pull the chat input snug under the scroll panel by dropping the default block gap.
_INPUT_DOCK_CSS = f"<style>.st-key-{_INPUT_DOCK_KEY}{{margin-top:-1rem}}</style>"


def render_page(context: RagPageContext) -> None:
    """Render the conversational RAG page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    on_entry = entered_page("conversational_rag")
    st.subheader(strings["CHAT_SECTION_HEADER"], anchor="conversational-rag-header")
    st.caption(strings["CHAT_SECTION_CAPTION"])
    st.html(_CHAT_ALIGN_CSS)
    bubble_fill = _BUBBLE_FILL_DARK if st.context.theme.type == "dark" else _BUBBLE_FILL_LIGHT
    st.html(_assistant_bubble_css(bubble_fill))
    st.html(_STATUS_BUBBLE_CSS)
    st.html(_FOLLOWUP_BUBBLE_CSS)
    st.html(_INPUT_DOCK_CSS)

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

    # The chat input renders inline under the panel + follow-ups (see below), so a
    # typed message arrives via _PENDING_KEY + a rerun (like a follow-up click). This
    # run only needs the pending question so the panel can stream its answer in place.
    pending = st.session_state.pop(_PENDING_KEY, None)
    question = (pending or "").strip()
    submitting = bool(question and index is not None)

    default_tab = get_settings().semantic_search_default_tab
    answer: ConversationalAnswer | None = None
    elapsed = 0.0
    config = None
    # Peek the scroll intent before the panel so a submitted turn can scroll to the
    # new question *before* the blocking stream (pinning it to the top as it streams).
    scroll_requested = on_entry or st.session_state.pop(_SCROLL_REQUESTED_KEY, False)
    with st.container(height=_CHAT_PANEL_HEIGHT_PX, key=_CHAT_PANEL_KEY):
        if not turns and not submitting:
            _render_welcome_bubble(strings, context.session_root())
        for turn in turns:
            _render_stored_turn(strings, turn, inspect=controls.inspect, default_tab=default_tab)
        if submitting:
            config = build_conversational_config(
                controls,
                context.session_root(),
                language=answer_language_name(
                    st.session_state.get("language", context.default_language)
                ),
            )
            # Clear the previous turn's follow-up chips before streaming. Streamlit
            # removes stale elements only when a script run ends, but st.write_stream
            # blocks the run for the whole answer — without this, the old chips linger
            # beside the just-asked question until the answer finishes.
            if turns:
                st.container(key=f"{FOLLOWUP_BUBBLE_KEY_PREFIX}{turns[-1]['turn_id']}")
            answer, elapsed = _stream_pending_turn(
                strings,
                question,
                len(turns),
                index.run_dir,
                state,
                config,
                _history_from_turns(turns),
                get_cached_chunks(cache, question),
                scroll=scroll_requested,
            )
        elif turns and controls.followups:
            # Suggested follow-ups read as a continuation of the latest answer, so
            # they live inside the scroll panel right beneath it.
            latest = turns[-1]
            clicked = render_followup_bubble(
                strings, context.session_root(), latest["answer"].follow_ups, latest["turn_id"]
            )
            if clicked:
                st.session_state[_PENDING_KEY] = clicked
                st.session_state[_SCROLL_REQUESTED_KEY] = True
                st.rerun()

    # A submitted turn already scrolled from inside _stream_pending_turn (before its
    # blocking stream). Page entry, a follow-up click, and the post-answer rerun are
    # not streaming, so they pin the newest question to the panel top here.
    newest_user_key = _newest_user_turn_key(turns, submitting)
    if scroll_requested and not submitting and newest_user_key:
        scroll_message_into_view(_CHAT_PANEL_KEY, newest_user_key)

    # Dock the input just under the panel + follow-ups. Wrapping it in a container
    # makes Streamlit render it inline (not viewport-pinned); a typed message queues
    # via _PENDING_KEY and reruns so the next run streams it into the panel above.
    with st.container(key=_INPUT_DOCK_KEY):
        typed = st.chat_input(
            strings["CHAT_INPUT_PLACEHOLDER"], disabled=index is None, key=_CHAT_INPUT_KEY
        )
    if typed and index is not None:
        st.session_state[_PENDING_KEY] = typed.strip()
        st.session_state[_SCROLL_REQUESTED_KEY] = True
        st.rerun()

    render_conversational_token_panel(strings, records)
    context.render_downloads()

    if on_entry or st.session_state.pop(_FOCUS_INPUT_KEY, False):
        focus_chat_input()

    if submitting and answer is not None:
        turns.append({"question": question, "answer": answer, "turn_id": len(turns)})
        trim_old_turn_payloads(turns, get_settings().conv_rag_max_live_turns)
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
        st.session_state[_SCROLL_REQUESTED_KEY] = True
        st.session_state[_FOCUS_INPUT_KEY] = True
        st.rerun()


def _render_welcome_bubble(strings, session_root) -> None:
    """Show the editable assistant greeting at the start of a fresh conversation."""
    greeting = pick_random_line(
        resolve_welcome_message(session_root, strings["CHAT_WELCOME_DEFAULT"]),
        st.session_state.get(_CONV_ID_KEY, ""),
    )
    with st.chat_message("assistant"):
        st.write(greeting)


def _render_stored_turn(strings, turn: dict, *, inspect: bool, default_tab: str) -> None:
    """Render one persisted turn: the user bubble and the assistant's answer."""
    _render_user_message(turn["question"], turn["turn_id"])
    answer: ConversationalAnswer = turn["answer"]
    key = f"{_ASSISTANT_TURN_KEY_PREFIX}{turn['turn_id']}"
    with st.container(key=key), st.chat_message("assistant"):
        render_messages(strings, answer.warnings, answer.errors)
        if answer.answer:
            st.write(answer.answer)
    if inspect:
        render_turn_inspection(strings, answer, default_tab=default_tab)


def _stream_pending_turn(
    strings, question, turn_id, run_dir, state, config, history, cached, *, scroll=False
):
    """Stream the pending turn's answer into the chat panel; return (answer, seconds).

    The grounded answer streams token-by-token at the top; a live ``st.status``
    footer below it narrates the plan/retrieve/re-rank/state stages and collapses
    when the turn completes. When *scroll* is set, the new question is pinned to the
    panel top before the blocking stream starts, so it stays visible as the answer
    streams in — instead of only scrolling once the whole answer has finished.
    """
    _render_user_message(question, turn_id)
    if scroll:
        scroll_message_into_view(_CHAT_PANEL_KEY, f"{_USER_TURN_KEY_PREFIX}{turn_id}")
    key = f"{_ASSISTANT_TURN_KEY_PREFIX}{turn_id}"
    with st.container(key=key), st.chat_message("assistant"):
        answer_area = st.container()
    with st.container(key=f"{_STATUS_TURN_KEY_PREFIX}{turn_id}"), st.chat_message("assistant"):
        status = st.status(strings["RAG_GENERATING"])

    def _report_progress(message: LibraryMessage) -> None:
        status.update(label=localize_message(strings, message.as_dict()))

    start = perf_counter()
    generation = conversational_answer_stream(
        run_dir,
        question,
        state,
        config,
        history=history,
        cached_chunks=cached,
        progress_callback=_report_progress,
        retriever=cached_retriever,
        chat_resolver=cached_chat_resolver,
        aux_resolver=cached_aux_resolver,
    )
    with answer_area:
        st.write_stream(generation)
        elapsed = perf_counter() - start
        answer = generation.answer or ConversationalAnswer(answer="", state=state)
        render_messages(strings, answer.warnings, answer.errors)
    status.update(state="complete")
    return answer, elapsed


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
    trim_old_turn_payloads(turns, get_settings().conv_rag_max_live_turns)
    base_state = turns[-1]["answer"].state if turns else ConversationState()
    st.session_state[_CONV_ID_KEY] = conversation_id
    st.session_state[_TURNS_KEY] = turns
    st.session_state[_STATE_KEY] = replace(
        base_state, asked_questions=asked_questions_from_records(records, conversation_id)
    )
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

    with st.container(horizontal=True, vertical_alignment="center", gap=None):
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
            width="stretch",
            label_visibility="collapsed",
        )
    if selected != current_id:
        _activate_conversation(selected, records)
        st.rerun()


def _render_user_message(question: str, turn_id: int) -> None:
    """Render the user's turn as a right-aligned (messenger-style) chat bubble."""
    with st.container(key=f"{_USER_TURN_KEY_PREFIX}{turn_id}"), st.chat_message("user"):
        st.write(question)


def _newest_user_turn_key(turns: list[dict], submitting: bool) -> str | None:
    """Container key of the most recent user bubble to pin to the top of the panel.

    While streaming, the pending turn's bubble uses ``turn_id == len(turns)``;
    otherwise the latest stored turn's own ``turn_id`` is used. ``None`` when there
    is nothing to scroll to (a fresh, empty conversation).
    """
    if submitting:
        return f"{_USER_TURN_KEY_PREFIX}{len(turns)}"
    if turns:
        return f"{_USER_TURN_KEY_PREFIX}{turns[-1]['turn_id']}"
    return None


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
