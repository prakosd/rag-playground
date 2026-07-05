"""Step 4 content area for Simple RAG Q&A.

Two stages: **Generate prompt** runs semantic search and assembles an editable,
fully-visible RAG prompt from the retrieved knowledge; **Send** streams the
selected language model's answer and records token usage + latency. Per-session
prompt history (with replay) and a page-top token summary round it out. The heavy
lifting lives in ``rag_engine`` (prompt builder, streaming) and the app helpers
(``qa_history`` / ``qa_form_ui``); this module only wires widgets to them.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from rag_engine import (
    RagConfig,
    build_rag_prompt,
    messages,
    resolve_chat_model,
    retrieve,
    stream_prompt,
)
from rag_engine.models import TokenUsage

from crawl4md_streamlit.focus import focus_widget
from crawl4md_streamlit.i18n import Strings, get_strings
from crawl4md_streamlit.index_catalog import IndexRef
from crawl4md_streamlit.llm_form_ui import chat_model_choices, chat_model_label
from crawl4md_streamlit.qa_form_ui import token_totals, tone_choices
from crawl4md_streamlit.qa_history import QaRecord, append_qa_record, load_qa_history
from crawl4md_streamlit.rag_ui import (
    RagPageContext,
    find_index,
    index_option_label,
    kv_grid_html,
    local_time_label,
    render_index_metadata,
    render_messages,
    select_index,
)
from crawl4md_streamlit.settings import get_settings

_settings = get_settings()
_DEFAULT_TOP_RESULTS = _settings.rag_qa_top_results
_MAX_TOP_RESULTS = 20
_PROMPT_FIELD_HEIGHT = 260
_PANEL_INDEX_COLUMN_WIDTHS = (0.68, 0.32)

# Widget keys; a history replay pre-fills these before the widgets render.
_INDEX_KEY = "rag_qa_index"
_TOP_RESULTS_KEY = "rag_qa_top_results"
_MODEL_KEY = "rag_qa_llm_model"
_TONE_KEY = "rag_qa_tone"
_QUESTION_KEY = "rag_qa_question"
_PROMPT_KEY = "rag_qa_prompt"
# The last answer and its stats caption persist so they survive reruns after a send.
_ANSWER_KEY = "rag_qa_answer"
_STATS_KEY = "rag_qa_stats"
# A replay stashes a record here; a one-shot flag then moves focus to the prompt.
_REPLAY_KEY = "rag_qa_replay"
_FOCUS_PROMPT_KEY = "rag_qa_focus_prompt"


def render_page(context: RagPageContext) -> None:
    """Render the Simple RAG Q&A page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    session_root = context.session_root()
    indexes = list(context.list_indexes())

    st.subheader(strings["QA_SECTION_HEADER"], anchor="rag-qa-header")
    st.caption(strings["QA_SECTION_CAPTION"])
    summary_slot = st.container()

    # Apply a pending replay before the widgets render, then seed first-run
    # defaults so a replay can overwrite them without a Streamlit warning.
    replay = st.session_state.pop(_REPLAY_KEY, None)
    if replay is not None:
        _apply_replay(strings, indexes, replay)
    model_options, default_model_index = chat_model_choices()
    tones, default_tone_index = tone_choices()
    st.session_state.setdefault(_TOP_RESULTS_KEY, _DEFAULT_TOP_RESULTS)
    st.session_state.setdefault(_MODEL_KEY, model_options[default_model_index])
    st.session_state.setdefault(_TONE_KEY, tones[default_tone_index])
    st.session_state.setdefault(_QUESTION_KEY, "")
    st.session_state.setdefault(_PROMPT_KEY, "")

    index, model, tone, top_results = _render_panel(strings, indexes, model_options, tones)
    question, generate = _render_question_form(strings, disabled=index is None)
    if generate and index is not None and question.strip():
        _generate_prompt(strings, index, question.strip(), top_results, tone, model)

    prompt_text, send = _render_prompt_form(strings, disabled=index is None)
    if st.session_state.pop(_FOCUS_PROMPT_KEY, False):
        focus_widget(_PROMPT_KEY)

    answered_now = False
    if send and index is not None:
        st.session_state[_ANSWER_KEY] = None
        st.session_state[_STATS_KEY] = None
        if prompt_text.strip():
            answered_now = _send_prompt(
                strings,
                session_root,
                index=index,
                model=model,
                tone=tone,
                top_results=top_results,
                question=question,
                prompt_text=prompt_text,
            )
        else:
            st.info(strings["QA_NO_PROMPT_HINT"])
    if not answered_now:
        _render_stored_answer(strings)

    records = load_qa_history(session_root)
    _render_qa_history(strings, records)
    with summary_slot:
        _render_token_summary(strings, records)

    context.render_downloads()


def _render_panel(
    strings: Strings,
    indexes: Sequence[IndexRef],
    model_options: Sequence[str],
    tones: Sequence[str],
) -> tuple[IndexRef | None, str, str, int]:
    """Render the index / top-results / model / tone panel; return the choices."""
    with st.container(border=True):
        index_col, top_col = st.columns(_PANEL_INDEX_COLUMN_WIDTHS)
        with index_col:
            index = select_index(strings, indexes, key=_INDEX_KEY)
        with top_col:
            top_results = int(
                st.number_input(
                    strings["QA_TOP_RESULTS_LABEL"],
                    min_value=1,
                    max_value=_MAX_TOP_RESULTS,
                    step=1,
                    help=strings["QA_TOP_RESULTS_HELP"],
                    disabled=index is None,
                    key=_TOP_RESULTS_KEY,
                )
            )
        model_col, tone_col = st.columns(2)
        with model_col:
            model = st.selectbox(
                strings["QA_LLM_LABEL"],
                options=list(model_options),
                format_func=lambda model_id: chat_model_label(model_id, strings),
                help=strings["QA_LLM_HELP"],
                disabled=index is None,
                key=_MODEL_KEY,
            )
        with tone_col:
            tone = st.selectbox(
                strings["QA_TONE_LABEL"],
                options=list(tones),
                help=strings["QA_TONE_HELP"],
                disabled=index is None,
                key=_TONE_KEY,
            )
        if index is not None:
            render_index_metadata(strings, index)
    return index, model, tone, top_results


def _render_question_form(strings: Strings, *, disabled: bool) -> tuple[str, bool]:
    """Render the question field + Generate-prompt button (Enter submits)."""
    with st.form("rag_qa_question_form", enter_to_submit=True, border=True):
        question = st.text_input(
            strings["QA_QUESTION_LABEL"],
            placeholder=strings["QA_QUESTION_PLACEHOLDER"],
            disabled=disabled,
            key=_QUESTION_KEY,
        )
        generate = st.form_submit_button(
            strings["QA_GENERATE_BUTTON"],
            type="primary",
            icon=":material/auto_awesome:",
            help=strings["QA_GENERATE_HELP"],
            disabled=disabled,
        )
    return question, generate


def _render_prompt_form(strings: Strings, *, disabled: bool) -> tuple[str, bool]:
    """Render the editable prompt field + Send button (Ctrl/Cmd+Enter submits)."""
    with st.form("rag_qa_prompt_form", enter_to_submit=True, border=True):
        prompt_text = st.text_area(
            strings["QA_PROMPT_LABEL"],
            placeholder=strings["QA_PROMPT_PLACEHOLDER"],
            help=strings["QA_PROMPT_HELP"],
            height=_PROMPT_FIELD_HEIGHT,
            disabled=disabled,
            key=_PROMPT_KEY,
        )
        send = st.form_submit_button(
            strings["QA_SEND_BUTTON"],
            type="primary",
            icon=":material/send:",
            help=strings["QA_SEND_HELP"],
            disabled=disabled,
        )
    return prompt_text, send


def _generate_prompt(
    strings: Strings, index: IndexRef, question: str, top_results: int, tone: str, model: str
) -> None:
    """Retrieve knowledge for *question* and build the editable prompt from it."""
    config = RagConfig(top_k=top_results, llm_model=model)
    with st.spinner(strings["SEARCH_SEARCHING"]):
        result = retrieve(index.run_dir, question, config)
    render_messages(strings, result.warnings, result.errors)
    st.session_state[_PROMPT_KEY] = build_rag_prompt(question, result.chunks, tone)
    st.session_state[_ANSWER_KEY] = None
    st.session_state[_STATS_KEY] = None
    st.session_state[_FOCUS_PROMPT_KEY] = True


def _send_prompt(
    strings: Strings,
    session_root: Path,
    *,
    index: IndexRef,
    model: str,
    tone: str,
    top_results: int,
    question: str,
    prompt_text: str,
) -> bool:
    """Stream the model's answer to *prompt_text* and record it; return success."""
    resolved, warnings = resolve_chat_model(model)
    render_messages(strings, warnings, [])
    st.markdown(f"**{strings['QA_ANSWER_HEADER']}**")
    generation = stream_prompt(resolved.model, prompt_text)
    start = time.perf_counter()
    try:
        st.write_stream(generation)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        render_messages(strings, [], [messages.classify_generation_failure(str(exc))])
        return False
    elapsed = time.perf_counter() - start
    caption = _stats_caption(strings, generation.usage, elapsed)
    st.caption(caption)
    _record_send(
        session_root,
        index=index,
        model_used=resolved.model_id,
        tone=tone,
        top_results=top_results,
        question=question,
        prompt_text=prompt_text,
        usage=generation.usage,
        elapsed=elapsed,
    )
    st.session_state[_ANSWER_KEY] = generation.text
    st.session_state[_STATS_KEY] = caption
    return True


def _record_send(
    session_root: Path,
    *,
    index: IndexRef,
    model_used: str,
    tone: str,
    top_results: int,
    question: str,
    prompt_text: str,
    usage: TokenUsage | None,
    elapsed: float,
) -> None:
    append_qa_record(
        session_root,
        QaRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            index_folder=index.vector_folder,
            index_run=index.run_name,
            embedding_model=index.manifest.embedding_model_used or "",
            llm_model=model_used,
            tone=tone,
            top_k=int(top_results),
            question=question.strip(),
            prompt=prompt_text,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            latency_seconds=elapsed,
        ),
    )


def _render_stored_answer(strings: Strings) -> None:
    """Re-render the last answer (and stats) so it survives reruns after a send."""
    answer = st.session_state.get(_ANSWER_KEY)
    if not answer:
        return
    st.markdown(f"**{strings['QA_ANSWER_HEADER']}**")
    st.write(answer)
    caption = st.session_state.get(_STATS_KEY)
    if caption:
        st.caption(caption)


def _render_token_summary(strings: Strings, records: Sequence[QaRecord]) -> None:
    """Render the page-top input/output/total token metrics for the session."""
    totals = token_totals(records)
    cols = st.columns(3)
    cols[0].metric(strings["QA_SUMMARY_INPUT_LABEL"], f"{totals.input_tokens:,}")
    cols[1].metric(strings["QA_SUMMARY_OUTPUT_LABEL"], f"{totals.output_tokens:,}")
    cols[2].metric(strings["QA_SUMMARY_TOTAL_LABEL"], f"{totals.total_tokens:,}")


def _stats_caption(strings: Strings, usage: TokenUsage | None, seconds: float) -> str:
    """Build the per-answer token + latency caption, showing n/a for missing counts."""
    na = strings["QA_TOKEN_NA"]
    return strings["QA_ANSWER_STATS"].format(
        input=na if usage is None or usage.input_tokens is None else usage.input_tokens,
        output=na if usage is None or usage.output_tokens is None else usage.output_tokens,
        total=na if usage is None or usage.total_tokens is None else usage.total_tokens,
        seconds=f"{seconds:.1f}",
    )


def _apply_replay(strings: Strings, indexes: Sequence[IndexRef], replay: dict) -> None:
    """Pre-fill the Step 4 widgets from a stored history record before they render."""
    st.session_state[_QUESTION_KEY] = str(replay.get("question", ""))
    st.session_state[_PROMPT_KEY] = str(replay.get("prompt", ""))
    st.session_state[_TOP_RESULTS_KEY] = int(replay.get("top_k", _DEFAULT_TOP_RESULTS))
    options, _ = chat_model_choices()
    model = str(replay.get("llm_model", ""))
    if model in options:
        st.session_state[_MODEL_KEY] = model
    tones, _ = tone_choices()
    tone = str(replay.get("tone", ""))
    if tone in tones:
        st.session_state[_TONE_KEY] = tone
    ref = find_index(indexes, str(replay.get("index_folder", "")), str(replay.get("index_run", "")))
    if ref is not None:
        st.session_state[_INDEX_KEY] = index_option_label(strings, ref)
    st.session_state[_ANSWER_KEY] = None
    st.session_state[_STATS_KEY] = None
    st.session_state[_FOCUS_PROMPT_KEY] = True


def _tokens_value(strings: Strings, record: QaRecord) -> str:
    na = strings["QA_TOKEN_NA"]
    return strings["QA_HISTORY_TOKENS_VALUE"].format(
        input=na if record.input_tokens is None else record.input_tokens,
        output=na if record.output_tokens is None else record.output_tokens,
        total=na if record.total_tokens is None else record.total_tokens,
    )


def _history_grid(strings: Strings, record: QaRecord) -> str:
    """Build a tidy label/value grid summarising one history record."""
    rows = [
        (strings["QA_HISTORY_META_INDEX"], f"{record.index_folder} / {record.index_run}"),
        (strings["QA_HISTORY_META_MODEL"], record.llm_model or "—"),
        (strings["QA_HISTORY_META_TONE"], record.tone or "—"),
        (strings["QA_HISTORY_META_TOP"], str(record.top_k)),
        (strings["QA_HISTORY_META_TOKENS"], _tokens_value(strings, record)),
        (
            strings["QA_HISTORY_META_TIME"],
            strings["QA_HISTORY_SECONDS"].format(seconds=f"{record.latency_seconds:.1f}"),
        ),
    ]
    return kv_grid_html(rows)


def _render_qa_history(strings: Strings, records: Sequence[QaRecord]) -> None:
    """Render the collapsible prompt history as tidy cards with a replay button."""
    with st.expander(strings["QA_HISTORY_EXPANDER"], expanded=False):
        if not records:
            st.caption(strings["QA_HISTORY_EMPTY"])
            return
        for position, record in enumerate(records):
            with st.container(border=True):
                head, action = st.columns([0.85, 0.15], vertical_alignment="center")
                head.markdown(f"**{record.question or '—'}**")
                with action, st.container(horizontal_alignment="right"):
                    if st.button(
                        ":material/replay:",
                        key=f"qa_history_replay_{position}",
                        help=strings["QA_HISTORY_REPLAY_HELP"],
                    ):
                        st.session_state[_REPLAY_KEY] = asdict(record)
                        st.rerun()
                st.caption(local_time_label(record.timestamp_utc))
                st.markdown(_history_grid(strings, record), unsafe_allow_html=True)
