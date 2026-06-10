"""Step 2 vector-index form UI for the crawl4md Streamlit app.

Pure option-building and input-validation helpers are kept separate from the
Streamlit rendering so they can be unit tested without a running app.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st
from artifact_store.crawl_results import CrawlResultFile
from vector_indexer import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LANGUAGE,
    EMBEDDING_MODEL_OPTIONS,
    LUCENE_LANGUAGES,
)

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.i18n import Strings

VEC_DEFAULT_CHUNK_SIZE = 600
VEC_DEFAULT_CHUNK_OVERLAP = 100
VEC_DEFAULT_EMBEDDING_DIMENSION = 512
_UPLOAD_TYPES = ["md", "txt", "zip"]


def crawl_result_options(files: Sequence[CrawlResultFile]) -> dict[str, str]:
    """Return an ordered ``{label: path}`` map for the crawl-result multiselect."""
    options: dict[str, str] = {}
    for file in files:
        file_name = file.relative_path.split("/", 1)[-1]
        base_label = f"{file.crawl_label} / {file_name}"
        label = base_label
        suffix = 2
        while label in options:
            label = f"{base_label} ({suffix})"
            suffix += 1
        options[label] = str(file.path)
    return options


def has_index_inputs(selected_paths: Sequence[str], uploaded_count: int) -> bool:
    """Return True when at least one crawl result or uploaded file is provided."""
    return bool(selected_paths) or uploaded_count > 0


def render_vector_index_form(
    *,
    fields_disabled: bool,
    state: str,
    job_alive: bool,
    strings: Strings,
    crawl_result_files: Sequence[CrawlResultFile],
) -> dict[str, Any]:
    """Render the vector-index settings form and return submitted values."""
    options = crawl_result_options(crawl_result_files)
    submitted = False
    stop_submitted = False
    with st.form("vector_index_settings", enter_to_submit=False):
        selected_labels = st.multiselect(
            strings["VEC_SOURCES_LABEL"],
            options=list(options.keys()),
            help=strings["VEC_SOURCES_HELP"],
            disabled=fields_disabled,
        )
        if not options:
            st.caption(strings["VEC_SOURCES_EMPTY"])
        uploaded = st.file_uploader(
            strings["VEC_UPLOAD_LABEL"],
            type=_UPLOAD_TYPES,
            accept_multiple_files=True,
            help=strings["VEC_UPLOAD_HELP"],
            disabled=fields_disabled,
        )
        size_cols = st.columns(2)
        with size_cols[0]:
            chunk_size = st.number_input(
                strings["VEC_CHUNK_SIZE_LABEL"],
                min_value=1,
                value=VEC_DEFAULT_CHUNK_SIZE,
                help=strings["VEC_CHUNK_SIZE_HELP"],
                disabled=fields_disabled,
            )
        with size_cols[1]:
            chunk_overlap = st.number_input(
                strings["VEC_CHUNK_OVERLAP_LABEL"],
                min_value=0,
                value=VEC_DEFAULT_CHUNK_OVERLAP,
                help=strings["VEC_CHUNK_OVERLAP_HELP"],
                disabled=fields_disabled,
            )
        model_options = list(EMBEDDING_MODEL_OPTIONS)
        embedding_model = st.selectbox(
            strings["VEC_EMBEDDING_MODEL_LABEL"],
            options=model_options,
            index=model_options.index(DEFAULT_EMBEDDING_MODEL),
            help=strings["VEC_EMBEDDING_MODEL_HELP"],
            disabled=fields_disabled,
        )
        embedding_dimension = st.number_input(
            strings["VEC_EMBEDDING_DIMENSION_LABEL"],
            min_value=1,
            value=VEC_DEFAULT_EMBEDDING_DIMENSION,
            help=strings["VEC_EMBEDDING_DIMENSION_HELP"],
            disabled=fields_disabled,
        )
        language_options = list(LUCENE_LANGUAGES)
        language = st.selectbox(
            strings["VEC_LANGUAGE_LABEL"],
            options=language_options,
            index=language_options.index(DEFAULT_LANGUAGE),
            help=strings["VEC_LANGUAGE_HELP"],
            disabled=fields_disabled,
        )
        action_cols = st.columns([1.5, 3], vertical_alignment="bottom")
        for action_col, action_button in zip(
            action_cols,
            crawl_action_buttons(state, job_alive=job_alive, strings=strings),
            strict=False,
        ):
            with action_col:
                pressed = st.form_submit_button(
                    action_button.label,
                    type=action_button.button_type,
                    icon=action_button.icon,
                    disabled=action_button.disabled,
                    key=f"vector_{action_button.action}",
                )
            if action_button.action == "start":
                submitted = pressed
            elif action_button.action == "stop":
                stop_submitted = pressed
    selected_paths = [options[label] for label in selected_labels if label in options]
    uploaded_files = list(uploaded or [])
    return {
        "submitted": submitted,
        "stop_submitted": stop_submitted,
        "selected_paths": selected_paths,
        "uploaded_files": uploaded_files,
        "chunk_size": int(chunk_size),
        "chunk_overlap": int(chunk_overlap),
        "embedding_model": embedding_model,
        "embedding_dimension": int(embedding_dimension),
        "language": language,
    }
