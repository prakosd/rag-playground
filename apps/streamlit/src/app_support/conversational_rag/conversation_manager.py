"""Group, title, and replay Step 5 (Conversational RAG) turns per session.

Turns persist to the session's history JSONL tagged with a ``conversation_id`` so
one session can hold several independent conversations ("saved games"). These
pure helpers (no Streamlit) group persisted records into conversations, derive a
human title, mint short ids, and rebuild a *display-adequate*
``ConversationalAnswer`` from a stored record — enough to re-render a turn and
seed continuity, but without the un-persisted live retrieval cache or full
rolling state. Loading a session can then rehydrate the conversation dropdown and
replay a selected conversation's turns.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace

from rag_engine import (
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RetrievedChunk,
    ValidatedFollowup,
)

from app_support.conversational_rag.conversational_rag_history import ConversationalTurnRecord
from app_support.rag_shared.result_snapshot import StoredResult

__all__ = [
    "ConversationSummary",
    "asked_questions_from_records",
    "conversation_summaries",
    "conversation_title",
    "conversation_turns",
    "new_conversation_id",
    "new_transaction_id",
    "trim_old_turn_payloads",
    "turn_from_record",
]

# Short, human-scannable ids that fit a dropdown label and a token-table column.
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_ID_LENGTH = 6
_TITLE_MAX_CHARS = 48
# Mirrors rag_engine's asked-question history cap so a reloaded conversation seeds
# the same bounded history the live pipeline maintains.
_ASKED_HISTORY_CAP = 20


@dataclass(frozen=True)
class ConversationSummary:
    """One conversation's dropdown entry: id, title, size, and last activity."""

    conversation_id: str
    title: str
    turn_count: int
    latest_timestamp_utc: str


def _short_id() -> str:
    """Return a short, collision-resistant, path-safe lowercase id."""
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))


def new_conversation_id() -> str:
    """Return a fresh conversation id (groups a session's turns into a chat)."""
    return _short_id()


def new_transaction_id() -> str:
    """Return a fresh transaction id (identifies one turn within a conversation)."""
    return _short_id()


def conversation_title(summary: str, first_question: str) -> str:
    """Derive a short conversation title from the rewriter summary or first question.

    Prefers the rolling ``summary`` (once the rewriter has one) and otherwise the
    first user question, truncated with an ellipsis. Returns ``""`` only when both
    are empty, letting the caller supply a localized placeholder.
    """
    text = summary.strip() or first_question.strip()
    if len(text) > _TITLE_MAX_CHARS:
        return text[: _TITLE_MAX_CHARS - 1].rstrip() + "\u2026"
    return text


def _chunks_from_results(results: tuple[StoredResult, ...]) -> list[RetrievedChunk]:
    """Rebuild renderable chunks from a turn's stored result snapshots.

    Mirrors ``rag_ui.chunks_from_stored`` but is inlined here so this module stays
    free of Streamlit (``rag_ui`` imports it), keeping it unit-testable in isolation.
    """
    return [
        RetrievedChunk(
            text=item.text,
            source=item.source,
            score=item.score,
            metadata=dict(item.metadata),
        )
        for item in results
    ]


def turn_from_record(record: ConversationalTurnRecord) -> dict:
    """Rebuild a display-adequate ``{question, answer}`` turn from a stored record.

    The answer carries the persisted text, sources, sub-questions, follow-ups,
    per-stage timings, models, and the rolling summary — enough to re-render the
    turn and its inspector. Un-persisted fields (live retrieval cache, entities,
    warnings/errors) are left empty; the turn id is assigned by the caller.
    """
    answer = ConversationalAnswer(
        answer=record.answer,
        sources=_chunks_from_results(record.results),
        plan=QueryPlan(sub_questions=list(record.sub_questions)),
        follow_ups=[ValidatedFollowup(question=question) for question in record.follow_ups_shown],
        state=ConversationState(summary=record.state_summary),
        model_used=record.llm_model or None,
        aux_model_used=record.aux_model or None,
        reranker_used=record.reranker or None,
        timings={
            "plan": record.plan_seconds,
            "retrieve": record.retrieve_seconds,
            "rerank": record.rerank_seconds,
            "answer": record.answer_seconds,
            "followups": record.followups_seconds,
            "state": record.state_seconds,
        },
    )
    return {"question": record.raw_question, "answer": answer}


def conversation_turns(records: list[ConversationalTurnRecord], conversation_id: str) -> list[dict]:
    """Rebuild one conversation's turns, oldest first, with sequential turn ids."""
    ordered = sorted(
        (record for record in records if record.conversation_id == conversation_id),
        key=lambda record: record.timestamp_utc,
    )
    turns: list[dict] = []
    for index, record in enumerate(ordered):
        turn = turn_from_record(record)
        turn["turn_id"] = index
        turns.append(turn)
    return turns


def asked_questions_from_records(
    records: list[ConversationalTurnRecord], conversation_id: str
) -> tuple[str, ...]:
    """Rebuild a conversation's asked-question history from its saved turns.

    Folds every turn's resolved sub-questions (oldest first, case-insensitively
    de-duplicated, capped) so follow-up de-duplication survives a reload — the
    live ``ConversationState.asked_questions`` is not persisted to disk.
    """
    ordered = sorted(
        (record for record in records if record.conversation_id == conversation_id),
        key=lambda record: record.timestamp_utc,
    )
    asked: list[str] = []
    seen: set[str] = set()
    for record in ordered:
        for question in record.sub_questions or (record.raw_question,):
            text = question.strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                asked.append(text)
    return tuple(asked[-_ASKED_HISTORY_CAP:])


def trim_old_turn_payloads(turns: list[dict], keep_recent: int) -> None:
    """Shed heavy chunk payloads from turns older than the *keep_recent* newest.

    Frees each old turn's retrieved ``sources`` and follow-up ``chunks`` (the bulk
    of a turn's memory) in place while keeping its question/answer text so the
    transcript still renders. The newest ``keep_recent`` turns stay intact so the
    follow-up buttons and per-turn inspector keep working.
    """
    if keep_recent <= 0 or len(turns) <= keep_recent:
        return
    for turn in turns[:-keep_recent]:
        answer = turn["answer"]
        answer.sources = []
        answer.follow_ups = [replace(followup, chunks=[]) for followup in answer.follow_ups]


def conversation_summaries(
    records: list[ConversationalTurnRecord],
) -> list[ConversationSummary]:
    """Group persisted turns into conversations, most recently active first.

    Each summary titles the conversation from its latest rolling summary (falling
    back to the first question) and counts its turns. Turns predating conversation
    ids (empty id) collapse into a single legacy group.
    """
    groups: dict[str, list[ConversationalTurnRecord]] = {}
    for record in records:
        groups.setdefault(record.conversation_id, []).append(record)
    summaries: list[ConversationSummary] = []
    for conversation_id, group in groups.items():
        ordered = sorted(group, key=lambda record: record.timestamp_utc)
        latest = ordered[-1]
        summaries.append(
            ConversationSummary(
                conversation_id=conversation_id,
                title=conversation_title(latest.state_summary, ordered[0].raw_question),
                turn_count=len(ordered),
                latest_timestamp_utc=latest.timestamp_utc,
            )
        )
    summaries.sort(key=lambda summary: summary.latest_timestamp_utc, reverse=True)
    return summaries
