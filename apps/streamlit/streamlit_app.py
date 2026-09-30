from __future__ import annotations

import os

# Best-effort: prefer protobuf's pure-Python parser, which tolerates out-of-date
# ``*_pb2`` modules that the C/upb backend rejects with "Descriptors cannot be
# created directly" (seen when a newer protobuf is paired with stale generated code,
# e.g. via chromadb reached through vector_indexer). This only takes effect when
# this module is imported before protobuf; under ``streamlit run`` Streamlit imports
# protobuf first, so the reliable fix is the ``protobuf`` version pin in
# apps/streamlit/requirements.txt. Kept here for non-``streamlit run`` entry points,
# set before the module imports below (see E402 ignore).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# The offline embedding model (ChromaDB's bundled ONNX MiniLM) tokenizes through
# HuggingFace ``tokenizers``, whose Rust parallelism is unsafe across the forks
# Streamlit and Playwright perform — it prints a "process just got forked" warning
# and risks deadlocks. Default it off before any heavy import loads tokenizers;
# ``setdefault`` still lets an operator override it explicitly.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import html
import warnings
from pathlib import Path

import streamlit as st
from log4py import configure_logging, get_logger
from streamlit.components.v2 import component as component_v2

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _SESSIONS_ROOT,
    _STATE_IDLE,
    _current_crawl_runtime,
    _session_log_path,
)
from app_support.crawl.form_defaults import default_form_values
from app_support.i18n import get_strings
from app_support.log_context import set_log_session_id
from app_support.pages import (
    page_spec_by_nav_label,
)
from app_support.session_manager import (
    SESSION_DIR_PREFIX,
)
from app_support.settings import get_settings
from app_support.shell.assets import (
    _AUTHOR_PHOTO_URL,
    _LINKEDIN_ICON_DATA_URI,
    _PORTFOLIO_MODAL_CSS,
    _PORTFOLIO_MODAL_HTML,
    _PORTFOLIO_MODAL_JS,
    _github_icon_data_uri,
)
from app_support.shell.constants import (
    _AUTHOR_LINKEDIN_URL,
    _AUTHOR_NAME,
    _CREATE_TOAST_STATE,
    _FORM_MAX_WIDTH_PX,
    _LOAD_TOAST_STATE,
    _PENDING_PAGE_TOAST_STATE,
    _PORTFOLIO_MODAL_COMPONENT_KEY,
    _PORTFOLIO_MODAL_FIRST_DELAY_SECONDS,
    _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD,
    _PORTFOLIO_MODAL_LAST_SHOWN_FIELD,
    _PORTFOLIO_MODAL_REPEAT_HOURS,
    _PROJECT_GITHUB_URL,
    _README_URL,
    _SESSION_STORAGE_KEY,
    _STREAMLIT_README_URL,
    _SWITCH_TOAST_STATE,
    _TOAST_PAGE_SUCCESS_ICON,
)
from app_support.shell.crawl_orchestration import (
    _reattach_selected_session_job,
    _render_crawl_event_loop,
)
from app_support.shell.page_router import _navigation_pages, _render_page_header
from app_support.shell.session_records import (
    SESSION_RECORDS_CACHE_STATE,
)
from app_support.shell.session_select import (
    _ensure_selected_session,
    _load_session_dialog,
    _render_session_controls,
    _session_options,
    _sync_language_widget_state,
)
from app_support.shell.session_storage import (
    _mount_session_storage,
)
from app_support.shell.vector_orchestration import (
    _reattach_selected_session_vector_job,
)
from app_support.site_graph_3d.static_publish import remove_orrery_static
from app_support.storage import resolve_storage_backend
from app_support.support import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    active_registry_session_ids,
    bootstrap_gate_state,
    cleanup_old_sessions_with_lock,
    should_show_portfolio_modal,
)
from app_support.vector_index.vector_index_jobs import (
    active_vector_registry_session_ids,
)

_APP_DIR = Path(__file__).resolve().parent

# Load a local .env (e.g. AWS_*/OPENAI_API_KEY for Step 2 embeddings) when
# python-dotenv is installed. In Codespaces/CI these come from the real
# environment instead, so a missing package or file is not an error.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_APP_DIR.parents[1] / ".env")
except ImportError:
    pass


# Configure project-wide logging once per process, before any runtime work emits
# records. Only the project's own top-level loggers are configured, keeping
# third-party (chromadb, urllib3, playwright) noise out. The file destination is
# routed per record to the active session's log (see _session_log_path), so each
# session gets its own log under its folder; stderr stays global.
_PROJECT_LOGGER_NAMES = (
    "artifact_store",
    "crawl4md",
    "app_support",
    "rag_engine",
    "vector_indexer",
)


@st.cache_resource(show_spinner=False)
def _configure_app_logging() -> bool:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        logger_names=_PROJECT_LOGGER_NAMES,
        log_file_router=_session_log_path,
    )
    # langchain_aws warns once per model when a provider is not on its streaming
    # allowlist (e.g. nvidia); it then falls back to the non-streaming Converse API.
    # That fallback is harmless, so silence the notice to keep logs readable.
    warnings.filterwarnings("ignore", message=r".*is not verified as streaming-capable.*")
    return True


_configure_app_logging()
_logger = get_logger("app_support.app")

st.set_page_config(
    page_title="crawl4md — Website Crawler",
    page_icon=":material/travel_explore:",
    layout="wide",
)


_PORTFOLIO_MODAL_COMPONENT = component_v2(
    "crawl4md_portfolio_modal",
    html=_PORTFOLIO_MODAL_HTML,
    css=_PORTFOLIO_MODAL_CSS,
    js=_PORTFOLIO_MODAL_JS,
)


@st.cache_resource(show_spinner=False)
def _run_startup_cleanup(active_session_ids: tuple[str, ...]) -> None:
    removed = cleanup_old_sessions_with_lock(
        _SESSIONS_ROOT,
        active_session_ids=active_session_ids,
        retention_days=get_settings().session_retention_days,
        backend=resolve_storage_backend(),
    )
    # Prune each removed session's published 3D viewers from the static dir.
    remove_orrery_static(
        _APP_DIR / "static",
        [path.name.removeprefix(SESSION_DIR_PREFIX) for path in removed],
    )


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
    st.session_state.setdefault("latest_event", {})
    st.session_state.setdefault("progress_chart_history", [])
    st.session_state.setdefault("active_output_dir", "")
    st.session_state.setdefault("started_at", None)
    st.session_state.setdefault("last_elapsed", "")
    st.session_state.setdefault("activity_log_size", DEFAULT_ACTIVITY_LOG_SIZE)
    st.session_state.setdefault("activity_log_latest_line", None)
    st.session_state.setdefault("preview_file_relative_path", "")
    st.session_state.setdefault("delete_folder_relative_path", "")
    st.session_state.setdefault("export_folder_relative_path", "")
    st.session_state.setdefault("form_defaults", default_form_values())
    st.session_state.setdefault("stop_confirmation_open", False)
    st.session_state.setdefault("vector_index_job", None)
    st.session_state.setdefault("vector_index_id", "")
    st.session_state.setdefault("vector_index_state", _STATE_IDLE)
    st.session_state.setdefault("vector_index_progress", {})
    st.session_state.setdefault("vector_index_stage", "")
    st.session_state.setdefault("vector_index_result", {})
    st.session_state.setdefault("vector_index_started_at", None)
    st.session_state.setdefault("vector_index_stop_confirmation_open", False)
    st.session_state.setdefault("session_load_dialog_open", False)
    st.session_state.setdefault("_load_session_enter", False)
    st.session_state.setdefault("language", _DEFAULT_LANGUAGE)
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_SHOWN_FIELD, "")
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD, "")
    st.session_state.setdefault(SESSION_RECORDS_CACHE_STATE, {})


def _render_footer() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    built_by = html.escape(strings["FOOTER_BUILT_BY"].format(author=_AUTHOR_NAME))
    tagline = html.escape(strings["FOOTER_TAGLINE"])
    linkedin_label = html.escape(strings["FOOTER_LINK_LINKEDIN"])
    github_label = html.escape(strings["FOOTER_LINK_GITHUB"])
    linkedin_url = html.escape(_AUTHOR_LINKEDIN_URL, quote=True)
    github_url = html.escape(_PROJECT_GITHUB_URL, quote=True)
    linkedin_icon = html.escape(_LINKEDIN_ICON_DATA_URI, quote=True)
    github_icon = html.escape(_github_icon_data_uri(), quote=True)
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
            "githubIconUrl": _github_icon_data_uri(),
            "readmeUrl": _README_URL,
            "streamlitReadmeUrl": _STREAMLIT_README_URL,
            "readmeLabel": strings["PORTFOLIO_MODAL_LINK_README"],
            "streamlitReadmeLabel": strings["PORTFOLIO_MODAL_LINK_STREAMLIT_README"],
        },
    )


def _render_shared_styles() -> None:
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
        h3#crawl4md-header,
        h3#vector-index-header,
        h3#semantic-search-header,
        h3#basic-rag-qa-header,
        h3#conversational-rag-header {{
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


_init_state()
_mount_session_storage()
active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

# Show deferred "session created" toast only once the storage component has
# confirmed the localStorage write. Firing earlier shows it on an intermediate
# rerun that can be replaced by component callbacks, making the toast disappear.
if (
    st.session_state.get(_CREATE_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    st.session_state.pop(_CREATE_TOAST_STATE)
    st.toast(active_strings["TOAST_SESSION_CREATED"], icon=_TOAST_PAGE_SUCCESS_ICON)
if st.session_state.get(_LOAD_TOAST_STATE) and not st.session_state.pending_browser_session_records:
    _load_toast_id = st.session_state.pop(_LOAD_TOAST_STATE)
    st.toast(
        active_strings["TOAST_SESSION_LOADED"].format(id=_load_toast_id),
        icon=":material/folder_open:",
    )
if (
    st.session_state.get(_SWITCH_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    _switch_toast_id = st.session_state.pop(_SWITCH_TOAST_STATE)
    st.toast(
        active_strings["DIALOG_LOAD_SESSION_ALREADY_LOADED"].format(id=_switch_toast_id),
        icon=":material/folder_open:",
    )
if st.session_state.get("upload_done_folder"):
    _upload_folder = st.session_state.pop("upload_done_folder")
    st.toast(
        active_strings["FILES_UPLOAD_SUCCESS"].format(folder=_upload_folder),
        icon=_TOAST_PAGE_SUCCESS_ICON,
    )
if st.session_state.get("sample_import_done_folder"):
    _sample_folder = st.session_state.pop("sample_import_done_folder")
    st.toast(
        active_strings["FILES_SAMPLE_IMPORT_SUCCESS"].format(folder=_sample_folder),
        icon=_TOAST_PAGE_SUCCESS_ICON,
    )
_pending_page_toast = st.session_state.pop(_PENDING_PAGE_TOAST_STATE, None)
if _pending_page_toast:
    st.toast(_pending_page_toast, icon=_TOAST_PAGE_SUCCESS_ICON)

# Register the page router on *every* run before any st.stop() so a deep-linked
# URL (e.g. /vector-index) survives the session-bootstrap reruns below. Were
# st.navigation() reached only after the gates, stopping during hydration would
# drop the requested page and Streamlit would fall back to the default page.
_render_shared_styles()
navigation_page = st.navigation(_navigation_pages(active_strings), position="top")

bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
if bootstrap_state == "hydrating":
    st.title(active_strings["PAGE_TITLE"])
    st.write(active_strings["PAGE_SUBTITLE"])
    st.info(active_strings["SESSION_LOADING"])
    st.stop()

_ensure_selected_session()
bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
active_language_widget_key = _sync_language_widget_state()
if bootstrap_state != "ready":
    active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(active_strings["PAGE_TITLE"])
    st.write(active_strings["PAGE_SUBTITLE"])
    if bootstrap_state == "storage_error":
        st.error(active_strings["ERROR_SESSION_STORAGE_WRITE"])
        st.stop()
    st.info(active_strings["SESSION_LOADING"])
    st.stop()

_reattach_selected_session_job()
_reattach_selected_session_vector_job()
_run_startup_cleanup(
    tuple(
        sorted(
            set(_session_options())
            | active_registry_session_ids()
            | active_vector_registry_session_ids()
        )
    )
)

# Route this run's log records to the selected session's log file.
set_log_session_id(st.session_state.get("session_id", ""))

active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
_render_crawl_event_loop()

selected_page_spec = page_spec_by_nav_label(navigation_page.title, active_strings)
_render_page_header(selected_page_spec, active_strings)
_, _, _, session_fields_disabled = _current_crawl_runtime()
_render_session_controls(
    fields_disabled=session_fields_disabled,
    language_widget_key=active_language_widget_key,
    strings=active_strings,
)
if st.session_state.session_load_dialog_open:
    _load_session_dialog()

navigation_page.run()
_render_footer()
_render_portfolio_modal()
