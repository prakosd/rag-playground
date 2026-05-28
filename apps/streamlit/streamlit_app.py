from __future__ import annotations

import html
import mimetypes
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import altair as alt
import streamlit as st
from pydantic import ValidationError
from streamlit.components.v2 import component as component_v2

from crawl4md_streamlit.form_defaults import DEFAULT_LIMIT, default_form_values
from crawl4md_streamlit.form_ui import render_crawl_form
from crawl4md_streamlit.generated_files import (
    build_download_tree,
    collapse_crawl_run_folder,
    generated_files_cache_token,
)
from crawl4md_streamlit.i18n import CATALOG, get_strings
from crawl4md_streamlit.progress_chart import (
    PROGRESS_CHART_TIME_UNIT_HOUR,
    PROGRESS_CHART_TIME_UNIT_MINUTE,
    PROGRESS_CHART_TIME_UNIT_SECOND,
    append_live_progress_sample,
    load_persisted_progress_history,
    prefer_persisted_history,
    prepare_cumulative_chart_display_rows,
    prepare_cumulative_chart_rows,
    prepare_pace_chart_rows,
    progress_chart_time_unit_seconds,
    select_progress_chart_time_unit,
)
from crawl4md_streamlit.support import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    DEFAULT_SESSION_LANGUAGE,
    PLAYWRIGHT_MISSING_BROWSER_MESSAGE,
    CrawlJob,
    GeneratedFile,
    ReadyDownload,
    SessionRecord,
    active_registry_session_ids,
    activity_log_path,
    bootstrap_gate_state,
    build_configs,
    build_ready_download,
    cleanup_old_sessions_with_lock,
    count_crawl_dirs,
    create_session_record,
    drain_events,
    elapsed_time_display,
    ensure_within_root,
    find_latest_crawl_dir,
    find_ready_download_in_session,
    format_eta_seconds,
    format_status_row,
    format_status_url_preview,
    generate_crawl_id,
    get_active_job_snapshot,
    is_text_previewable,
    job_state_from_event,
    latest_session_id,
    list_generated_files,
    normalize_event_urls,
    normalize_session_records,
    preview_created_timestamp,
    read_recent_lines,
    read_text_preview,
    request_cancel,
    serialize_session_records,
    session_dir,
    session_exists,
    session_time_remaining,
    should_show_portfolio_modal,
    start_crawl_job,
    touch_session,
    validate_safe_id,
)

_URL_RE = re.compile(r"https?://[^\s<>\"]+")
_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DOWNLOADS_REFRESH_INTERVAL = "7s"
_GENERATED_FILES_CACHE_TTL_SECONDS = 2.0
_DIALOG_PLACEHOLDER_TITLE = " "
_DIALOG_LOAD_SESSION_TITLE = "Load Session"
_HOURS_PER_DAY = 24
_ICON_BUTTON_WIDTH_PX = 44
_LIVE_AREA_REFRESH_INTERVAL = "3s"
_PROGRESS_CHART_HEIGHT = 220
_PACE_CHART_HEIGHT = 180
_CHART_CUMULATIVE_TITLE_KEYS = {
    PROGRESS_CHART_TIME_UNIT_SECOND: "CHART_CUMULATIVE_TITLE_SECOND",
    PROGRESS_CHART_TIME_UNIT_MINUTE: "CHART_CUMULATIVE_TITLE_MINUTE",
    PROGRESS_CHART_TIME_UNIT_HOUR: "CHART_CUMULATIVE_TITLE_HOUR",
}
_CHART_TIME_UNIT_KEYS = {
    PROGRESS_CHART_TIME_UNIT_SECOND: "CHART_TIME_UNIT_SECOND",
    PROGRESS_CHART_TIME_UNIT_MINUTE: "CHART_TIME_UNIT_MINUTE",
    PROGRESS_CHART_TIME_UNIT_HOUR: "CHART_TIME_UNIT_HOUR",
}
_CHART_COLOR_DISCOVERED = "#FAFAFA"
_CHART_COLOR_SUCCESSFUL = "#21C354"
_CHART_COLOR_FAILED = "#FF4B4B"
_CHART_COLOR_LIMIT = "#FACA2B"
_CHART_AREA_OPACITY = 0.45
_CHART_LIMIT_LINE_WIDTH = 2.0
_CHART_LEGEND_ORIENT = "bottom"
_AUTHOR_NAME = "Danang Prakoso"
_AUTHOR_LINKEDIN_URL = "https://www.linkedin.com/in/prakosd"
_PROJECT_GITHUB_URL = "https://github.com/prakosd/rag-playground"
_README_URL = "https://github.com/prakosd/crawl4md/blob/master/README.md"
_STREAMLIT_README_URL = "https://github.com/prakosd/crawl4md/blob/master/apps/streamlit/README.md"
_LINKEDIN_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA1MTIg"
    "NTEyJz48cmVjdCB3aWR0aD0nNTEyJyBoZWlnaHQ9JzUxMicgcng9JzcyJyBmaWxsPScjMEE3"
    "RUI3Jy8+PGNpcmNsZSBjeD0nMTQyJyBjeT0nMTQyJyByPSc0NCcgZmlsbD0nd2hpdGUnLz48"
    "cmVjdCB4PScxMDgnIHk9JzIwMicgd2lkdGg9JzY4JyBoZWlnaHQ9JzIxNCcgcng9JzEyJyBm"
    "aWxsPSd3aGl0ZScvPjxwYXRoIGZpbGw9J3doaXRlJyBkPSdNMjA1IDIwMmg2N3YzMWMxNS0y"
    "MyA0MC0zNSA3Mi0zNSA0OCAwIDgwIDMyIDgwIDEwMXYxMTdoLTY5VjMwN2MwLTM1LTEzLTUy"
    "LTQwLTUyLTI4IDAtNDIgMjAtNDIgNTh2MTAzaC02OHonLz48L3N2Zz4="
)
_GITHUB_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA5OCA5"
    "Nic+PHBhdGggZmlsbD0nYmxhY2snIGZpbGwtcnVsZT0nZXZlbm9kZCcgZD0nTTQ4LjkgMEMyMS45"
    "IDAgMCAyMiAwIDQ5LjFjMCAyMS43IDE0IDQwLjEgMzMuNSA0Ni42IDIuNS41IDMuMy0xLjEgMy4z"
    "LTIuNCAwLTEuMi0uMS01LjItLjEtOS40LTEzLjYgMy0xNi41LTUuOS0xNi41LTUuOS0yLjIt"
    "NS43LTUuNC03LjItNS40LTcuMi00LjQtMyAuMy0zIC4zLTMgNC45LjMgNy41IDUuMSA3LjUgNS4x"
    "IDQuMyA3LjUgMTEuNCA1LjMgMTQuMiA0LjEuNC0zLjIgMS43LTUuMyAzLjEtNi41LTEwLjktMS4y"
    "LTIyLjMtNS41LTIyLjMtMjQuNCAwLTUuNCAxLjktOS44IDUtMTMuMi0uNS0xLjItMi4yLTYuMy41"
    "LTEzIDAgMCA0LjEtMS4zIDEzLjQgNSAzLjktMS4xIDgtMS42IDEyLjItMS42czguMy42IDEyLjIg"
    "MS42YzkuMy02LjMgMTMuNC01IDEzLjQtNSAyLjcgNi43IDEgMTEuOC41IDEzIDMuMSAzLjQgNSA3"
    "LjggNSAxMy4yIDAgMTguOS0xMS41IDIzLjEtMjIuNCAyNC40IDEuOCAxLjYgMy4zIDQuNiAzLjMg"
    "OS4zIDAgNi43LS4xIDEyLjEtLjEgMTMuOCAwIDEuMy45IDIuOSAzLjQgMi40Qzg0IDg5LjEgOTgg"
    "NzAuNyA5OCA0OS4xIDk4IDIyIDc2IDAgNDguOSAweicgY2xpcC1ydWxlPSdldmVub2RkJy8+"
    "PC9zdmc+"
)
_AUTHOR_PHOTO_URL = (
    "https://media.licdn.com/dms/image/v2/D5635AQFefjHsJTUdIA/"
    "profile-framedphoto-shrink_400_400/B56Zgrsi34G4Ag-/0/1753079754750"
    "?e=1780549200&v=beta&t=sL7UhTUKZUnpSGqaC8UGkKl-yGnQz8XV5UqwLfDwp3o"
)
_PREVIEW_DIALOG_WIDTH = "large"
# Adjust this percentage to resize the preview modal relative to the viewport.
_PREVIEW_DIALOG_VIEWPORT_PERCENT = 70
_PREVIEW_DIALOG_VIEWPORT_WIDTH = f"{_PREVIEW_DIALOG_VIEWPORT_PERCENT}vw"
_PREVIEW_DIALOG_VIEWPORT_HEIGHT = f"{_PREVIEW_DIALOG_VIEWPORT_PERCENT}vh"
_PREVIEW_DIALOG_SCOPE_CLASS = "crawl4md-preview-dialog-scope"
_PREVIEW_LIMIT_BYTES = 256 * 1024
_PREVIEW_LIMIT_KIB = _PREVIEW_LIMIT_BYTES // 1024
_UTC_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_DEFAULT_LANGUAGE = DEFAULT_SESSION_LANGUAGE
_TOAST_PAGE_SUCCESS_ICON = "✅"
_TOAST_PAGE_FAIL_ICON = "❌"
_TOAST_PAGE_DISCOVERED_ICON = "🔎"
_CREATE_TOAST_STATE = "_create_toast"
_EXTEND_TOAST_STATE = "_extend_toast"
_LOAD_TOAST_STATE = "_load_toast"
_SWITCH_TOAST_STATE = "_switch_toast"
_EXTEND_TOAST_SUCCESS = "success"
_EXTEND_TOAST_FAILED = "failed"
_STATE_CANCEL_REQUESTED = "cancel_requested"
_STATE_CANCELLED = "cancelled"
_STATE_COMPLETED = "completed"
_STATE_FAILED = "failed"
_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_STATE_STOPPED = "stopped"
_REFRESH_FORM_STATES = {
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_STOPPED,
}
_TERMINAL_STATES = {_STATE_COMPLETED, _STATE_FAILED, _STATE_STOPPED}
_FORM_MAX_WIDTH_PX = 980
_PORTFOLIO_MODAL_COMPONENT_KEY = "portfolio_modal"
_PORTFOLIO_MODAL_FIRST_DELAY_SECONDS = 60
_PORTFOLIO_MODAL_REPEAT_DAYS = 7
_PORTFOLIO_MODAL_REPEAT_HOURS = _HOURS_PER_DAY * _PORTFOLIO_MODAL_REPEAT_DAYS
_PORTFOLIO_MODAL_LAST_SHOWN_FIELD = "portfolio_modal_last_shown_at"
_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD = "portfolio_modal_last_dismissed_at"
_STATUS_ROW_STYLE = "display:flex;justify-content:space-between;font-size:0.875rem;opacity:1"
_STATUS_NEXT_ROW_STYLE = f"{_STATUS_ROW_STYLE};padding-bottom:1rem"
_SESSION_STORAGE_COMPONENT_KEY = "browser_session_storage"
_SESSION_RECORDS_CACHE_STATE = "normalized_session_records_cache"
_SESSION_RECORDS_CACHE_MAX_ENTRIES = 8
_SESSION_RECORDS_FIELD = "sessions"
_SESSION_ID_FIELD = "session_id"
_SESSION_CREATED_AT_FIELD = "created_at"
_SESSION_LANGUAGE_FIELD = "language"
_SESSION_STORAGE_KEY = "crawl4md.streamlit.sessions.v1"
_SESSION_SELECTED_ID_FIELD = "selected_session_id"
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
    const pendingNeedWrite = pendingRecords.some(r => !storedRecords.some(s => s.session_id === r.session_id))
    if (hasPendingRecords && pendingNeedWrite && storedPending) {
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

_PORTFOLIO_MODAL_HTML = """
<div id="crawl4md-portfolio-modal-root"></div>
"""

_PORTFOLIO_MODAL_CSS = """
:host {
    font-family: var(--st-font, "Source Sans Pro", sans-serif);
}

#crawl4md-portfolio-modal-root {
    display: contents;
}

.portfolio-modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(17, 24, 39, 0.48);
    backdrop-filter: blur(2px);
}

.portfolio-modal-overlay[hidden] {
    display: none;
}

.portfolio-modal-panel {
    position: relative;
    width: min(560px, calc(100vw - 32px));
    max-height: min(82vh, 720px);
    overflow: auto;
    box-sizing: border-box;
    padding: 24px;
    color: var(--st-text-color, #111827);
    background: var(--st-background-color, #ffffff);
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-base-radius, 8px);
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.28);
}

.portfolio-modal-close {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-button-radius, 8px);
    color: var(--st-text-color, #111827);
    background: var(--st-secondary-background-color, #f3f4f6);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
}

.portfolio-modal-header {
    display: flex;
    gap: 16px;
    align-items: center;
    padding-right: 34px;
}

.portfolio-modal-avatar {
    width: 84px;
    height: 84px;
    flex: 0 0 auto;
    object-fit: cover;
    border-radius: 50%;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
}

.portfolio-modal-title {
    margin: 0;
    color: var(--st-heading-color, var(--st-text-color, #111827));
    font: 700 1.35rem/1.25 var(--st-heading-font, var(--st-font, sans-serif));
}

.portfolio-modal-kicker {
    margin: 6px 0 0;
    color: var(--st-text-color, #111827);
    opacity: 0.72;
    font-size: 0.95rem;
}

.portfolio-modal-copy {
    margin: 18px 0 0;
    font-size: 0.98rem;
    line-height: 1.6;
}

.portfolio-modal-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    margin-top: 20px;
}

.portfolio-modal-link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-link:hover {
    text-decoration: underline;
}

.portfolio-modal-doc-link {
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-doc-link:hover {
    text-decoration: underline;
}

.portfolio-modal-icon-image {
    width: 22px;
    height: 22px;
    flex: 0 0 auto;
    object-fit: contain;
}

@media (max-width: 520px) {
    .portfolio-modal-panel {
        padding: 20px;
    }

    .portfolio-modal-header {
        align-items: flex-start;
    }

    .portfolio-modal-avatar {
        width: 64px;
        height: 64px;
    }
}
"""

_PORTFOLIO_MODAL_JS = """
const MODAL_VISIBLE_CLASS = "is-visible"

function readPayload(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) return { version: 1, sessions: [] }
        const parsed = JSON.parse(rawValue)
        if (Array.isArray(parsed)) return { version: 1, sessions: parsed }
        if (parsed && typeof parsed === "object") return parsed
    } catch {
        return { version: 1, sessions: [] }
    }
    return { version: 1, sessions: [] }
}

function utcNow() {
    return new Date().toISOString().replace(".000Z", "Z")
}

function writeTimestamp(storageKey, field, value) {
    if (!storageKey || !field) return
    try {
        const payload = readPayload(storageKey)
        payload.version = 1
        payload[field] = value
        window.localStorage.setItem(storageKey, JSON.stringify(payload))
    } catch {
        return
    }
}

function appendText(parent, tagName, className, text) {
    const element = document.createElement(tagName)
    element.className = className
    element.textContent = text || ""
    parent.appendChild(element)
    return element
}

function appendLink(parent, href, label, iconUrl, iconClass) {
    const link = document.createElement("a")
    link.className = iconClass ? `portfolio-modal-link ${iconClass}` : "portfolio-modal-link"
    link.href = href || "#"
    link.target = "_blank"
    link.rel = "noopener noreferrer"
    const icon = document.createElement("img")
    icon.className = iconClass
        ? `portfolio-modal-icon-image ${iconClass}`
        : "portfolio-modal-icon-image"
    icon.setAttribute("aria-hidden", "true")
    icon.alt = ""
    icon.src = iconUrl || ""
    link.appendChild(icon)
    link.appendChild(document.createTextNode(label || ""))
    parent.appendChild(link)
}

const instances = new WeakMap()

export default function (component) {
    const { data, parentElement } = component
    const root = parentElement.querySelector("#crawl4md-portfolio-modal-root")
    if (!root) return

    let instance = instances.get(parentElement)
    if (!instance) {
        instance = { timer: null, open: false, overlay: null, onKeyDown: null }
        instances.set(parentElement, instance)
    }

    if (data.shouldShow !== true) {
        if (instance.timer) window.clearTimeout(instance.timer)
        if (instance.onKeyDown) document.removeEventListener("keydown", instance.onKeyDown)
        root.innerHTML = ""
        instance.timer = null
        instance.open = false
        instance.overlay = null
        instance.onKeyDown = null
        return
    }

    if (instance.overlay) {
        if (!root.contains(instance.overlay)) root.appendChild(instance.overlay)
        return
    }

    root.innerHTML = ""

    const overlay = document.createElement("div")
    overlay.className = "portfolio-modal-overlay"
    overlay.hidden = true

    const panel = document.createElement("section")
    panel.className = "portfolio-modal-panel"
    panel.setAttribute("role", "dialog")
    panel.setAttribute("aria-modal", "true")
    panel.setAttribute("aria-labelledby", "portfolio-modal-title")

    const closeButton = document.createElement("button")
    closeButton.className = "portfolio-modal-close"
    closeButton.type = "button"
    closeButton.setAttribute("aria-label", data.closeLabel || "Close")
    closeButton.textContent = "x"
    panel.appendChild(closeButton)

    const header = document.createElement("div")
    header.className = "portfolio-modal-header"
    const image = document.createElement("img")
    image.className = "portfolio-modal-avatar"
    image.src = data.photoUrl || ""
    image.alt = data.photoAlt || ""
    header.appendChild(image)
    const headerText = document.createElement("div")
    const title = appendText(headerText, "h2", "portfolio-modal-title", data.title)
    title.id = "portfolio-modal-title"
    appendText(headerText, "p", "portfolio-modal-kicker", data.tagline)
    header.appendChild(headerText)
    panel.appendChild(header)

    appendText(panel, "p", "portfolio-modal-copy", data.body)
    appendText(panel, "p", "portfolio-modal-copy", data.cta)

    const docLinks = document.createElement("p")
    docLinks.className = "portfolio-modal-copy"
    const readmeLink = document.createElement("a")
    readmeLink.className = "portfolio-modal-doc-link"
    readmeLink.href = data.readmeUrl || "#"
    readmeLink.target = "_blank"
    readmeLink.rel = "noopener noreferrer"
    readmeLink.textContent = data.readmeLabel || ""
    const sep = document.createTextNode(" \u00b7 ")
    const stReadmeLink = document.createElement("a")
    stReadmeLink.className = "portfolio-modal-doc-link"
    stReadmeLink.href = data.streamlitReadmeUrl || "#"
    stReadmeLink.target = "_blank"
    stReadmeLink.rel = "noopener noreferrer"
    stReadmeLink.textContent = data.streamlitReadmeLabel || ""
    docLinks.appendChild(readmeLink)
    docLinks.appendChild(sep)
    docLinks.appendChild(stReadmeLink)
    panel.appendChild(docLinks)

    const actions = document.createElement("div")
    actions.className = "portfolio-modal-actions"
    appendLink(actions, data.linkedinUrl, data.linkedinLabel, data.linkedinIconUrl, "linkedin")
    appendLink(actions, data.githubUrl, data.githubLabel, data.githubIconUrl, "github")
    panel.appendChild(actions)
    overlay.appendChild(panel)
    root.appendChild(overlay)

    function dismiss() {
        if (!instance.open) return
        writeTimestamp(data.storageKey, data.lastDismissedField, utcNow())
        overlay.classList.remove(MODAL_VISIBLE_CLASS)
        overlay.hidden = true
        instance.open = false
        document.removeEventListener("keydown", onKeyDown)
    }

    function onKeyDown(event) {
        if (event.key === "Escape") dismiss()
    }

    instance.overlay = overlay
    instance.onKeyDown = onKeyDown

    overlay.addEventListener("click", event => {
        if (event.target === overlay) dismiss()
    })
    closeButton.addEventListener("click", dismiss)

    const delayMs = Math.max(0, Number(data.delaySeconds || 0)) * 1000
    instance.timer = window.setTimeout(() => {
        instance.timer = null
        overlay.hidden = false
        overlay.classList.add(MODAL_VISIBLE_CLASS)
        instance.open = true
        writeTimestamp(data.storageKey, data.lastShownField, utcNow())
        document.addEventListener("keydown", onKeyDown)
        closeButton.focus()
    }, delayMs)

    return () => {
        if (instance.timer) window.clearTimeout(instance.timer)
        document.removeEventListener("keydown", onKeyDown)
        root.innerHTML = ""
        instances.delete(parentElement)
    }
}
"""


st.set_page_config(
    page_title="crawl4md — Website Crawler",
    page_icon=":material/travel_explore:",
    layout="wide",
)


_SESSION_STORAGE_COMPONENT = component_v2(
    "crawl4md_session_storage",
    html=_SESSION_STORAGE_HTML,
    js=_SESSION_STORAGE_JS,
)

_PORTFOLIO_MODAL_COMPONENT = component_v2(
    "crawl4md_portfolio_modal",
    html=_PORTFOLIO_MODAL_HTML,
    css=_PORTFOLIO_MODAL_CSS,
    js=_PORTFOLIO_MODAL_JS,
)


@st.cache_resource(show_spinner=False)
def _run_startup_cleanup(active_session_ids: tuple[str, ...]) -> None:
    cleanup_old_sessions_with_lock(_SESSIONS_ROOT, active_session_ids=active_session_ids)


def _init_state() -> None:
    st.session_state.setdefault("session_id", "")
    st.session_state.setdefault("browser_session_records", [])
    st.session_state.setdefault("browser_sessions_hydrated", False)
    st.session_state.setdefault("pending_browser_session_records", [])
    st.session_state.setdefault("pending_bootstrap_session_id", "")
    st.session_state.setdefault("session_storage_write_failed", False)
    st.session_state.setdefault("preferred_session_id", "")
    st.session_state.setdefault("pending_selected_session_id", "")
    st.session_state.setdefault("session_ids_to_purge", [])
    st.session_state.setdefault("job", None)
    st.session_state.setdefault("job_state", _STATE_IDLE)
    st.session_state.setdefault("crawl_id", "")
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("latest_event", {})
    st.session_state.setdefault("progress_chart_history", [])
    st.session_state.setdefault("active_output_dir", "")
    st.session_state.setdefault("started_at", None)
    st.session_state.setdefault("last_elapsed", "")
    st.session_state.setdefault("activity_log_size", DEFAULT_ACTIVITY_LOG_SIZE)
    st.session_state.setdefault("activity_log_latest_line", None)
    st.session_state.setdefault("preview_file_relative_path", "")
    st.session_state.setdefault("form_defaults", default_form_values())
    st.session_state.setdefault("stop_confirmation_open", False)
    st.session_state.setdefault("session_load_dialog_open", False)
    st.session_state.setdefault("_load_session_enter", False)
    st.session_state.setdefault("language", _DEFAULT_LANGUAGE)
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_SHOWN_FIELD, "")
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD, "")
    st.session_state.setdefault(_SESSION_RECORDS_CACHE_STATE, {})


def _session_records_cache_key(payload: object) -> tuple[tuple[str, str, str, str], ...]:
    raw_records = (
        payload.get(_SESSION_RECORDS_FIELD, []) if isinstance(payload, Mapping) else payload
    )
    if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Iterable):
        return ()

    key_parts: list[tuple[str, str, str, str]] = []
    for raw_record in raw_records:
        if isinstance(raw_record, SessionRecord):
            key_parts.append(
                (
                    "record",
                    raw_record.session_id,
                    raw_record.created_at.isoformat(),
                    raw_record.language,
                )
            )
            continue
        if isinstance(raw_record, Mapping):
            key_parts.append(
                (
                    "mapping",
                    str(raw_record.get(_SESSION_ID_FIELD, "")),
                    str(raw_record.get(_SESSION_CREATED_AT_FIELD, "")),
                    str(raw_record.get(_SESSION_LANGUAGE_FIELD, "")),
                )
            )
            continue
        key_parts.append(("other", repr(raw_record), "", ""))
    return tuple(key_parts)


def _cached_normalize_session_records(payload: object) -> list[SessionRecord]:
    cache_key = _session_records_cache_key(payload)
    cache = st.session_state.get(_SESSION_RECORDS_CACHE_STATE)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_SESSION_RECORDS_CACHE_STATE] = cache
    cached_records = cache.get(cache_key)
    if cached_records is not None:
        return list(cached_records)

    records = normalize_session_records(payload)
    if len(cache) >= _SESSION_RECORDS_CACHE_MAX_ENTRIES:
        cache.clear()
    cache[cache_key] = tuple(records)
    return records


@st.cache_data(ttl=_GENERATED_FILES_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_list_generated_files(
    session_root: str,
    search_root: str,
    download_limit_bytes: int,
    cache_token: tuple[float, int],
) -> list[GeneratedFile]:
    return list_generated_files(
        Path(session_root),
        Path(search_root),
        download_limit_bytes=download_limit_bytes,
    )


@st.cache_data(ttl=_GENERATED_FILES_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_download_tree(files: tuple[GeneratedFile, ...]) -> dict[str, Any]:
    return build_download_tree(list(files))


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
    result = _SESSION_STORAGE_COMPONENT(
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
    if pending and stored_payload is not None:
        stored_ids = {
            record.session_id for record in _cached_normalize_session_records(stored_payload)
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


def _normalize_language(value: object) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in CATALOG else _DEFAULT_LANGUAGE


def _language_widget_key() -> str:
    session_id = str(st.session_state.get("session_id", "")).strip()
    return f"language_selector_{session_id or 'bootstrap'}"


def _sync_language_widget_state() -> str:
    widget_key = _language_widget_key()
    language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.session_state.language = language
    return widget_key


def _select_session_id(session_id: str, *, restore_language: bool = True) -> None:
    if not session_id:
        return
    records = _browser_session_records()
    known_ids = {record.session_id for record in records}
    if session_id not in known_ids:
        return
    if st.session_state.session_id != session_id:
        st.session_state.preview_file_relative_path = ""
        st.session_state.events = []
        st.session_state.latest_event = {}
        st.session_state.progress_chart_history = []
        st.session_state.active_output_dir = ""
        st.session_state.activity_log_latest_line = None
        st.session_state.last_elapsed = ""
        st.session_state.job = None
        st.session_state.job_state = _STATE_IDLE
        st.session_state.started_at = None
        st.session_state.prev_successful_pages = 0
        st.session_state.prev_failed_pages = 0
        st.session_state.prev_discovered_pages = 0
        # Persist the newly selected session id back to browser storage only on change.
        st.session_state.pending_selected_session_id = session_id
    st.session_state.session_id = session_id
    st.session_state.preferred_session_id = session_id
    if not restore_language:
        return
    for record in records:
        if record.session_id == session_id:
            st.session_state.language = _normalize_language(record.language)
            break


def _commit_session_record(record: SessionRecord) -> None:
    """Merge *record* into browser session state and stage it for localStorage write."""
    records = _cached_normalize_session_records(
        [
            *serialize_session_records(_browser_session_records()),
            *serialize_session_records([record]),
        ]
    )
    pending_records = _cached_normalize_session_records(
        [
            *st.session_state.pending_browser_session_records,
            *serialize_session_records([record]),
        ]
    )
    st.session_state.browser_session_records = records
    st.session_state.pending_browser_session_records = serialize_session_records(pending_records)
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False


def _create_new_session() -> None:
    record = create_session_record()
    st.session_state.language = record.language
    _commit_session_record(record)
    _select_session_id(record.session_id)
    st.session_state[_CREATE_TOAST_STATE] = True
    st.rerun()


def _register_and_select_session(session_id: str) -> None:
    """Register an externally known session into local browser records and select it."""
    mtime = session_dir(_SESSIONS_ROOT, session_id).stat().st_mtime
    created_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
    touch_session(_SESSIONS_ROOT, session_id)
    current_language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    record = create_session_record(session_id=session_id, language=current_language, now=created_at)
    _commit_session_record(record)
    st.session_state.session_load_dialog_open = False
    st.session_state[_LOAD_TOAST_STATE] = record.session_id
    _select_session_id(record.session_id, restore_language=False)
    st.rerun()


def _on_load_session_dismiss() -> None:
    st.session_state.session_load_dialog_open = False
    st.session_state["_load_session_enter"] = False


@st.dialog(_DIALOG_LOAD_SESSION_TITLE, width="small", on_dismiss=_on_load_session_dismiss)
def _load_session_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _on_input_commit() -> None:
        st.session_state["_load_session_enter"] = True

    session_id_input = st.text_input(
        label=strings["DIALOG_LOAD_SESSION_ID_LABEL"],
        placeholder=strings["DIALOG_LOAD_SESSION_ID_PLACEHOLDER"],
        help=strings["DIALOG_LOAD_SESSION_ID_HELP"],
        key="load_session_id_input",
        on_change=_on_input_commit,
    )
    error_slot = st.empty()
    cancel_col, _, load_col = st.columns([2, 5, 3])
    with cancel_col:
        if st.button(strings["DIALOG_LOAD_BTN_CANCEL"], key="load_session_cancel"):
            st.session_state["_load_session_enter"] = False
            st.session_state.session_load_dialog_open = False
            st.rerun()
    with load_col, st.container(horizontal_alignment="right"):
        load_clicked = st.button(
            strings["DIALOG_LOAD_BTN_LOAD"],
            type="primary",
            icon=":material/folder_open:",
            key="load_session_confirm",
        )
    enter_submitted = st.session_state.get("_load_session_enter", False)
    st.session_state["_load_session_enter"] = False
    if load_clicked or enter_submitted:
        stripped = session_id_input.strip()
        if not stripped:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        try:
            validate_safe_id(stripped)
        except ValueError:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        known_ids = {r.session_id for r in _browser_session_records()}
        if stripped in known_ids:
            st.session_state[_SWITCH_TOAST_STATE] = stripped
            st.session_state.session_load_dialog_open = False
            _select_session_id(stripped)
            st.rerun()
        if not session_exists(_SESSIONS_ROOT, stripped):
            error_slot.error(strings["DIALOG_LOAD_SESSION_NOT_FOUND"].format(id=stripped))
            return
        _register_and_select_session(stripped)


def _ensure_selected_session() -> None:
    records = _browser_session_records()
    if records:
        known_ids = {record.session_id for record in records}
        preferred_session_id = str(st.session_state.get("preferred_session_id", ""))
        current_session_id = str(st.session_state.get("session_id", ""))
        selected_session_id = current_session_id
        if preferred_session_id in known_ids:
            selected_session_id = preferred_session_id
        elif current_session_id not in known_ids:
            selected_session_id = latest_session_id(records)
        restore_language = (
            selected_session_id != current_session_id
            or str(st.session_state.get("language", "")).strip().upper() not in CATALOG
        )
        _select_session_id(
            selected_session_id,
            restore_language=restore_language,
        )
        return

    record = create_session_record()
    st.session_state.browser_session_records = [record]
    st.session_state.pending_browser_session_records = serialize_session_records([record])
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False
    _select_session_id(record.session_id)
    st.rerun()


def _on_language_change(widget_key: str) -> None:
    new_lang = _normalize_language(st.session_state.get(widget_key, _DEFAULT_LANGUAGE))
    st.session_state.language = new_lang
    session_id = st.session_state.session_id
    records = _browser_session_records()
    updated = [
        SessionRecord(r.session_id, r.created_at, new_lang) if r.session_id == session_id else r
        for r in records
    ]
    st.session_state.browser_session_records = updated
    updated_record = next((r for r in updated if r.session_id == session_id), None)
    if updated_record is not None:
        pending = _cached_normalize_session_records(
            [
                *st.session_state.pending_browser_session_records,
                *serialize_session_records([updated_record]),
            ]
        )
        st.session_state.pending_browser_session_records = serialize_session_records(pending)


def _session_options() -> list[str]:
    return [record.session_id for record in _browser_session_records()]


def _session_selector_index(options: list[str]) -> int:
    if st.session_state.session_id in options:
        return options.index(st.session_state.session_id)
    return 0


def _job_is_alive(job: CrawlJob | None = None) -> bool:
    current_job = st.session_state.job if job is None else job
    return bool(current_job is not None and current_job.thread.is_alive())


def _drain_job_events(job: CrawlJob | None) -> bool:
    """Apply worker events to the Streamlit-facing crawl state."""
    if job is None:
        return False
    state_changed = False
    for event in drain_events(job):
        event_name = str(event.get("event", ""))
        st.session_state.events.append(event)
        st.session_state.latest_event.update(event)
        chart_history = st.session_state.get("progress_chart_history")
        if not isinstance(chart_history, list):
            chart_history = []
        st.session_state.progress_chart_history = append_live_progress_sample(
            chart_history,
            event,
            started_at=st.session_state.started_at,
        )
        output_dir = str(event.get("output_dir", ""))
        if output_dir:
            st.session_state.active_output_dir = output_dir
        next_state = job_state_from_event(event_name)
        # Keep the UI in Stop-pending state if older worker events arrive late.
        if st.session_state.job_state == _STATE_CANCEL_REQUESTED and next_state in {
            _STATE_RUNNING,
            _STATE_CANCEL_REQUESTED,
        }:
            next_state = _STATE_CANCEL_REQUESTED
        elif next_state == _STATE_CANCELLED:
            next_state = _STATE_STOPPED
        if next_state != st.session_state.job_state:
            state_changed = True
        st.session_state.job_state = next_state
        if next_state in _TERMINAL_STATES:
            started_at = st.session_state.started_at
            if started_at is not None:
                elapsed = datetime.now(timezone.utc) - started_at
                st.session_state.last_elapsed = str(elapsed).split(".")[0]
            st.session_state.started_at = None
            st.session_state.job = None
            st.session_state.form_defaults = default_form_values()
    return state_changed


def _reattach_selected_session_job() -> None:
    """Restore a running crawl job from the process-local registry after browser refresh.

    Called after session selection so that `st.session_state.session_id` is already set.
    Does nothing if a job is already attached to this Streamlit session.
    """
    if st.session_state.job is not None:
        return
    session_id = st.session_state.session_id
    if not session_id:
        return
    snapshot = get_active_job_snapshot(session_id)
    if snapshot is None:
        return
    st.session_state.job = snapshot.job
    st.session_state.crawl_id = snapshot.crawl_id
    st.session_state.job_state = snapshot.job_state
    st.session_state.started_at = snapshot.started_at
    st.session_state.activity_log_size = snapshot.activity_log_size
    st.session_state.latest_event = dict(snapshot.latest_event)
    st.session_state.active_output_dir = snapshot.active_output_dir
    # Seed page-count deltas so the first drain doesn't fire spurious toast messages.
    st.session_state.prev_successful_pages = int(snapshot.latest_event.get("successful_pages", 0))
    st.session_state.prev_failed_pages = int(snapshot.latest_event.get("failed_pages", 0))
    st.session_state.prev_discovered_pages = int(
        snapshot.latest_event.get("queued_discovered_urls", 0)
    )
    st.session_state.progress_chart_history = []
    if snapshot.latest_event:
        st.session_state.progress_chart_history = append_live_progress_sample(
            st.session_state.progress_chart_history,
            snapshot.latest_event,
            started_at=snapshot.started_at,
        )


def _session_root(session_id: str | None = None) -> Path:
    current_session_id = session_id or st.session_state.session_id
    if not current_session_id:
        return _SESSIONS_ROOT
    return session_dir(_SESSIONS_ROOT, current_session_id)


def _start_job(values: dict[str, Any]) -> None:
    # Guard: if the registry already has an alive job for this session (e.g. a
    # second tab opened the same session), reattach instead of starting a new crawl.
    if get_active_job_snapshot(st.session_state.session_id) is not None:
        _reattach_selected_session_job()
        st.rerun()
        return
    try:
        crawler_config, page_config, activity_log_size = build_configs(values)
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    crawl_id = generate_crawl_id(
        seq=count_crawl_dirs(_SESSIONS_ROOT, st.session_state.session_id) + 1
    )
    job = start_crawl_job(
        session_id=st.session_state.session_id,
        crawl_id=crawl_id,
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.job = job
    st.session_state.crawl_id = crawl_id
    st.session_state.job_state = _STATE_RUNNING
    st.session_state.started_at = datetime.now(timezone.utc)
    st.session_state.last_elapsed = ""
    st.session_state.events = []
    st.session_state.latest_event = {"limit": crawler_config.limit}
    st.session_state.progress_chart_history = []
    st.session_state.active_output_dir = ""
    st.session_state.activity_log_size = activity_log_size
    st.session_state.activity_log_latest_line = None
    st.rerun()


def _stop_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    if job is not None and job.thread.is_alive():
        st.session_state.job_state = _STATE_CANCEL_REQUESTED
        request_cancel(job)
        st.rerun()
        return
    st.warning(strings["ERROR_NO_ACTIVE_CRAWL"])


def _on_stop_dismiss() -> None:
    st.session_state.stop_confirmation_open = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_stop_dismiss)
def _stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.markdown(
        """
        <style>
        div[data-testid="stElementContainer"].st-key-stop_cancel_button button {
            background-color: #28a745; border-color: #28a745; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_cancel_button button:hover {
            background-color: #218838; border-color: #1e7e34; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_confirm_button button {
            background-color: #dc3545; border-color: #dc3545; color: white;
        }
        div[data-testid="stElementContainer"].st-key-stop_confirm_button button:hover {
            background-color: #c82333; border-color: #bd2130; color: white;
        }
        div[data-testid="stColumn"]:has(.st-key-stop_confirm_button) [data-testid="stVerticalBlock"] {
            align-items: flex-end;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.write(strings["DIALOG_STOP_BODY"])
    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button(strings["DIALOG_BTN_KEEP"], key="stop_cancel_button"):
            st.session_state.stop_confirmation_open = False
            st.rerun()
    with action_cols[1]:
        if st.button(
            strings["DIALOG_BTN_STOP"],
            type="secondary",
            icon=":material/stop_circle:",
            key="stop_confirm_button",
        ):
            st.session_state.stop_confirmation_open = False
            _stop_job()


def render_progress_and_files(
    processed: int,
    successful: int,
    failed: int,
    discovered: int,
    limit: int,
    state: str,
) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    denominator = discovered if discovered > 0 else max(limit, 1)
    covered_unique_pages = min(processed, denominator)
    progress_ratio = min(max(covered_unique_pages / denominator, 0.0), 1.0)
    progress_pct = progress_ratio * 100
    extra_attempts = max(processed - discovered, 0) if discovered > 0 else 0
    normalized_state = (state or "unknown").strip().lower()
    is_retry_phase = extra_attempts > 0 and normalized_state in {
        _STATE_RUNNING,
        _STATE_CANCEL_REQUESTED,
    }
    state_label = strings["STATE_LABELS"].get(
        normalized_state, normalized_state.replace("_", " ").title()
    )
    state_icon = {
        _STATE_IDLE: "🟡",
        _STATE_RUNNING: "🟢",
        _STATE_FAILED: "🔴",
        _STATE_COMPLETED: "✅",
        _STATE_CANCEL_REQUESTED: "🟠",
        _STATE_STOPPED: "⏹️",
    }.get(normalized_state, "⚠️")
    denominator_label = (
        strings["DENOM_DISCOVERED"].format(n=f"{discovered:,}")
        if discovered > 0
        else strings["DENOM_LIMIT"].format(n=f"{limit:,}")
    )
    processed_delta = (
        strings["METRIC_PROCESSED_DELTA_RETRY"].format(n=f"{extra_attempts:,}")
        if extra_attempts > 0
        else strings["METRIC_PROCESSED_DELTA"].format(n=f"{processed:,}")
    )
    progress_status = (
        strings["PROGRESS_RETRYING"]
        if is_retry_phase
        else f"{progress_pct:.2f}% {strings['PROGRESS_COMPLETE']}"
    )
    attempts_label = strings["PROGRESS_ATTEMPTS"].format(n=f"{processed:,}")

    with st.container():
        st.markdown(
            f'<div style="{_STATUS_ROW_STYLE}">'
            f"<span>📄 {attempts_label} / {denominator_label}</span>"
            f"<span>⏳ {progress_status}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(progress_ratio)

        row1 = st.columns(3)
        row1[0].metric(
            label=strings["METRIC_PROCESSED_LABEL"],
            value=f"{processed:,}",
            delta=processed_delta,
            delta_color="off",
            help=strings["METRIC_PROCESSED_TOOLTIP"],
            border=True,
        )
        row1[1].metric(
            label=strings["METRIC_SUCCESSFUL_LABEL"],
            value=f"{successful:,}",
            delta=strings["METRIC_SUCCESSFUL_DELTA"].format(n=f"{successful:,}"),
            delta_color="normal",
            help=strings["METRIC_SUCCESSFUL_TOOLTIP"],
            border=True,
        )
        row1[2].metric(
            label=strings["METRIC_FAILED_LABEL"],
            value=f"{failed:,}",
            delta=strings["METRIC_FAILED_DELTA"].format(n=f"{failed:,}"),
            delta_color="inverse",
            help=strings["METRIC_FAILED_TOOLTIP"],
            border=True,
        )

        row2 = st.columns(3)
        discovered_remaining = max(limit - discovered, 0)
        limit_reached = discovered >= limit
        limit_status_delta = (
            strings["METRIC_LIMIT_DELTA_REACHED"]
            if limit_reached
            else strings["METRIC_LIMIT_DELTA_MORE"]
        )
        row2[0].metric(
            label=strings["METRIC_DISCOVERED_LABEL"],
            value=f"{discovered:,}",
            delta=strings["METRIC_DISCOVERED_DELTA"].format(
                n=f"{discovered:,}", m=f"{discovered_remaining:,}"
            ),
            delta_color="normal",
            help=strings["METRIC_DISCOVERED_TOOLTIP"],
            border=True,
        )
        row2[1].metric(
            label=strings["METRIC_LIMIT_LABEL"],
            value=f"{limit:,}",
            delta=limit_status_delta,
            delta_color="off",
            help=strings["METRIC_LIMIT_TOOLTIP"],
            border=True,
        )
        with row2[2]:
            st.metric(
                label=f"{state_icon} {strings['METRIC_STATE_WORD']}",
                value=state_label,
                delta=strings["METRIC_STATE_DELTA"],
                delta_color="off",
                help=strings["METRIC_STATE_TOOLTIP"],
                border=True,
            )

        if normalized_state == _STATE_FAILED:
            st.error(strings["BANNER_FAILED"])
        elif normalized_state == _STATE_CANCEL_REQUESTED:
            st.info(strings["BANNER_CANCEL_REQUESTED"])
        elif normalized_state == _STATE_STOPPED:
            st.info(strings["BANNER_STOPPED"])


def _render_status() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    state_changed = _drain_job_events(job)
    if state_changed and st.session_state.job_state in _REFRESH_FORM_STATES:
        st.rerun()
    latest = st.session_state.latest_event
    processed_pages = int(latest.get("processed_pages", 0) or 0)
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    new_success = successful_pages - int(st.session_state.get("prev_successful_pages", 0))
    new_fail = failed_pages - int(st.session_state.get("prev_failed_pages", 0))
    new_discovered = discovered_pages - int(st.session_state.get("prev_discovered_pages", 0))
    if not st.session_state.get("preview_file_relative_path", ""):
        if new_success > 0:
            st.toast(
                strings["TOAST_SUCCESS"].format(n=successful_pages),
                icon=_TOAST_PAGE_SUCCESS_ICON,
            )
        if new_fail > 0:
            st.toast(
                strings["TOAST_FAILED"].format(n=failed_pages),
                icon=_TOAST_PAGE_FAIL_ICON,
            )
        if new_discovered > 0:
            st.toast(
                strings["TOAST_DISCOVERED"].format(n=discovered_pages),
                icon=_TOAST_PAGE_DISCOVERED_ICON,
            )
    st.session_state.prev_successful_pages = successful_pages
    st.session_state.prev_failed_pages = failed_pages
    st.session_state.prev_discovered_pages = discovered_pages
    limit = int(latest.get("limit", DEFAULT_LIMIT) or DEFAULT_LIMIT)

    def _render_status_content() -> None:
        render_progress_and_files(
            processed=processed_pages,
            successful=successful_pages,
            failed=failed_pages,
            discovered=discovered_pages,
            limit=limit,
            state=st.session_state.job_state,
        )

        current_url = str(latest.get("current_url", ""))
        active_urls = normalize_event_urls(latest.get("active_urls", []))
        active_url_count = max(
            int(latest.get("active_url_count", len(active_urls)) or 0),
            len(active_urls),
        )
        max_concurrent = max(
            int(latest.get("max_concurrent", active_url_count or 1) or 1),
            active_url_count,
        )
        elapsed_str = elapsed_time_display(
            started_at=st.session_state.started_at,
            job_state=st.session_state.job_state,
            frozen_elapsed=st.session_state.last_elapsed,
        )
        right = strings["STATUS_ELAPSED"].format(elapsed=elapsed_str) if elapsed_str else ""
        if active_url_count > 1:
            st.markdown(
                format_status_url_preview(
                    label=strings["STATUS_ACTIVE_FETCHES"].format(
                        count=active_url_count,
                        max=max_concurrent,
                    ),
                    urls=active_urls,
                    total_count=active_url_count,
                    right_text=right,
                    style=_STATUS_ROW_STYLE,
                    overflow_template=strings["STATUS_MORE_URLS"],
                ),
                unsafe_allow_html=True,
            )
        elif active_url_count == 1 and active_urls:
            st.markdown(
                format_status_row(
                    url=active_urls[0],
                    url_template=strings["STATUS_CRAWLING"],
                    right_text=right,
                    style=_STATUS_ROW_STYLE,
                ),
                unsafe_allow_html=True,
            )
        elif current_url or elapsed_str:
            st.markdown(
                format_status_row(
                    url=current_url,
                    url_template=strings["STATUS_CRAWLING"],
                    right_text=right,
                    style=_STATUS_ROW_STYLE,
                ),
                unsafe_allow_html=True,
            )

        next_url = str(latest.get("next_url", ""))
        next_urls = normalize_event_urls(latest.get("next_urls", []))
        if not next_urls and next_url:
            next_urls = [next_url]
        next_url_count = max(
            int(latest.get("next_url_count", len(next_urls)) or 0),
            len(next_urls),
        )
        eta_seconds_raw = latest.get("eta_remaining_seconds")
        eta_seconds = float(eta_seconds_raw) if eta_seconds_raw is not None else None
        eta_text = format_eta_seconds(eta_seconds, strings)
        if next_url_count > 1:
            st.markdown(
                format_status_url_preview(
                    label=strings["STATUS_NEXT_FETCHES"].format(count=next_url_count),
                    urls=next_urls,
                    total_count=next_url_count,
                    right_text=eta_text,
                    style=_STATUS_NEXT_ROW_STYLE,
                    overflow_template=strings["STATUS_MORE_URLS"],
                ),
                unsafe_allow_html=True,
            )
        elif next_urls or eta_seconds is not None:
            st.markdown(
                format_status_row(
                    url=next_urls[0] if next_urls else "",
                    url_template=strings["STATUS_NEXT_URL"],
                    right_text=eta_text,
                    style=_STATUS_NEXT_ROW_STYLE,
                ),
                unsafe_allow_html=True,
            )

    _render_status_content()

    if st.session_state.job_state == _STATE_FAILED:
        err = str(latest.get("error", ""))
        if err == PLAYWRIGHT_MISSING_BROWSER_MESSAGE:
            st.error(strings["ERROR_PLAYWRIGHT_MISSING"])
        else:
            st.error(err or strings["ERROR_CRAWL_FAILED_FALLBACK"])


def _active_file_root() -> Path:
    session_folder = _session_root()
    active_output_dir = st.session_state.active_output_dir
    if active_output_dir:
        try:
            return ensure_within_root(session_folder, active_output_dir)
        except ValueError:
            pass
    job = st.session_state.job
    if job is not None and job.session_id == st.session_state.session_id:
        latest = find_latest_crawl_dir(job.output_base)
        if latest is not None:
            return ensure_within_root(session_folder, latest)
        return ensure_within_root(session_folder, job.output_base)
    return session_folder


def _build_cumulative_progress_chart(
    rows: list[dict[str, float]], chart_strings: Mapping[str, str]
) -> alt.LayerChart:
    color_scale = alt.Scale(
        domain=[
            chart_strings["CHART_SERIES_DISCOVERED"],
            chart_strings["CHART_SERIES_SUCCESSFUL"],
            chart_strings["CHART_SERIES_FAILED"],
            chart_strings["CHART_SERIES_LIMIT"],
        ],
        range=[
            _CHART_COLOR_DISCOVERED,
            _CHART_COLOR_SUCCESSFUL,
            _CHART_COLOR_FAILED,
            _CHART_COLOR_LIMIT,
        ],
    )
    color = alt.Color(
        "series:N",
        scale=color_scale,
        legend=alt.Legend(title=None, orient=_CHART_LEGEND_ORIENT),
    )
    x = alt.X("elapsed_time:Q", title="")

    discovered = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_DISCOVERED"]} for row in rows]
            )
        )
        .mark_area(opacity=_CHART_AREA_OPACITY)
        .encode(
            x=x,
            y=alt.Y("discovered_pages:Q", title=""),
            color=color,
        )
    )
    successful = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_SUCCESSFUL"]} for row in rows]
            )
        )
        .mark_area(opacity=_CHART_AREA_OPACITY)
        .encode(
            x=x,
            y=alt.Y("successful_pages:Q", title=""),
            color=color,
        )
    )
    failed = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_FAILED"]} for row in rows]
            )
        )
        .mark_area(opacity=_CHART_AREA_OPACITY)
        .encode(
            x=x,
            y=alt.Y("processed_pages:Q", title=""),
            y2="successful_pages:Q",
            color=color,
        )
    )
    limit = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_LIMIT"]} for row in rows]
            )
        )
        .mark_line(strokeWidth=_CHART_LIMIT_LINE_WIDTH)
        .encode(
            x=x,
            y=alt.Y("page_limit:Q", title=""),
            color=color,
        )
    )

    return alt.layer(discovered, successful, failed, limit).properties(
        height=_PROGRESS_CHART_HEIGHT
    )


def _render_progress_charts() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    live_history = st.session_state.get("progress_chart_history")
    if not isinstance(live_history, list):
        live_history = []

    persisted_history = load_persisted_progress_history(_active_file_root())
    selected_history = prefer_persisted_history(live_history, persisted_history)
    cumulative_rows = prepare_cumulative_chart_rows(selected_history)
    if not cumulative_rows:
        return

    time_unit = select_progress_chart_time_unit(selected_history)
    time_unit_seconds = progress_chart_time_unit_seconds(time_unit)
    time_unit_label = strings[_CHART_TIME_UNIT_KEYS[time_unit]]

    cumulative_chart_rows = prepare_cumulative_chart_display_rows(
        cumulative_rows,
        time_unit_seconds=time_unit_seconds,
    )
    st.caption(strings[_CHART_CUMULATIVE_TITLE_KEYS[time_unit]])
    st.altair_chart(
        _build_cumulative_progress_chart(cumulative_chart_rows, strings),
        use_container_width=True,
    )

    pace_rows = prepare_pace_chart_rows(
        selected_history,
        window_seconds=time_unit_seconds,
    )
    pace_chart_rows = [
        {
            time_unit_label: row["elapsed_seconds"] / time_unit_seconds,
            strings["CHART_SERIES_PACE"]: row["seconds_per_page_attempt"],
        }
        for row in pace_rows
    ]
    st.caption(strings["CHART_PACE_TITLE"])
    st.line_chart(
        pace_chart_rows,
        x=time_unit_label,
        y=strings["CHART_SERIES_PACE"],
        height=_PACE_CHART_HEIGHT,
        x_label="",
        y_label="",
    )


def _linkify_log_line(line: str) -> str:
    escaped = html.escape(line)
    return _URL_RE.sub(
        lambda m: (
            f'<a href="{m.group()}" target="_blank" rel="noopener noreferrer">{m.group()}</a>'
        ),
        escaped,
    )


def _render_activity_log() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    log_path = activity_log_path(_active_file_root())
    max_lines = int(st.session_state.activity_log_size)
    lines = read_recent_lines(log_path, max_lines=max_lines) if log_path else []
    st.session_state.activity_log_latest_line = lines[-1] if lines else None
    if lines:
        rows_html = "".join(
            f"<div style='padding:4px 8px;border-bottom:1px solid rgba(150,150,150,0.35);font-size:14px;font-family:sans-serif'>{_linkify_log_line(line)}</div>"
            for line in reversed(lines)
        )
        with st.expander(strings["ACTIVITY_LOG_HEADER"], expanded=False):
            st.html(
                f"<div style='height:200px;overflow-y:auto;border:1px solid rgba(150,150,150,0.35);border-radius:8px'>{rows_html}</div>"
            )


def _format_preview_timestamp_utc(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(_UTC_DISPLAY_FORMAT)
    except (OverflowError, OSError, ValueError):
        return None


def _on_preview_dismiss() -> None:
    st.session_state.preview_file_relative_path = ""


@st.dialog(
    _DIALOG_PLACEHOLDER_TITLE,
    width=_PREVIEW_DIALOG_WIDTH,
    on_dismiss=_on_preview_dismiss,
)
def _file_preview_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    session_folder = _session_root()
    try:
        file_path = ensure_within_root(session_folder, session_folder / preview_relative_path)
    except ValueError:
        st.session_state.preview_file_relative_path = ""
        return
    file_name = Path(preview_relative_path).name
    st.markdown(
        f"""
        <div class="{_PREVIEW_DIALOG_SCOPE_CLASS}" style="display:none"></div>
        <style>
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) {{
            overflow: hidden !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) > div {{
            align-items: center !important;
            justify-content: center !important;
            padding-top: 0 !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] {{
            width: {_PREVIEW_DIALOG_VIEWPORT_WIDTH} !important;
            max-width: {_PREVIEW_DIALOG_VIEWPORT_WIDTH} !important;
            height: {_PREVIEW_DIALOG_VIEWPORT_HEIGHT} !important;
            max-height: {_PREVIEW_DIALOG_VIEWPORT_HEIGHT} !important;
            margin: 0 !important;
            overflow: hidden !important;
            display: flex !important;
            flex-direction: column !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] > div:nth-child(2) {{
            flex: 1 1 auto !important;
            min-height: 0 !important;
            overflow: hidden !important;
            display: flex !important;
            flex-direction: column !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] > div:nth-child(2) [data-testid="stVerticalBlock"],
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] > div:nth-child(2) [data-testid="stLayoutWrapper"] {{
            flex: 1 1 auto !important;
            min-height: 0 !important;
            display: flex !important;
            flex-direction: column !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [data-testid="stElementContainer"]:has([data-testid="stCode"]) {{
            flex: 1 1 auto !important;
            min-height: 0 !important;
            height: auto !important;
            max-height: 100% !important;
            overflow: hidden !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [data-testid="stElementContainer"]:has([data-testid="stCode"]) [data-testid="stCode"] {{
            height: 100% !important;
            max-height: 100% !important;
            overflow: auto !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [data-testid="stElementContainer"]:has([data-testid="stCode"]) pre {{
            height: 100% !important;
            max-height: 100% !important;
            overflow: auto !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] > div:nth-child(1) {{
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
        }}
        div[data-testid="stDialog"]:has(.{_PREVIEW_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] > div:nth-child(1) > div:first-child {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(file_name)
    if not file_path.exists() or not file_path.is_file():
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    if not is_text_previewable(file_name):
        st.info(strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file_name))
        return
    try:
        current_stat = file_path.stat()
    except OSError:
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    current_size = current_stat.st_size

    path_text = strings["FILES_PREVIEW_PATH"].format(path=preview_relative_path)
    size_text = strings["FILES_PREVIEW_SIZE"].format(size_kib=round(current_size / 1024, 1))
    modified_display = _format_preview_timestamp_utc(current_stat.st_mtime)
    modified_text = (
        strings["FILES_PREVIEW_MODIFIED_AT"].format(value=modified_display)
        if modified_display
        else None
    )

    created_timestamp = preview_created_timestamp(current_stat)
    created_display = _format_preview_timestamp_utc(created_timestamp)
    created_text = (
        strings["FILES_PREVIEW_CREATED_AT"].format(value=created_display)
        if created_display
        else None
    )

    caption_html = (
        f'<div style="{_STATUS_ROW_STYLE}"><span>{path_text}</span><span>{size_text}</span></div>'
    )
    if modified_text and created_text:
        caption_html += (
            f'<div style="{_STATUS_ROW_STYLE}">'
            f"<span>{modified_text}</span><span>{created_text}</span></div>"
        )
    elif modified_text:
        caption_html += f"<div>{modified_text}</div>"
    elif created_text:
        caption_html += f"<div>{created_text}</div>"

    st.caption(caption_html, unsafe_allow_html=True)

    try:
        preview = read_text_preview(file_path, max_bytes=_PREVIEW_LIMIT_BYTES)
    except OSError:
        st.warning(strings["FILES_PREVIEW_READ_ERROR"].format(file=preview_relative_path))
        return

    if preview.text:
        st.code(
            preview.text,
            language="text",
            line_numbers=True,
            wrap_lines=False,
        )
    else:
        st.info(strings["FILES_PREVIEW_EMPTY"].format(file=file_name))
    if preview.truncated:
        st.caption(strings["FILES_PREVIEW_TRUNCATED"].format(limit_kib=_PREVIEW_LIMIT_KIB))


def _render_file_preview_button(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    previewable = is_text_previewable(file.name)
    preview_help = (
        strings["FILES_PREVIEW_HELP"].format(file=file.name)
        if previewable
        else strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file.name)
    )
    if st.button(
        label=strings["FILES_PREVIEW_BUTTON"],
        width=_ICON_BUTTON_WIDTH_PX,
        key=f"preview_{st.session_state.session_id}_{file.relative_path}",
        help=preview_help,
        disabled=not previewable,
    ):
        st.session_state.preview_file_relative_path = file.relative_path
        st.rerun()


def render_generated_file_download(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    try:
        current_size = file.path.stat().st_size
    except OSError:
        return
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        width="content",
        gap="xxsmall",
    ):
        _render_file_preview_button(file)
        if not file.download_allowed or current_size > _DOWNLOAD_LIMIT_BYTES:
            st.button(
                label=f"📄 {file.name}",
                disabled=True,
                help=strings["FILES_DOWNLOAD_TOO_LARGE"].format(file=file.name),
                key=f"download_blocked_{st.session_state.session_id}_{file.relative_path}",
            )
        else:
            mime_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            with file.path.open("rb") as file_obj:
                file_bytes = file_obj.read()
            st.download_button(
                label=f"📄 {file.name}",
                data=file_bytes,
                file_name=file.name,
                mime=mime_type,
                key=f"download_{st.session_state.session_id}_{file.relative_path}",
            )


def render_download_tree(
    tree: Mapping[str, Any], *, allow_crawl_run_folder_collapse: bool = True
) -> None:
    entries = sorted(
        tree.items(), key=lambda item: (not isinstance(item[1], dict), item[0].lower())
    )
    for name, entry in entries:
        if isinstance(entry, dict):
            folder_label = name.removeprefix("crawl_")
            folder_node: Mapping[str, Any] = entry
            if allow_crawl_run_folder_collapse:
                folder_label, folder_node = collapse_crawl_run_folder(name, entry)
            with st.expander(f"📁 {folder_label}"):
                render_download_tree(
                    folder_node,
                    allow_crawl_run_folder_collapse=False,
                )
            continue
        render_generated_file_download(entry)


def _render_ready_result_panel() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_root = _session_root()
    active_output_dir = str(st.session_state.get("active_output_dir", ""))
    ready: ReadyDownload | None = None
    if active_output_dir:
        ready = build_ready_download(
            active_output_dir,
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is None:
        ready = find_ready_download_in_session(
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is not None:
        _render_ready_result(ready, strings)


def _render_ready_result(ready: ReadyDownload, strings: dict[str, Any]) -> None:
    is_zip = ready.file.file_type == "zip"
    subtitle = (
        strings["READY_RESULT_ZIP_SUBTITLE"].format(count=ready.source_count)
        if is_zip
        else strings["READY_RESULT_SINGLE_SUBTITLE"]
    )
    path_parts = ready.file.relative_path.split("/")
    crawl_label = path_parts[0].removeprefix("crawl_") if path_parts else ""
    timestamp = path_parts[1] if len(path_parts) > 1 else ""
    if crawl_label:
        subtitle = f"{subtitle} ({crawl_label})"
    if crawl_label and timestamp:
        download_name = f"{crawl_label}_{timestamp}.{ready.file.file_type}"
    else:
        download_name = ready.file.name
    st.markdown(
        f'<h3 style="margin-bottom:0;padding-bottom:0">{strings["READY_RESULT_HEADER"]}</h3>'
        f'<p style="opacity:0.7;font-size:0.875rem;margin:0 0 0.75rem">'
        f"{subtitle}</p>",
        unsafe_allow_html=True,
    )
    if not ready.file.download_allowed:
        st.warning(strings["READY_RESULT_TOO_LARGE"])
        return
    try:
        file_bytes = ready.file.path.read_bytes()
    except OSError:
        return
    mime_type = mimetypes.guess_type(download_name)[0] or "application/octet-stream"
    st.download_button(
        label=strings["READY_RESULT_DOWNLOAD_BUTTON"],
        data=file_bytes,
        file_name=download_name,
        mime=mime_type,
        key=f"ready_result_{st.session_state.session_id}_{st.session_state.get('crawl_id', '')}",
        use_container_width=True,
    )


def _render_open_preview_dialog(files: list[GeneratedFile]) -> None:
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    file_by_relative_path = {file.relative_path: file for file in files}
    if preview_relative_path not in file_by_relative_path:
        st.session_state.preview_file_relative_path = ""
        return
    _file_preview_dialog()


@st.fragment(run_every=_DOWNLOADS_REFRESH_INTERVAL)
def _render_downloads() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_folder = _session_root()
    session_folder_str = str(session_folder.resolve())
    files = _cached_list_generated_files(
        session_folder_str,
        session_folder_str,
        _DOWNLOAD_LIMIT_BYTES,
        generated_files_cache_token(session_folder),
    )
    download_tree = _cached_download_tree(tuple(files))
    subtitle_text = (
        strings["FILES_DOWNLOADS_IN_PROGRESS"]
        if _job_is_alive(st.session_state.job)
        else strings["FILES_DOWNLOADS_SUBTITLE"]
    )
    st.markdown(
        f'<h3 style="padding-bottom:0">{strings["FILES_DOWNLOADS_SUBHEADER"]}</h3>'
        f'<p style="opacity:0.6;font-size:0.875rem;margin:0 0 1rem">{subtitle_text}</p>',
        unsafe_allow_html=True,
    )
    if files:
        rows = [
            {
                strings["FILES_COL_NAME"]: file.relative_path.removeprefix("crawl_"),
                strings["FILES_COL_TYPE"]: file.file_type,
                strings["FILES_COL_SIZE"]: round(file.size_bytes / (1024 * 1024), 3),
                strings["FILES_COL_MODIFIED"]: file.modified_at.strftime(_UTC_DISPLAY_FORMAT),
            }
            for file in files
        ]
        with st.expander(strings["FILES_HEADER"], expanded=False):
            st.dataframe(rows, hide_index=True, width="stretch")

    if _job_is_alive(st.session_state.job):
        if files:
            with st.expander(strings["FILES_CRAWL_RESULT_LABEL"], expanded=True):
                render_download_tree(download_tree)
    elif session_folder.exists():
        with st.expander(strings["FILES_CRAWL_RESULT_LABEL"], expanded=True):
            render_download_tree(download_tree)

    _render_open_preview_dialog(files)


@st.fragment(run_every=_LIVE_AREA_REFRESH_INTERVAL)
def _render_live_area() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    live_expanded = st.session_state.job_state in {_STATE_RUNNING, _STATE_CANCEL_REQUESTED}
    with st.expander(strings["PROGRESS_EXPANDER_LABEL"], expanded=live_expanded):
        _render_status()
        _render_progress_charts()
        _render_activity_log()


def _render_footer() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    built_by = html.escape(strings["FOOTER_BUILT_BY"].format(author=_AUTHOR_NAME))
    tagline = html.escape(strings["FOOTER_TAGLINE"])
    linkedin_label = html.escape(strings["FOOTER_LINK_LINKEDIN"])
    github_label = html.escape(strings["FOOTER_LINK_GITHUB"])
    linkedin_url = html.escape(_AUTHOR_LINKEDIN_URL, quote=True)
    github_url = html.escape(_PROJECT_GITHUB_URL, quote=True)
    linkedin_icon = html.escape(_LINKEDIN_ICON_DATA_URI, quote=True)
    github_icon = html.escape(_GITHUB_ICON_DATA_URI, quote=True)
    readme_label = html.escape(strings["FOOTER_LINK_README"])
    streamlit_readme_label = html.escape(strings["FOOTER_LINK_STREAMLIT_README"])
    readme_url = html.escape(_README_URL, quote=True)
    streamlit_readme_url = html.escape(_STREAMLIT_README_URL, quote=True)
    st.markdown(
        f"""
        <style>
        .crawl4md-footer {{
            margin: 2.5rem 0 0;
            padding: 1rem 0 0;
            border-top: 1px solid rgba(49, 51, 63, 0.18);
            color: inherit;
            opacity: 0.88;
            font-size: 0.9rem;
        }}
        .crawl4md-footer-inner {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.5rem 0.75rem;
        }}
        .crawl4md-footer-meta {{
            opacity: 0.76;
        }}
        .crawl4md-footer-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            color: inherit;
            text-decoration: none;
            font-weight: 600;
        }}
        .crawl4md-footer-link:hover {{
            text-decoration: underline;
        }}
        .crawl4md-footer-icon-image {{
            width: 1.25rem;
            height: 1.25rem;
            flex: 0 0 auto;
            object-fit: contain;
        }}
        </style>
        <footer class="crawl4md-footer">
            <div class="crawl4md-footer-inner">
                <span>{built_by}</span>
                <span class="crawl4md-footer-meta">{tagline}</span>
                <a class="crawl4md-footer-link" href="{linkedin_url}" target="_blank" rel="noopener noreferrer">
                    <img class="crawl4md-footer-icon-image" src="{linkedin_icon}" alt="" aria-hidden="true">{linkedin_label}
                </a>
                <a class="crawl4md-footer-link" href="{github_url}" target="_blank" rel="noopener noreferrer">
                    <img class="crawl4md-footer-icon-image" src="{github_icon}" alt="" aria-hidden="true">{github_label}
                </a>
                <a class="crawl4md-footer-link" href="{readme_url}" target="_blank" rel="noopener noreferrer">
                    {readme_label}
                </a>
                <a class="crawl4md-footer-link" href="{streamlit_readme_url}" target="_blank" rel="noopener noreferrer">
                    {streamlit_readme_label}
                </a>
            </div>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def _render_portfolio_modal() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    should_show = should_show_portfolio_modal(
        browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
        last_dismissed_at=st.session_state.get(_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD),
        repeat_after_hours=_PORTFOLIO_MODAL_REPEAT_HOURS,
    )
    _PORTFOLIO_MODAL_COMPONENT(
        key=_PORTFOLIO_MODAL_COMPONENT_KEY,
        height=0,
        data={
            "shouldShow": should_show,
            "delaySeconds": _PORTFOLIO_MODAL_FIRST_DELAY_SECONDS,
            "storageKey": _SESSION_STORAGE_KEY,
            "lastShownField": _PORTFOLIO_MODAL_LAST_SHOWN_FIELD,
            "lastDismissedField": _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD,
            "title": strings["PORTFOLIO_MODAL_TITLE"].format(author=_AUTHOR_NAME),
            "tagline": strings["FOOTER_TAGLINE"],
            "body": strings["PORTFOLIO_MODAL_BODY"],
            "cta": strings["PORTFOLIO_MODAL_CTA"],
            "linkedinLabel": strings["PORTFOLIO_MODAL_LINK_LINKEDIN"],
            "githubLabel": strings["PORTFOLIO_MODAL_LINK_GITHUB"],
            "closeLabel": strings["PORTFOLIO_MODAL_CLOSE_LABEL"],
            "photoAlt": strings["PORTFOLIO_MODAL_PHOTO_ALT"].format(author=_AUTHOR_NAME),
            "photoUrl": _AUTHOR_PHOTO_URL,
            "linkedinUrl": _AUTHOR_LINKEDIN_URL,
            "githubUrl": _PROJECT_GITHUB_URL,
            "linkedinIconUrl": _LINKEDIN_ICON_DATA_URI,
            "githubIconUrl": _GITHUB_ICON_DATA_URI,
            "readmeUrl": _README_URL,
            "streamlitReadmeUrl": _STREAMLIT_README_URL,
            "readmeLabel": strings["PORTFOLIO_MODAL_LINK_README"],
            "streamlitReadmeLabel": strings["PORTFOLIO_MODAL_LINK_STREAMLIT_README"],
        },
    )


_init_state()
_mount_session_storage()
strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

# Show deferred "session created" toast only once the storage component has
# confirmed the localStorage write. Firing earlier shows it on an intermediate
# rerun that can be replaced by component callbacks, making the toast disappear.
if (
    st.session_state.get(_CREATE_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    st.session_state.pop(_CREATE_TOAST_STATE)
    st.toast(strings["TOAST_SESSION_CREATED"], icon=_TOAST_PAGE_SUCCESS_ICON)
if st.session_state.get(_LOAD_TOAST_STATE) and not st.session_state.pending_browser_session_records:
    _load_toast_id = st.session_state.pop(_LOAD_TOAST_STATE)
    st.toast(
        strings["TOAST_SESSION_LOADED"].format(id=_load_toast_id), icon=":material/folder_open:"
    )
if (
    st.session_state.get(_SWITCH_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    _switch_toast_id = st.session_state.pop(_SWITCH_TOAST_STATE)
    st.toast(
        strings["DIALOG_LOAD_SESSION_ALREADY_LOADED"].format(id=_switch_toast_id),
        icon=":material/folder_open:",
    )

bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
if bootstrap_state == "hydrating":
    st.title(strings["PAGE_TITLE"])
    st.write(strings["PAGE_SUBTITLE"])
    st.info(strings["SESSION_LOADING"])
    st.stop()

_ensure_selected_session()
bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
language_widget_key = _sync_language_widget_state()
if bootstrap_state != "ready":
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(strings["PAGE_TITLE"])
    st.write(strings["PAGE_SUBTITLE"])
    if bootstrap_state == "storage_error":
        st.error(strings["ERROR_SESSION_STORAGE_WRITE"])
        st.stop()
    st.info(strings["SESSION_LOADING"])
    st.stop()

_reattach_selected_session_job()
_run_startup_cleanup(tuple(set(_session_options()) | active_registry_session_ids()))
_drain_job_events(st.session_state.job)

strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

st.markdown(
    f"""
    <style>
    div[data-testid="stMainBlockContainer"],
    section.main .block-container {{
        max-width: {_FORM_MAX_WIDTH_PX}px !important;
        margin-left: auto;
        margin-right: auto;
    }}
    div[data-testid="stForm"] {{
        max-width: {_FORM_MAX_WIDTH_PX}px;
        margin-left: auto;
        margin-right: auto;
    }}
    h3#form-subheader {{
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }}
    h3#progress {{
        padding-bottom: 0 !important;
    }}
    div[data-testid="stForm"] .stHeading h3 {{
        padding: 0.75rem 0 0 !important;
    }}
    div[class*="st-key-Stop"] button {{
        background-color: #dc2626;
        border-color: #dc2626;
        color: white;
    }}
    div[class*="st-key-Stop"] button:hover {{
        background-color: #b91c1c;
        border-color: #b91c1c;
        color: white;
    }}
    div[data-testid="stToastContainer"] {{
        top: auto !important;
        bottom: 1rem !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(strings["PAGE_TITLE"])
st.write(strings["PAGE_SUBTITLE"])
current_job = st.session_state.job
current_state = st.session_state.job_state
job_alive = _job_is_alive(current_job)
fields_disabled = (
    current_state == _STATE_RUNNING and job_alive
) or current_state == _STATE_CANCEL_REQUESTED
form_expanded = not fields_disabled

session_options = _session_options()
session_controls_col, language_col = st.columns([5, 1], vertical_alignment="top")
with session_controls_col:
    _extend_toast = st.session_state.pop(_EXTEND_TOAST_STATE, None)
    if _extend_toast == _EXTEND_TOAST_SUCCESS:
        st.toast(strings["TOAST_SESSION_EXTENDED"], icon=_TOAST_PAGE_SUCCESS_ICON)
    elif _extend_toast == _EXTEND_TOAST_FAILED:
        st.toast(strings["TOAST_SESSION_EXTEND_FAILED"], icon=_TOAST_PAGE_FAIL_ICON)
    with st.container(gap="xxsmall"):
        with st.container(horizontal=True, vertical_alignment="bottom", gap="xxsmall"):
            with st.container(
                horizontal=True, vertical_alignment="center", width="content", gap="xxsmall"
            ):
                st.markdown(strings["SESSION_SELECTOR_LABEL"])
                selected_session = st.selectbox(
                    label=strings["SESSION_SELECTOR_LABEL"],
                    options=session_options,
                    index=_session_selector_index(session_options),
                    key=f"session_selector_{st.session_state.session_id}",
                    label_visibility="collapsed",
                    width=240,
                    disabled=fields_disabled,
                )
            if st.button(
                "",
                width=_ICON_BUTTON_WIDTH_PX,
                key="session_create_button",
                icon=":material/add:",
                help=strings["SESSION_CREATE_BUTTON_TOOLTIP"],
                disabled=fields_disabled,
            ):
                _create_new_session()
            if st.button(
                "",
                width=_ICON_BUTTON_WIDTH_PX,
                key="session_load_button",
                icon=":material/folder_open:",
                help=strings["SESSION_LOAD_BUTTON_TOOLTIP"],
                disabled=fields_disabled,
            ):
                st.session_state.session_load_dialog_open = True
                st.rerun()
            if st.button(
                "",
                width=_ICON_BUTTON_WIDTH_PX,
                key="session_extend_button",
                icon=":material/more_time:",
                help=strings["SESSION_EXTEND_BUTTON_TOOLTIP"],
                disabled=fields_disabled,
            ):
                try:
                    touch_session(_SESSIONS_ROOT, st.session_state.session_id)
                    st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_SUCCESS
                except (OSError, ValueError):
                    st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_FAILED
                st.rerun()
        days_left, hours_left = session_time_remaining(_SESSIONS_ROOT, st.session_state.session_id)
        if days_left == 0:
            if hours_left == 0:
                expiry_key = "SESSION_EXPIRY_CAPTION_SOON"
            elif hours_left == 1:
                expiry_key = "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR"
            else:
                expiry_key = "SESSION_EXPIRY_CAPTION_HOURS"
        elif hours_left == 0:
            expiry_key = (
                "SESSION_EXPIRY_CAPTION_SINGULAR" if days_left == 1 else "SESSION_EXPIRY_CAPTION"
            )
        elif hours_left == 1:
            expiry_key = (
                "SESSION_EXPIRY_CAPTION_DAY_HOUR"
                if days_left == 1
                else "SESSION_EXPIRY_CAPTION_DAYS_HOUR"
            )
        else:
            expiry_key = (
                "SESSION_EXPIRY_CAPTION_DAY_HOURS"
                if days_left == 1
                else "SESSION_EXPIRY_CAPTION_DAYS_HOURS"
            )
        st.caption(
            strings[expiry_key].format(days=days_left, hours=hours_left)
        )  # one or both kwargs may be unused per key
    if selected_session != st.session_state.session_id:
        _select_session_id(str(selected_session))
        st.rerun()
with language_col, st.container(horizontal_alignment="right"):
    _language_default = (
        _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
        if language_widget_key not in st.session_state
        else None
    )
    st.segmented_control(
        label=strings["LANG_SELECTOR_LABEL"],
        options=list(CATALOG.keys()),
        key=language_widget_key,
        default=_language_default,
        label_visibility="collapsed",
        disabled=fields_disabled,
        on_change=_on_language_change,
        args=(language_widget_key,),
    )

values = render_crawl_form(
    fields_disabled=fields_disabled,
    expanded=form_expanded,
    state=current_state,
    job_alive=job_alive,
    strings=strings,
    defaults=st.session_state.form_defaults,
    activity_log_size=int(st.session_state.activity_log_size),
)
if values["submitted"]:
    st.session_state.stop_confirmation_open = False
    if current_job is not None and current_job.thread.is_alive():
        st.warning(strings["ERROR_CRAWL_ALREADY_RUNNING"])
    else:
        _start_job(values)
elif values["stop_submitted"]:
    st.session_state.stop_confirmation_open = True

if st.session_state.stop_confirmation_open and not job_alive:
    st.session_state.stop_confirmation_open = False

if st.session_state.stop_confirmation_open:
    _stop_confirmation_dialog()

if st.session_state.session_load_dialog_open:
    _load_session_dialog()

_render_ready_result_panel()
st.subheader(strings["PROGRESS_HEADER"])
st.caption(strings["PROGRESS_CAPTION"])
_render_live_area()
_render_downloads()
_render_footer()
_render_portfolio_modal()
