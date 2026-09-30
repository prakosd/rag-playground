"""Browser-localStorage session bridge extracted from ``streamlit_app.py``.

The CCv2 component that mirrors session records to/from browser localStorage, plus
the helpers that read, normalize, and server-validate those records. UI-thin: it only
touches ``st.session_state`` and the shared stores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.components import v2 as st_components_v2

from app_support.app_runtime import _SESSIONS_ROOT
from app_support.shell.constants import (
    _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD,
    _PORTFOLIO_MODAL_LAST_SHOWN_FIELD,
    _SESSION_STORAGE_COMPONENT_KEY,
    _SESSION_STORAGE_KEY,
)
from app_support.shell.session_records import (
    SESSION_RECORDS_CACHE_STATE,
    normalize_session_records_cached,
)
from app_support.support import (
    SessionRecord,
    serialize_session_records,
    session_exists,
)

_SESSION_STORAGE_HTML = """
<div id="crawl4md-session-storage" hidden></div>
"""
_SESSION_STORAGE_JS = """
const SESSION_ID_PATTERN = /^[a-z0-9_-]+$/
const SUPPORTED_LANGUAGES = new Set(["EN", "ID"])

function normalizeTimestamp(value) {
    if (typeof value !== "string") return null
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toISOString().replace(".000Z", "Z")
}

function normalizeRecords(records) {
    const byId = new Map()
    for (const record of records || []) {
        if (!record || typeof record.session_id !== "string") continue
        if (!SESSION_ID_PATTERN.test(record.session_id)) continue
        if (typeof record.created_at !== "string") continue
        const createdAt = new Date(record.created_at)
        if (Number.isNaN(createdAt.getTime())) continue
        const rawLang = typeof record.language === "string" ? record.language.trim().toUpperCase() : ""
        const language = SUPPORTED_LANGUAGES.has(rawLang) ? rawLang : "EN"
        const normalized = {
            session_id: record.session_id,
            created_at: createdAt.toISOString().replace(".000Z", "Z"),
            language,
        }
        const existing = byId.get(normalized.session_id)
        if (!existing || createdAt >= new Date(existing.created_at)) {
            byId.set(normalized.session_id, normalized)
        }
    }
    return Array.from(byId.values()).sort((left, right) => {
        const timeDelta = new Date(right.created_at) - new Date(left.created_at)
        if (timeDelta !== 0) return timeDelta
        return right.session_id.localeCompare(left.session_id)
    })
}

function readStorage(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) {
            return {
                records: [],
                selectedSessionId: null,
                portfolioModalLastShownAt: null,
                portfolioModalLastDismissedAt: null,
            }
        }
        const parsed = JSON.parse(rawValue)
        const records = Array.isArray(parsed)
            ? normalizeRecords(parsed)
            : normalizeRecords(parsed.sessions)
        const rawSelected = typeof parsed.selected_session_id === "string"
            ? parsed.selected_session_id.trim()
            : null
        const selectedSessionId = rawSelected && SESSION_ID_PATTERN.test(rawSelected)
            ? rawSelected
            : null
        return {
            records,
            selectedSessionId,
            portfolioModalLastShownAt: normalizeTimestamp(parsed.portfolio_modal_last_shown_at),
            portfolioModalLastDismissedAt: normalizeTimestamp(parsed.portfolio_modal_last_dismissed_at),
        }
    } catch {
        return {
            records: [],
            selectedSessionId: null,
            portfolioModalLastShownAt: null,
            portfolioModalLastDismissedAt: null,
        }
    }
}

function writeStorage(
    storageKey,
    records,
    selectedSessionId,
    portfolioModalLastShownAt,
    portfolioModalLastDismissedAt,
) {
    try {
        const payload = { version: 1, sessions: records }
        if (selectedSessionId) payload.selected_session_id = selectedSessionId
        if (portfolioModalLastShownAt) {
            payload.portfolio_modal_last_shown_at = portfolioModalLastShownAt
        }
        if (portfolioModalLastDismissedAt) {
            payload.portfolio_modal_last_dismissed_at = portfolioModalLastDismissedAt
        }
        window.localStorage.setItem(storageKey, JSON.stringify(payload))
        return true
    } catch {
        return false
    }
}

export default function (component) {
    const { data, setStateValue } = component
    const storageKey = data.storageKey
    const {
        records: storedRecords,
        selectedSessionId: storedSelectedId,
        portfolioModalLastShownAt,
        portfolioModalLastDismissedAt,
    } = readStorage(storageKey)
    const idsToRemove = new Set(Array.isArray(data.recordsToRemove) ? data.recordsToRemove : [])
    const filteredStoredRecords = idsToRemove.size > 0
        ? storedRecords.filter(r => !idsToRemove.has(r.session_id))
        : storedRecords
    const pendingRecords = Array.isArray(data.pendingRecords) ? data.pendingRecords : []
    const nextRecords = normalizeRecords([...filteredStoredRecords, ...pendingRecords])
    const nextSerialized = JSON.stringify(nextRecords)
    const storedSerialized = JSON.stringify(storedRecords)
    const pendingSelectedId = typeof data.pendingSelectedSessionId === "string"
        ? data.pendingSelectedSessionId.trim()
        : null
    const nextSelectedId = pendingSelectedId || storedSelectedId
    const hasPendingRecords = pendingRecords.length > 0
    const recordsNeedWrite = nextSerialized !== storedSerialized
    const selectedNeedsWrite = !!pendingSelectedId && pendingSelectedId !== storedSelectedId
    let storedPending = (!hasPendingRecords || !recordsNeedWrite) && !selectedNeedsWrite
    if (recordsNeedWrite || selectedNeedsWrite) {
        storedPending = writeStorage(
            storageKey,
            nextRecords,
            nextSelectedId,
            portfolioModalLastShownAt,
            portfolioModalLastDismissedAt,
        )
    }
    const storageWriteFailed = (hasPendingRecords || !!pendingSelectedId) && storedPending === false
    if (hasPendingRecords && storedPending) {
        setStateValue("stored_records", nextRecords)
    }
    if (data.storageWriteFailed !== storageWriteFailed) {
        setStateValue("storage_write_failed", storageWriteFailed)
    }

    const pythonRecords = normalizeRecords(Array.isArray(data.records) ? data.records : [])
    if (JSON.stringify(pythonRecords) !== nextSerialized) {
        setStateValue("records", nextRecords)
    }
    if (data.hydrated !== true) {
        setStateValue("hydrated", true)
    }
    if (nextSelectedId && data.selectedSessionId !== nextSelectedId) {
        setStateValue("selected_session_id", nextSelectedId)
    }
    if (
        portfolioModalLastShownAt
        && data.portfolioModalLastShownAt !== portfolioModalLastShownAt
    ) {
        setStateValue("portfolio_modal_last_shown_at", portfolioModalLastShownAt)
    }
    if (
        portfolioModalLastDismissedAt
        && data.portfolioModalLastDismissedAt !== portfolioModalLastDismissedAt
    ) {
        setStateValue("portfolio_modal_last_dismissed_at", portfolioModalLastDismissedAt)
    }
}
"""


def _cached_normalize_session_records(payload: object) -> list[SessionRecord]:
    cache = st.session_state.get(SESSION_RECORDS_CACHE_STATE)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[SESSION_RECORDS_CACHE_STATE] = cache
    return normalize_session_records_cached(payload, cache)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_session_exists(sessions_root: str, session_id: str) -> bool:
    return session_exists(Path(sessions_root), session_id)


def _filter_server_valid_sessions(
    records: list[SessionRecord], current_session_id: str
) -> tuple[list[SessionRecord], list[str]]:
    """Split records into server-valid and missing; exempt the current session."""
    sessions_root_str = str(_SESSIONS_ROOT.resolve())
    valid: list[SessionRecord] = []
    invalid_ids: list[str] = []
    for record in records:
        if (
            record.session_id == current_session_id
            or _cached_session_exists(  # exempt the current session
                sessions_root_str, record.session_id
            )
        ):
            valid.append(record)
        else:
            invalid_ids.append(record.session_id)
    return valid, invalid_ids


def _browser_session_records() -> list[SessionRecord]:
    records = st.session_state.get("browser_session_records", [])
    if isinstance(records, list) and all(isinstance(record, SessionRecord) for record in records):
        return records
    return _cached_normalize_session_records(records)


def _component_field(result: Any, field: str) -> Any:
    value = getattr(result, field, None)
    if value is not None:
        return value
    component_state = st.session_state.get(_SESSION_STORAGE_COMPONENT_KEY, {})
    getter = getattr(component_state, "get", None)
    if callable(getter):
        return getter(field)
    return getattr(component_state, field, None)


def _component_result_field(result: Any, field: str) -> Any:
    return getattr(result, field, None)


def _mount_session_storage() -> None:
    # Build per rerun so tests can patch streamlit.components.v2 (AppTest caches this module).
    session_storage_component = st_components_v2.component(
        "crawl4md_session_storage",
        html=_SESSION_STORAGE_HTML,
        js=_SESSION_STORAGE_JS,
    )
    result = session_storage_component(
        key=_SESSION_STORAGE_COMPONENT_KEY,
        data={
            "storageKey": _SESSION_STORAGE_KEY,
            "records": serialize_session_records(_browser_session_records()),
            "pendingRecords": st.session_state.pending_browser_session_records,
            "pendingSelectedSessionId": st.session_state.pending_selected_session_id,
            "selectedSessionId": st.session_state.preferred_session_id,
            "hydrated": st.session_state.browser_sessions_hydrated,
            "storageWriteFailed": st.session_state.session_storage_write_failed,
            "recordsToRemove": st.session_state.get("session_ids_to_purge", []),
            "portfolioModalLastShownAt": st.session_state.get(
                _PORTFOLIO_MODAL_LAST_SHOWN_FIELD, ""
            ),
            "portfolioModalLastDismissedAt": st.session_state.get(
                _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD, ""
            ),
        },
        on_records_change=lambda: None,
        on_stored_records_change=lambda: None,
        on_storage_write_failed_change=lambda: None,
        on_hydrated_change=lambda: None,
        on_selected_session_id_change=lambda: None,
        on_portfolio_modal_last_shown_at_change=lambda: None,
        on_portfolio_modal_last_dismissed_at_change=lambda: None,
    )
    _apply_session_storage_result(result)


def _apply_session_storage_result(result: Any) -> None:
    records_payload = _component_field(result, "records")
    if records_payload is not None:
        normalized_payload = _cached_normalize_session_records(records_payload)
        st.session_state.browser_session_records = _cached_normalize_session_records(
            [
                *serialize_session_records(normalized_payload),
                *serialize_session_records(_browser_session_records()),
                *st.session_state.pending_browser_session_records,
            ]
        )
    storage_write_failed = _component_result_field(result, "storage_write_failed")
    if storage_write_failed is not None:
        st.session_state.session_storage_write_failed = bool(storage_write_failed)
    if _component_field(result, "hydrated") is True:
        st.session_state.browser_sessions_hydrated = True
    if records_payload is not None and st.session_state.browser_sessions_hydrated:
        valid, invalid_ids = _filter_server_valid_sessions(
            _browser_session_records(), str(st.session_state.get("session_id", ""))
        )
        st.session_state.browser_session_records = valid
        st.session_state.session_ids_to_purge = invalid_ids

    pending = _cached_normalize_session_records(st.session_state.pending_browser_session_records)
    stored_payload = _component_result_field(result, "stored_records")
    pending_ack_payload = stored_payload
    if (
        pending_ack_payload is None
        and records_payload is not None
        and not st.session_state.session_storage_write_failed
    ):
        pending_ack_payload = records_payload
    if pending and pending_ack_payload is not None:
        stored_ids = {
            record.session_id for record in _cached_normalize_session_records(pending_ack_payload)
        }
        if {record.session_id for record in pending}.issubset(stored_ids):
            st.session_state.pending_browser_session_records = []
        if st.session_state.pending_bootstrap_session_id in stored_ids:
            st.session_state.pending_bootstrap_session_id = ""
            st.session_state.session_storage_write_failed = False

    # Restore the previously selected session id from browser storage if present.
    stored_selected_id = _component_result_field(result, "selected_session_id")
    if isinstance(stored_selected_id, str) and stored_selected_id.strip():
        candidate = stored_selected_id.strip()
        records = _browser_session_records()
        known_ids = {r.session_id for r in records}
        if candidate in known_ids and not st.session_state.preferred_session_id:
            st.session_state.preferred_session_id = candidate

    last_shown_at = _component_field(result, _PORTFOLIO_MODAL_LAST_SHOWN_FIELD)
    if isinstance(last_shown_at, str):
        st.session_state[_PORTFOLIO_MODAL_LAST_SHOWN_FIELD] = last_shown_at.strip()
    last_dismissed_at = _component_field(result, _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD)
    if isinstance(last_dismissed_at, str):
        st.session_state[_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD] = last_dismissed_at.strip()

    # Clear pending_selected_session_id after one round-trip — JS writes synchronously
    # so confirmation via stored_payload is not needed.
    if st.session_state.pending_selected_session_id:
        st.session_state.pending_selected_session_id = ""
