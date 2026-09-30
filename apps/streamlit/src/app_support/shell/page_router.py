"""Workflow page routing extracted from ``streamlit_app.py``.

Builds each Step's page context (wiring shell callbacks into the ``app_pages/*``
render functions), turns the page registry into ``st.Page`` navigation entries, and
renders the shared page header.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _current_crawl_runtime,
    _current_vector_runtime,
    _session_root,
)
from app_support.downloads_ui import _render_downloads, _render_ready_result_panel
from app_support.i18n import Strings
from app_support.pages import APP_PAGE_SPECS, DEFAULT_PAGE_ID, AppPageSpec
from app_support.progress_ui import _render_live_area, _render_vector_index_live_area
from app_support.rag_shared.rag_ui import RagPageContext
from app_support.shell.constants import _RAG_PAGE_IDS, _VECTOR_INDEX_PAGE_ID
from app_support.shell.crawl_orchestration import _start_job, _stop_confirmation_dialog
from app_support.shell.vector_orchestration import (
    _crawl_result_files,
    _list_session_indexes,
    _start_vector_index_job,
    _vector_index_stop_confirmation_dialog,
)

# apps/streamlit/ (where app_pages/ lives): page_router → shell → app_support → src → apps/streamlit.
_APP_DIR = Path(__file__).resolve().parents[3]


def _import_page_module(module_name: str) -> Any:
    app_dir = str(_APP_DIR)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    return importlib.import_module(module_name)


def _crawl_page_context(crawl_module: Any) -> Any:
    return crawl_module.CrawlPageContext(
        current_runtime=_current_crawl_runtime,
        start_job=_start_job,
        stop_confirmation_dialog=_stop_confirmation_dialog,
        render_ready_result_panel=_render_ready_result_panel,
        render_live_area=_render_live_area,
        render_downloads=_render_downloads,
        default_language=_DEFAULT_LANGUAGE,
    )


def _vector_index_page_context(vector_module: Any) -> Any:
    return vector_module.VectorIndexPageContext(
        current_runtime=_current_vector_runtime,
        crawl_result_files=_crawl_result_files,
        start_job=_start_vector_index_job,
        stop_confirmation_dialog=_vector_index_stop_confirmation_dialog,
        render_live_area=_render_vector_index_live_area,
        render_downloads=_render_downloads,
        default_language=_DEFAULT_LANGUAGE,
    )


def _rag_page_context() -> RagPageContext:
    return RagPageContext(
        default_language=_DEFAULT_LANGUAGE,
        list_indexes=_list_session_indexes,
        render_downloads=_render_downloads,
        session_root=_session_root,
    )


def _page_renderers() -> dict[str, Callable[[], None]]:
    renderers: dict[str, Callable[[], None]] = {}
    for page_spec in APP_PAGE_SPECS:
        page_module = _import_page_module(page_spec.module_name)
        if page_spec.page_id == DEFAULT_PAGE_ID:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _crawl_page_context(page_module),
            )
        elif page_spec.page_id == _VECTOR_INDEX_PAGE_ID:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _vector_index_page_context(page_module),
            )
        elif page_spec.page_id in _RAG_PAGE_IDS:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _rag_page_context(),
            )
        else:
            renderers[page_spec.page_id] = page_module.render_page
    return renderers


def _navigation_pages(strings: Strings) -> list[Any]:
    renderers = _page_renderers()
    return [
        st.Page(
            renderers[page_spec.page_id],
            title=strings[page_spec.nav_label_key],
            icon=page_spec.icon,
            url_path=page_spec.url_path,
            default=page_spec.page_id == DEFAULT_PAGE_ID,
        )
        for page_spec in APP_PAGE_SPECS
    ]


def _render_page_header(page_spec: AppPageSpec, strings: Strings) -> None:
    st.title(strings[page_spec.title_key])
    st.write(strings[page_spec.subtitle_key])
