"""Step 5 content area: advanced conversational RAG with a glass-box inspector.

The page is thin — it collects controls, calls ``rag_engine.conversational_answer``
(planning → multi-query retrieval → re-ranking → answer → validated follow-ups →
state), then renders each turn as the user's question plus a compact answer bubble, an
optional per-turn inspection expander, and inline link-styled follow-up suggestions. All
persistence and turn rendering reuse the pure ``conversational_rag`` helpers and shared
rag_shared UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
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
    ERROR_REPLY_PROMPT_KEY,
    pick_random_line,
    resolve_app_message,
    resolve_welcome_message,
)
from app_support.conversational_rag.conversational_rag_build_ui import (
    apply_pending_load,
    render_build_launch_button,
    render_build_load_dialog,
)
from app_support.conversational_rag.conversational_rag_form_ui import (
    FOLLOWUP_BUBBLE_KEY_PREFIX,
    INSPECT_BUBBLE_KEY_PREFIX,
    ConversationalControls,
    build_conversational_config,
    render_advanced_controls,
    render_followup_bubble,
    render_turn_inspection,
)
from app_support.conversational_rag.conversational_rag_history import (
    ConversationalFollowupRecord,
    ConversationalPromptTrace,
    ConversationalStageUsage,
    ConversationalTurnRecord,
    append_conversational_rag_record,
    load_conversational_rag_history,
)
from app_support.conversational_rag.conversational_token_ui import (
    render_conversational_token_panel,
)
from app_support.conversational_rag.followup_cache import get_cached_chunks, replace_followups
from app_support.conversational_rag.showcase_conversation_storage import (
    showcase_conversations_hydrated,
    sync_showcase_conversation_ids,
)
from app_support.focus import entered_page, focus_chat_input, scroll_message_into_view
from app_support.i18n import answer_language_name, get_strings, localize_message
from app_support.rag_shared.index_catalog import embedding_model_of
from app_support.rag_shared.rag_ui import RagPageContext
from app_support.rag_shared.resource_cache import (
    cached_aux_resolver,
    cached_chat_resolver,
    cached_retriever,
)
from app_support.rag_shared.result_snapshot import stored_results
from app_support.settings import get_settings
from app_support.shell.constants import _FORM_MAX_WIDTH_PX

_TURNS_KEY = "conversational_rag_turns"
_STATE_KEY = "conversational_rag_state"
_CACHE_KEY = "conversational_rag_followup_cache"
_PENDING_KEY = "conversational_rag_pending"
_CONV_ID_KEY = "conversational_rag_current_id"
_SHOWCASE_CONV_IDS_KEY = "showcase_my_conversation_ids"
# One-shot guard so a showcase opens the visitor's latest conversation only on first load.
_SHOWCASE_INIT_KEY = "showcase_initial_selection_done"
_USER_TURN_KEY_PREFIX = "conv-user-"
_ASSISTANT_TURN_KEY_PREFIX = "conv-assistant-"
_CHAT_INPUT_KEY = "conversational_rag_input"
_CHAT_PANEL_KEY = "conversational_rag_panel"
_SCROLL_REQUESTED_KEY = "conversational_rag_scroll_bottom"
_FOCUS_INPUT_KEY = "conversational_rag_focus_input"
_INPUT_DOCK_KEY = "conversational_rag_input_dock"
# The showcase renders outside the shell, so mirror the shell's content max-width
# (streamlit_app._render_shared_styles) to match Steps 1-5, and set the top padding
# to clear Streamlit's ~60px toolbar so the first row (New conversation + picker) is
# not hidden behind it, while keeping the chrome-less chat near the top.
_SHOWCASE_WIDTH_CSS = (
    "<style>"
    'div[data-testid="stMainBlockContainer"],section.main .block-container'
    f"{{max-width:{_FORM_MAX_WIDTH_PX}px!important;margin-left:auto;margin-right:auto;"
    "padding-top:3.5rem!important}"
    "</style>"
)
# Right-align the user's chat bubbles (messenger style); the assistant stays left.
_CHAT_ALIGN_CSS = (
    "<style>"
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
    "{flex-direction:row-reverse;width:fit-content;max-width:80%;margin-left:auto}"
    # Force the 0.2rem nudge Streamlit only applies to single-line bubbles, so a
    # multi-line question's first line lines up with the avatar like the assistant's.
    f"div[class*='st-key-{_USER_TURN_KEY_PREFIX}'] div[data-testid='stChatMessageContent']"
    "{text-align:right;margin-top:0.2rem}"
    "</style>"
)
# Give the model answer the same grey rounded bubble as the user's, but left-aligned.
# The fill matches Streamlit's own user-bubble colour (its secondary background,
# transparentized), which differs by theme — so it is chosen at render time.
# Scoped to the answer via the conv-assistant- container; the inspection panel
# (rendered outside it) stays unstyled, and the streaming status inside is de-framed
# by _STATUS_BUBBLE_CSS.
_BUBBLE_FILL_DARK = "rgba(38, 39, 48, 0.5)"
_BUBBLE_FILL_LIGHT = "rgba(240, 242, 246, 0.5)"
# The panel/container border colour Streamlit draws per theme; reused for the docked
# chat input's idle border so it matches the conversation panel above it.
_PANEL_BORDER_DARK = "rgba(250, 250, 250, 0.2)"
_PANEL_BORDER_LIGHT = "rgba(49, 51, 63, 0.2)"


def _assistant_bubble_css(fill: str) -> str:
    """Grey rounded bubble for the model answer, matching the user's bubble."""
    return (
        "<style>"
        f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stChatMessage']"
        f"{{width:fit-content;max-width:80%;background-color:{fill};"
        "padding-right:1rem;padding-top:1rem;padding-bottom:1rem}"
        # Match the user bubble's default 0.2rem content nudge so the first answer
        # line lines up with the avatar the same way the user's question does.
        f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stChatMessageContent']"
        "{margin-top:0.2rem}"
        "</style>"
    )


# The live status ("Generating…"/"Finalizing…") streams inside the answer bubble,
# just under the answer text. Strip its expander frame and padding so it reads as a
# plain spinner + label line hugging the answer instead of a boxed rectangle. A small
# negative top margin lifts it so, before any answer text, the spinner centres on the
# avatar instead of sitting below it (the empty answer slot above would push it down) —
# kept gentle so the spinner stays level with the avatar rather than riding above it.
_STATUS_BUBBLE_CSS = (
    "<style>"
    f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stExpander']"
    "{border:0;background:transparent;box-shadow:none;margin-top:-0.25rem}"
    f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stExpander'] details"
    "{border:0;background:transparent}"
    f"div[class*='st-key-{_ASSISTANT_TURN_KEY_PREFIX}'] div[data-testid='stExpander'] summary"
    "{padding:0}"
    "</style>"
)


# The follow-up suggestions render as a compact bubble just under the answer, showing
# the assistant avatar so it reads as a distinct model message matching the answer
# bubble above it. It keeps its OWN rounded bubble (rather than welding into the answer)
# so the two fit-content bubbles' differing widths can't leave an empty stepped notch
# beside it; a small negative top margin keeps it close so it still reads as a
# continuation. The suggestions lay out inline like a sentence (a wrapping row of
# tertiary buttons) styled as blue underlined links.
def _followup_bubble_css(fill: str) -> str:
    """Render the follow-up suggestions as a compact bubble just under the answer."""
    return (
        "<style>"
        f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stChatMessage']"
        f"{{width:fit-content;max-width:80%;background-color:{fill};margin-top:-0.5rem;"
        # Match the answer bubble's padding so both bubbles share the same inner spacing.
        "padding-right:1rem;padding-top:1rem;padding-bottom:1rem}"
        # Align the content's first line with the avatar like the answer bubble, so a
        # lone no-suggestions nudge sits level with the icon instead of centred lower.
        f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stChatMessageContent']"
        "{margin-top:0.2rem}"
        # Tighten the intro line's own bottom margin so the chips sit close under it.
        f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stChatMessageContent'] p"
        "{margin-bottom:0.25rem}"
        # Lay the chips out left-to-right so long, wrapping suggestions read naturally
        # instead of centring on their own row.
        f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stHorizontalBlock']"
        "{flex-wrap:wrap;gap:0.1rem 0.75rem;justify-content:flex-start;margin-top:-0.25rem}"
        f"div[class*='st-key-{FOLLOWUP_BUBBLE_KEY_PREFIX}'] div[data-testid='stButton'] button"
        "{padding:0;min-height:0;border:0;text-decoration:underline;color:#4a9eff;"
        "justify-content:flex-start;text-align:left}"
        "</style>"
    )


# Pull the chat input snug under the scroll panel by dropping the default block gap.
_INPUT_DOCK_CSS = f"<style>.st-key-{_INPUT_DOCK_KEY}{{margin-top:-1rem}}</style>"
# Pull the chat panel up snug under the conversation controls row (New + picker + Build),
# trimming the default block gap so the panel reads as part of that row (mirrors
# _INPUT_DOCK_CSS, which docks the chat input under the panel).
_PANEL_DOCK_CSS = f"<style>.st-key-{_CHAT_PANEL_KEY}{{margin-top:-0.75rem}}</style>"
# Weld the scroll panel to the composer below it: square the panel's bottom corners and
# the chat input's top corners so the history + input read as one continuous surface.
_WELD_CSS = (
    "<style>"
    f".st-key-{_CHAT_PANEL_KEY}{{border-bottom-left-radius:0;border-bottom-right-radius:0}}"
    f".st-key-{_INPUT_DOCK_KEY} [data-testid='stChatInput']>div"
    "{border-top-left-radius:0;border-top-right-radius:0}"
    "</style>"
)
# Trim the default expander top padding when its content leads straight with tabs (the
# Prompt templates editor), so the tab row sits snug under the expander header.
_TABS_EXPANDER_TIGHTEN_CSS = (
    "<style>"
    "[data-testid='stExpanderDetails']"
    ":has(>[data-testid='stVerticalBlock']>[data-testid='stTabs']:first-child)"
    "{padding-top:0.25rem}"
    # The Messages tab nests a second tab row; pull it up so it sits snug under the
    # outer tab row instead of leaving an empty band above the sub-tabs.
    "[data-testid='stExpanderDetails']"
    ":has(>[data-testid='stVerticalBlock']>[data-testid='stTabs']:first-child)"
    " [data-testid='stTabs'] [data-testid='stTabs']{margin-top:-0.75rem}"
    # Hug the "Required placeholders" caption to its text area: lift it under the tab
    # row and drop its own paragraph's default 16px bottom margin so it reads as a
    # tight heading instead of floating between the tabs and the editor.
    "[data-testid='stExpanderDetails']"
    ":has(>[data-testid='stVerticalBlock']>[data-testid='stTabs']:first-child)"
    " [data-testid='stCaptionContainer']{margin-top:-0.5rem}"
    "[data-testid='stExpanderDetails']"
    ":has(>[data-testid='stVerticalBlock']>[data-testid='stTabs']:first-child)"
    " [data-testid='stCaptionContainer'] p{margin:0 0 0.25rem}"
    "</style>"
)
# Consistent rhythm inside each per-turn Inspect panel: a small, even space above the
# first element and below the last of every tab (the section label, or the Answer tab's
# Prompt/Response tabs) and above the nested Prompt/Response tabs wherever they appear —
# trimmed from Streamlit's default 16px slack but not welded shut. The bottom space keeps
# an empty-state note (the State/Diagnostics tabs' "nothing here" caption) off the panel's
# bottom border. The section-label caption's own `<p>` carries a 16px bottom margin that
# its container only half-compensates, leaving a visible gap under the label; zero it (and
# trim list bottoms) so content hugs its label. Scoped to the Inspect containers by key.
_INSPECT_TABS_RHYTHM_CSS = (
    "<style>"
    f"div[class*='st-key-{INSPECT_BUBBLE_KEY_PREFIX}'] [data-testid='stTabs'] [data-testid='stTabs']"
    "{margin-top:-0.25rem}"
    f"div[class*='st-key-{INSPECT_BUBBLE_KEY_PREFIX}'] [data-testid='stTabs'] [role='tabpanel']"
    "{padding-top:0.5rem;padding-bottom:0.5rem}"
    f"div[class*='st-key-{INSPECT_BUBBLE_KEY_PREFIX}'] [data-testid='stTabs']"
    " [data-testid='stCaptionContainer'] p{margin-bottom:0}"
    f"div[class*='st-key-{INSPECT_BUBBLE_KEY_PREFIX}'] [data-testid='stTabs']"
    " [data-testid='stMarkdownContainer'] ul{margin-bottom:0.5rem}"
    "</style>"
)


def _showcase_panel_css(border_color: str, height_px: int) -> str:
    """Make the showcase chat panel a user-resizable scroll box (drag the bottom edge).

    The showcase builds the panel with a plain ``st.container`` (no ``height=``), so
    unlike Step 5's height-locked container the browser's ``resize`` handle can actually
    change — and persist — the height (an inline drag height survives reruns and isn't
    overridden). This CSS recreates the bordered, scrollable look ``st.container(height=)``
    gives, starting at *height_px*. It rounds only the top corners and squares the bottom
    two itself so the panel welds flush to the chat input docked below it (matching Step 5,
    where ``_WELD_CSS`` squares the height-locked container's bottom corners).
    """
    return (
        "<style>"
        f".st-key-{_CHAT_PANEL_KEY}{{"
        # flex:none so this stops being a flex-grow item and its own height applies
        # (otherwise a plain container collapses to min-height); the drag then overrides it.
        f"flex:none;height:{height_px}px;min-height:200px;overflow-y:auto;resize:vertical;"
        f"border:1px solid {border_color};"
        # Round only the top; square the bottom so it welds to the chat input below.
        "border-top-left-radius:0.5rem;border-top-right-radius:0.5rem;"
        "border-bottom-left-radius:0;border-bottom-right-radius:0;padding:1rem}"
        "</style>"
    )


def _idle_input_border_css(border_color: str) -> str:
    """Border the docked chat input on its free sides when unfocused, matching the panel.

    The panel already draws the shared top edge (welded), so only the left, right, and
    bottom are coloured; a focused input keeps Streamlit's accent border.
    """
    return (
        "<style>"
        f".st-key-{_INPUT_DOCK_KEY} [data-testid='stChatInput']>div:not(:focus-within)"
        f"{{border-left-color:{border_color};border-right-color:{border_color};"
        f"border-bottom-color:{border_color}}}"
        "</style>"
    )


def _turn_failed(answer: ConversationalAnswer) -> bool:
    """True when a turn reported errors or produced no answer text — show a natural reply.

    Persisted turns drop their warnings/errors on replay, so a previously failed turn
    reloads with an empty answer and no errors; treating "nothing to show" as a failure
    keeps the friendly reply after a refresh or a conversation switch.
    """
    return bool(answer.errors) or not answer.answer.strip()


def _error_reply(strings, session_root, turn_id: int, overrides=None) -> str:
    """One natural, non-technical reply for a failed turn; varies per turn, editable."""
    return pick_random_line(
        resolve_app_message(
            session_root, ERROR_REPLY_PROMPT_KEY, strings["CONV_ERROR_REPLY_DEFAULT"], overrides
        ),
        turn_id,
    )


def _turn_in_flight(session_state) -> bool:
    """True when a queued question is waiting to stream — used to lock inputs mid-turn."""
    return bool((session_state.get(_PENDING_KEY) or "").strip())


def _inspect_deferred(is_latest: bool, followups_enabled: bool) -> bool:
    """Whether a turn's Inspect panel renders below its follow-ups instead of inline.

    The latest turn defers so its answer↔follow-up bubbles stay welded and the
    full-width panel drops to the turn's bottom. Deferring regardless of streaming
    keeps the panel in one stable position, so a mid-stream re-render can't leave a
    duplicate copy behind while ``st.write_stream`` blocks the run.
    """
    return is_latest and followups_enabled


def render_page(
    context: RagPageContext,
    *,
    showcase_controls: ConversationalControls | None = None,
    show_token_panel: bool = True,
    showcase_prompts: Mapping[str, str] | None = None,
    showcase_slug: str | None = None,
) -> None:
    """Render the conversational RAG page content area.

    In showcase mode (*showcase_controls* set) the tuning controls, build section,
    Output Files, and the page heading are hidden and the frozen controls drive a
    chat-only, read-only page; the conversation picker is filtered to the visitor's
    own conversations. The showcase renders outside the shell, so it mirrors the
    shell's content width here. *show_token_panel* lets the showcase hide the Token
    usage panel unless the launch URL opts in (``?showToken``); Inspect is likewise
    opt-in (``?inspect``) via the frozen controls' ``inspect``, set by the route.
    *showcase_prompts* injects a launched build's frozen prompts (6 model + app
    messages) so the showcase reproduces them without any prompt files on disk.
    *showcase_slug* scopes the visitor's conversation ids persisted in browser
    localStorage so the New-conversation button and picker survive a reload.
    """
    showcase = showcase_controls is not None
    strings = get_strings(st.session_state.get("language", context.default_language))
    if showcase:
        st.html(_SHOWCASE_WIDTH_CSS)
    else:
        apply_pending_load(strings, context.session_root())
    on_entry = entered_page("conversational_rag")
    if not showcase:
        st.subheader(strings["CHAT_SECTION_HEADER"], anchor="conversational-rag-header")
        st.caption(strings["CHAT_SECTION_CAPTION"])
    theme_dark = st.context.theme.type == "dark"
    bubble_fill = _BUBBLE_FILL_DARK if theme_dark else _BUBBLE_FILL_LIGHT
    panel_border = _PANEL_BORDER_DARK if theme_dark else _PANEL_BORDER_LIGHT
    panel_height = get_settings().conv_rag_chat_panel_height_px
    st.html(_CHAT_ALIGN_CSS)
    st.html(_assistant_bubble_css(bubble_fill))
    st.html(_STATUS_BUBBLE_CSS)
    st.html(_followup_bubble_css(bubble_fill))
    st.html(_INPUT_DOCK_CSS)
    st.html(_PANEL_DOCK_CSS)
    st.html(_WELD_CSS)
    st.html(_idle_input_border_css(panel_border))
    st.html(_TABS_EXPANDER_TIGHTEN_CSS)
    st.html(_INSPECT_TABS_RHYTHM_CSS)
    # The showcase builds the panel with a plain st.container (no height=) so the visitor
    # can drag-resize it; inject its scroll-box CSS here (not right before the panel) so
    # no invisible element sits between the controls row and the panel, which would widen
    # the gap _PANEL_DOCK_CSS trims.
    if showcase:
        st.html(_showcase_panel_css(panel_border, panel_height))

    # Peek the queued question (a typed message or a follow-up click) before the
    # controls so every input can be locked while its answer streams — a mid-stream
    # widget change would otherwise interrupt the run and drop the just-streamed turn.
    pending = st.session_state.get(_PENDING_KEY)
    in_flight = _turn_in_flight(st.session_state)

    if showcase:
        controls = showcase_controls
    else:
        controls = render_advanced_controls(
            strings,
            "conversational_rag",
            list(context.list_indexes()),
            context.session_root(),
            disabled=in_flight,
        )
    index = controls.index

    records = load_conversational_rag_history(context.session_root())
    summaries = conversation_summaries(records)
    showcase_hydrated = False
    if showcase:
        showcase_hydrated = _sync_showcase_conversations(showcase_slug, records)
        summaries = _showcase_visible_summaries(summaries)
    _ensure_active_conversation(records, summaries)
    if showcase:
        _ensure_showcase_initial_conversation(records, summaries, hydrated=showcase_hydrated)
        _register_showcase_conversation()
    _render_conversation_controls(
        strings,
        records,
        summaries,
        controls,
        context.session_root(),
        st.session_state.get("language", context.default_language),
        show_build=not showcase,
        disabled=in_flight,
    )

    turns: list[dict] = st.session_state[_TURNS_KEY]
    state: ConversationState = st.session_state[_STATE_KEY]
    cache: dict = st.session_state[_CACHE_KEY]

    question = (pending or "").strip()
    submitting = bool(question and index is not None)
    # A queued question with no usable index can't stream; drop it so it doesn't wedge.
    if pending is not None and not submitting:
        st.session_state.pop(_PENDING_KEY, None)

    default_tab = get_settings().semantic_search_default_tab
    answer: ConversationalAnswer | None = None
    elapsed = 0.0
    config = None
    # Peek the scroll intent before the panel so a submitted turn can scroll to the
    # new question *before* the blocking stream (pinning it to the top as it streams).
    scroll_requested = on_entry or st.session_state.pop(_SCROLL_REQUESTED_KEY, False)
    # The showcase builds the panel without Streamlit's height= so the visitor can drag it
    # taller/shorter (its scroll-box CSS was injected above); Step 5 keeps the fixed height.
    if showcase:
        panel_container = st.container(key=_CHAT_PANEL_KEY)
    else:
        panel_container = st.container(height=panel_height, key=_CHAT_PANEL_KEY)
    with panel_container:
        if not turns and not submitting:
            _render_welcome_bubble(strings, context.session_root(), showcase_prompts)
        for position, turn in enumerate(turns):
            is_latest = position == len(turns) - 1
            # The latest turn's Inspect panel renders below its follow-ups (see the
            # follow-ups branch) so the answer↔follow-up bubbles stay welded and the
            # full-width panel drops to the very bottom of the turn.
            defer_inspect = _inspect_deferred(is_latest, controls.followup_show_count > 0)
            _render_stored_turn(
                strings,
                context.session_root(),
                turn,
                inspect=controls.inspect and not defer_inspect,
                default_tab=default_tab,
                overrides=showcase_prompts,
            )
        # Fixed-position slot for the latest turn's follow-ups and its deferred Inspect
        # panel, so the next turn can wipe them the instant it starts streaming. An
        # emptied st.empty flushes mid-run; an emptied keyed container only clears when
        # the run ends, and st.write_stream blocks the run for the whole answer — which
        # is why the old chips used to linger beside the just-asked question until it
        # finished.
        followup_slot = st.empty()
        if submitting:
            config = build_conversational_config(
                controls,
                context.session_root(),
                language=answer_language_name(
                    st.session_state.get("language", context.default_language)
                ),
                prompt_overrides=showcase_prompts,
            )
            followup_slot.empty()  # wipe the prior turn's follow-ups + Inspect now
            answer, elapsed = _stream_pending_turn(
                strings,
                context.session_root(),
                question,
                len(turns),
                index.run_dir,
                state,
                config,
                _history_from_turns(turns),
                get_cached_chunks(cache, question),
                scroll=scroll_requested,
                overrides=showcase_prompts,
            )
        elif turns and controls.followup_show_count > 0:
            # Suggested follow-ups read as a continuation of the latest answer, so
            # they live inside the scroll panel right beneath it; the Inspect panel
            # then sits below them at the bottom of the turn. Both go in the slot so the
            # next turn's stream can clear them together.
            latest = turns[-1]
            with followup_slot.container():
                clicked = render_followup_bubble(
                    strings,
                    context.session_root(),
                    latest["answer"].follow_ups,
                    latest["turn_id"],
                    overrides=showcase_prompts,
                )
                if controls.inspect:
                    render_turn_inspection(
                        strings,
                        latest["answer"],
                        default_tab=default_tab,
                        turn_id=latest["turn_id"],
                    )
            if clicked:
                st.session_state[_PENDING_KEY] = clicked
                st.session_state[_SCROLL_REQUESTED_KEY] = True
                st.rerun()
        # A submitted turn already scrolled from inside _stream_pending_turn (before
        # its blocking stream). Page entry, a follow-up click, and the post-answer
        # rerun are not streaming, so pin the newest question to the panel top from
        # INSIDE the panel: keeping this 1px scroll helper within the height-capped
        # panel avoids adding a flow element between the panel and the docked input,
        # which was reintroducing the gap above the chat input after a turn.
        newest_user_key = _newest_user_turn_key(turns, submitting)
        if scroll_requested and not submitting and newest_user_key:
            scroll_message_into_view(_CHAT_PANEL_KEY, newest_user_key)

    # Dock the input just under the panel + follow-ups. Wrapping it in a container
    # makes Streamlit render it inline (not viewport-pinned); a typed message queues
    # via _PENDING_KEY and reruns so the next run streams it into the panel above.
    with st.container(key=_INPUT_DOCK_KEY):
        typed = st.chat_input(
            strings["CHAT_INPUT_PLACEHOLDER"],
            disabled=index is None or in_flight,
            key=_CHAT_INPUT_KEY,
        )
    if typed and index is not None:
        st.session_state[_PENDING_KEY] = typed.strip()
        st.session_state[_SCROLL_REQUESTED_KEY] = True
        st.rerun()

    if show_token_panel:
        render_conversational_token_panel(strings, records)
    if not showcase:
        context.render_downloads()
        render_build_load_dialog(strings, context.session_root())

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
        # Consume the queued question only after the turn is safely committed, so an
        # interrupted stream keeps it and re-streams instead of losing the turn.
        st.session_state.pop(_PENDING_KEY, None)
        st.session_state[_SCROLL_REQUESTED_KEY] = True
        st.session_state[_FOCUS_INPUT_KEY] = True
        st.rerun()


def _render_welcome_bubble(strings, session_root, overrides=None) -> None:
    """Show the editable assistant greeting at the start of a fresh conversation."""
    greeting = pick_random_line(
        resolve_welcome_message(session_root, strings["CHAT_WELCOME_DEFAULT"], overrides),
        st.session_state.get(_CONV_ID_KEY, ""),
    )
    with st.chat_message("assistant"):
        st.write(greeting)


def _render_stored_turn(
    strings,
    session_root,
    turn: dict,
    *,
    inspect: bool,
    default_tab: str,
    overrides: Mapping[str, str] | None = None,
) -> None:
    """Render one persisted turn: the user bubble and the assistant's answer."""
    _render_user_message(turn["question"], turn["turn_id"])
    answer: ConversationalAnswer = turn["answer"]
    key = f"{_ASSISTANT_TURN_KEY_PREFIX}{turn['turn_id']}"
    with st.container(key=key), st.chat_message("assistant"):
        if _turn_failed(answer):
            st.write(_error_reply(strings, session_root, turn["turn_id"], overrides))
        else:
            st.write(answer.answer)
    if inspect:
        render_turn_inspection(strings, answer, default_tab=default_tab, turn_id=turn["turn_id"])


def _stream_pending_turn(
    strings,
    session_root,
    question,
    turn_id,
    run_dir,
    state,
    config,
    history,
    cached,
    *,
    scroll=False,
    overrides: Mapping[str, str] | None = None,
):
    """Stream the pending turn's answer into the chat panel; return (answer, seconds).

    The grounded answer streams token-by-token inside the answer bubble; a live
    ``st.status`` under it (same bubble) narrates the plan/retrieve/re-rank/state
    stages and collapses when the turn completes. When *scroll* is set, the new
    question is pinned to the panel top before the blocking stream starts, so it
    stays visible as the answer streams in — instead of only scrolling once the
    whole answer has finished.
    """
    _render_user_message(question, turn_id)
    key = f"{_ASSISTANT_TURN_KEY_PREFIX}{turn_id}"
    with st.container(key=key), st.chat_message("assistant"):
        answer_area = st.container()
        # The live status sits inside the answer bubble, just under the streamed text.
        status = st.status(strings["RAG_GENERATING"])
    # Scroll only after the answer bubble is in the DOM, so the 1px scroll-helper
    # iframe lands below it instead of between the question and the answer — where it
    # otherwise added a visible gap during the blocking stream that vanished on commit.
    if scroll:
        scroll_message_into_view(_CHAT_PANEL_KEY, f"{_USER_TURN_KEY_PREFIX}{turn_id}")

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
        if _turn_failed(answer):
            st.write(_error_reply(strings, session_root, turn_id, overrides))
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


def _showcase_visible_summaries(
    summaries: list[ConversationSummary],
) -> list[ConversationSummary]:
    """Filter the picker to the conversations this showcase visitor started."""
    mine = st.session_state.get(_SHOWCASE_CONV_IDS_KEY, set())
    return [summary for summary in summaries if summary.conversation_id in mine]


def _sync_showcase_conversations(slug: str | None, records: list[ConversationalTurnRecord]) -> bool:
    """Mirror the visitor's conversation ids to/from browser storage (per showcase link).

    Hydrates the private picker set from localStorage so a visitor's own conversations
    survive a reload, like session ids do. A conversation is persisted only once it has
    a saved turn, so empty, abandoned ones never accumulate. Returns whether the browser
    bridge has hydrated yet, so the caller can defer the initial latest-conversation pick.
    """
    if not slug:
        return False
    mine = st.session_state.setdefault(_SHOWCASE_CONV_IDS_KEY, set())
    active = str(st.session_state.get(_CONV_ID_KEY, ""))
    saved_ids = {record.conversation_id for record in records if record.conversation_id}
    pending = [active] if active in saved_ids else []
    stored = sync_showcase_conversation_ids(slug, pending)
    st.session_state[_SHOWCASE_CONV_IDS_KEY] = set(stored) | mine
    return showcase_conversations_hydrated(slug)


def _ensure_showcase_initial_conversation(
    records: list[ConversationalTurnRecord],
    summaries: list[ConversationSummary],
    *,
    hydrated: bool,
) -> None:
    """On a showcase's first load, open the visitor's most recent conversation.

    Runs once per showcase session, and only after the browser has hydrated the visitor's
    saved-conversation list (localStorage). If they have saved conversations and are still
    on the fresh empty one, switch to the latest so its history shows; a brand-new visitor
    (no saved conversations) keeps the empty one. The one-shot guard means a later
    "New conversation" click is never overridden.
    """
    if st.session_state.get(_SHOWCASE_INIT_KEY) or not hydrated:
        return
    st.session_state[_SHOWCASE_INIT_KEY] = True
    if summaries and not st.session_state.get(_TURNS_KEY):
        _activate_conversation(summaries[0].conversation_id, records)


def _register_showcase_conversation() -> None:
    """Record the active conversation as the visitor's own (keeps the picker private)."""
    mine = st.session_state.setdefault(_SHOWCASE_CONV_IDS_KEY, set())
    current = st.session_state.get(_CONV_ID_KEY)
    if current:
        mine.add(current)


def _render_conversation_controls(
    strings,
    records: list[ConversationalTurnRecord],
    summaries: list[ConversationSummary],
    controls: ConversationalControls,
    session_root: Path,
    language: str,
    *,
    show_build: bool = True,
    disabled: bool = False,
) -> None:
    """Render the New-conversation button, the conversation picker, and Build & launch."""
    current_id = st.session_state[_CONV_ID_KEY]
    option_ids = [summary.conversation_id for summary in summaries]
    if current_id not in option_ids:
        option_ids = [current_id, *option_ids]  # the unsaved, in-progress conversation
    titles = {summary.conversation_id: summary.title for summary in summaries}

    def _label(conversation_id: str) -> str:
        title = titles.get(conversation_id) or strings["CHAT_NEW_CONVERSATION"]
        return f"{conversation_id} · {title}" if conversation_id else title

    with st.container(horizontal=True, vertical_alignment="center", gap="xxsmall"):
        if st.button(
            "",
            width=_ICON_BUTTON_WIDTH_PX,
            icon=":material/add:",
            help=strings["CHAT_NEW_CONVERSATION"],
            key="conversational_rag_new",
            disabled=disabled,
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
            disabled=disabled,
        )
        if show_build:
            render_build_launch_button(strings, controls, session_root, language, disabled=disabled)
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
    embedding_model = embedding_model_of(index)
    record = ConversationalTurnRecord(
        timestamp_utc=datetime.now(UTC).isoformat(timespec="milliseconds"),
        index_folder=index.vector_folder,
        index_run=index.run_name,
        embedding_model=embedding_model,
        llm_model=answer.model_used or config.rag.llm_model,
        aux_model=answer.aux_model_used or "",
        reranker=answer.reranker_used or config.reranker,
        raw_question=question,
        sub_questions=tuple(answer.plan.sub_questions),
        proposed_subquestion_count=answer.plan.proposed_count,
        answer=answer.answer,
        plan_seconds=timings.get("plan", 0.0),
        retrieve_seconds=timings.get("retrieve", 0.0),
        rerank_seconds=timings.get("rerank", 0.0),
        answer_seconds=timings.get("answer", 0.0),
        followups_seconds=timings.get("followups", 0.0),
        state_seconds=timings.get("state", 0.0),
        total_seconds=elapsed,
        results=stored_results(answer.sources),
        overflow_results=stored_results(answer.overflow_sources),
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
        prompt_traces=tuple(
            ConversationalPromptTrace(
                process=trace.process,
                prompt=trace.prompt,
                response=trace.response,
            )
            for trace in answer.prompt_traces
        ),
        follow_ups_shown=tuple(item.question for item in answer.follow_ups),
        follow_ups_dropped=tuple(item.question for item in answer.dropped_followups),
        follow_ups_evaluated=tuple(
            ConversationalFollowupRecord(
                question=item.question,
                score=item.score,
                verdict=item.verdict,
                checked_by_llm=item.checked_by_llm,
            )
            for item in (*answer.follow_ups, *answer.dropped_followups)
        ),
        conversation_id=conversation_id,
        transaction_id=new_transaction_id(),
        state_summary=answer.state.summary,
    )
    append_conversational_rag_record(session_root, record)
