"""Per-showcase browser-localStorage bridge for a visitor's conversation ids.

A showcase runs as a fresh Streamlit session, so a visitor's own conversations (the
picker is filtered to them) would vanish on reload without browser storage. This thin
CCv2 bridge mirrors a per-slug list of conversation ids to/from ``localStorage`` so
the New-conversation button and conversation picker survive reloads, exactly like the
session-id bridge does for sessions. Incognito or cleared storage starts fresh. Only
short, opaque conversation ids are stored — never a secret or any chat text.
"""

from __future__ import annotations

import re

import streamlit as st
from streamlit.components import v2 as st_components_v2

__all__ = [
    "merge_conversation_ids",
    "showcase_conversations_hydrated",
    "sync_showcase_conversation_ids",
]

_COMPONENT_NAME = "crawl4md_showcase_conversations"
# One localStorage entry per showcase link; the slug scopes it (see build_manager).
_STORAGE_KEY_PREFIX = "crawl4md-showcase-conv-"
_COMPONENT_KEY_PREFIX = "showcase_conv_storage_"
# Conversation ids are short lowercase alphanumeric (conversation_manager._short_id);
# the bound keeps a crafted value from bloating storage, and empty legacy ids drop out.
# Keep in sync with ID_PATTERN in the JS below (both validate the same ids).
_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")

_STORAGE_HTML = """
<div id="crawl4md-showcase-conversations" hidden></div>
"""
_STORAGE_JS = """
// Mirror of _ID_RE in the Python module; keep both in sync.
const ID_PATTERN = /^[a-z0-9]{1,32}$/

function uniqueIds(ids) {
    const seen = new Set()
    const out = []
    for (const id of ids) {
        if (typeof id === "string" && ID_PATTERN.test(id) && !seen.has(id)) {
            seen.add(id)
            out.push(id)
        }
    }
    return out
}

function readIds(storageKey) {
    try {
        const raw = window.localStorage.getItem(storageKey)
        if (!raw) return []
        const parsed = JSON.parse(raw)
        return Array.isArray(parsed) ? uniqueIds(parsed) : []
    } catch {
        return []
    }
}

function writeIds(storageKey, ids) {
    try {
        window.localStorage.setItem(storageKey, JSON.stringify(ids))
    } catch {
        // A full or disabled store just means no persistence this visit.
    }
}

export default function (component) {
    const { data, setStateValue } = component
    const storageKey = data.storageKey
    const stored = readIds(storageKey)
    const pending = Array.isArray(data.pendingIds) ? data.pendingIds : []
    const merged = uniqueIds([...stored, ...pending])
    if (JSON.stringify(merged) !== JSON.stringify(stored)) {
        writeIds(storageKey, merged)
    }
    const known = Array.isArray(data.ids) ? data.ids : []
    if (JSON.stringify(known) !== JSON.stringify(merged)) {
        setStateValue("ids", merged)
    }
    if (data.hydrated !== true) {
        setStateValue("hydrated", true)
    }
}
"""


def merge_conversation_ids(stored: object, pending: object) -> list[str]:
    """Merge stored + pending conversation ids: valid, de-duplicated, order-preserving."""
    out: list[str] = []
    seen: set[str] = set()
    for source in (stored, pending):
        if not isinstance(source, (list, tuple)):
            continue
        for item in source:
            if isinstance(item, str) and _ID_RE.match(item) and item not in seen:
                seen.add(item)
                out.append(item)
    return out


def sync_showcase_conversation_ids(slug: str, pending_ids: list[str]) -> list[str]:
    """Mirror the visitor's conversation ids for *slug* to/from localStorage.

    Writes any *pending_ids* (conversations that now have a saved turn) and returns the
    merged, persisted list. Mounts a per-slug CCv2 bridge; before the browser hydrates
    it (or in a headless test) the stored list is unknown, so the result is just the
    pending ids — the picker fills in on the hydration rerun.
    """
    component_key = f"{_COMPONENT_KEY_PREFIX}{slug}"
    state = st.session_state.get(component_key, {})
    known = state.get("ids", []) if hasattr(state, "get") else []
    pending = [item for item in pending_ids if isinstance(item, str) and _ID_RE.match(item)]
    # Build per rerun so tests can patch streamlit.components.v2 (AppTest caches module).
    component = st_components_v2.component(_COMPONENT_NAME, html=_STORAGE_HTML, js=_STORAGE_JS)
    result = component(
        key=component_key,
        data={
            "storageKey": f"{_STORAGE_KEY_PREFIX}{slug}",
            "pendingIds": pending,
            "ids": known if isinstance(known, list) else [],
            "hydrated": bool(state.get("hydrated")) if hasattr(state, "get") else False,
        },
        on_ids_change=lambda: None,
        on_hydrated_change=lambda: None,
    )
    hydrated_ids = getattr(result, "ids", None)
    if hydrated_ids is None and hasattr(state, "get"):
        hydrated_ids = state.get("ids")
    return merge_conversation_ids(hydrated_ids, pending)


def showcase_conversations_hydrated(slug: str) -> bool:
    """Return ``True`` once the browser bridge for *slug* has hydrated from localStorage.

    The bridge sets a ``hydrated`` flag on its first client round-trip; until then the
    visitor's stored conversation ids are still unknown. Callers use this to defer a
    one-time initial selection (open the visitor's latest conversation) until their saved
    list has actually arrived, instead of acting on the pre-hydration empty list.
    """
    state = st.session_state.get(f"{_COMPONENT_KEY_PREFIX}{slug}", {})
    return bool(state.get("hydrated")) if hasattr(state, "get") else False
