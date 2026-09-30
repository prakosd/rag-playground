"""Shared shell constants extracted from ``streamlit_app.py``.

Scalar constants (page ids, author/footer links, toast icons + state keys, refresh
triggers, portfolio-modal + session-storage keys) used across the shell modules.
Kept dependency-light so every shell module can import it without a cycle.
"""

from __future__ import annotations

from app_support.app_runtime import (
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_STOPPED,
)

_VECTOR_INDEX_PAGE_ID = "vector_index"
_RAG_PAGE_IDS = ("semantic_search", "basic_rag_qa", "conversational_rag")
_DIALOG_LOAD_SESSION_TITLE = "Load Session"
_HOURS_PER_DAY = 24
_AUTHOR_NAME = "Danang Prakoso"
_AUTHOR_LINKEDIN_URL = "https://www.linkedin.com/in/prakosd"
_PROJECT_GITHUB_URL = "https://github.com/prakosd/rag-playground"
_README_URL = "https://github.com/prakosd/rag-playground/blob/master/README.md"
_STREAMLIT_README_URL = (
    "https://github.com/prakosd/rag-playground/blob/master/apps/streamlit/README.md"
)
_TOAST_PAGE_SUCCESS_ICON = "✅"
_TOAST_PAGE_FAIL_ICON = "❌"
_TOAST_PAGE_DISCOVERED_ICON = "🔎"
_CREATE_TOAST_STATE = "_create_toast"
_EXTEND_TOAST_STATE = "_extend_toast"
_LOAD_TOAST_STATE = "_load_toast"
_SWITCH_TOAST_STATE = "_switch_toast"
# A page (app_pages/**, which must not call st.toast) sets this to a localized
# success message; the shell fires it once on the next run.
_PENDING_PAGE_TOAST_STATE = "pending_page_toast"
_EXTEND_TOAST_SUCCESS = "success"
_EXTEND_TOAST_FAILED = "failed"
_REFRESH_FORM_STATES = {
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_STOPPED,
}
_FORM_MAX_WIDTH_PX = 980
_PORTFOLIO_MODAL_COMPONENT_KEY = "portfolio_modal"
_PORTFOLIO_MODAL_FIRST_DELAY_SECONDS = 60
_PORTFOLIO_MODAL_REPEAT_DAYS = 7
_PORTFOLIO_MODAL_REPEAT_HOURS = _HOURS_PER_DAY * _PORTFOLIO_MODAL_REPEAT_DAYS
_PORTFOLIO_MODAL_LAST_SHOWN_FIELD = "portfolio_modal_last_shown_at"
_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD = "portfolio_modal_last_dismissed_at"
_SESSION_STORAGE_COMPONENT_KEY = "browser_session_storage"
_SESSION_STORAGE_KEY = "crawl4md.streamlit.sessions.v1"
_SESSION_SELECTED_ID_FIELD = "selected_session_id"
