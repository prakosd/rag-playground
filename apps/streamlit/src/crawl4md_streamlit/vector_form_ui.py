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
    DEFAULT_LANGUAGE,
    DEFAULT_LOCAL_MODEL,
    EMBEDDING_MODEL_OPTIONS,
    LUCENE_LANGUAGES,
    EmbeddingModelInfo,
    get_embedding_model_info,
)

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.i18n import Strings

VEC_DEFAULT_CHUNK_SIZE = 600
VEC_DEFAULT_CHUNK_OVERLAP = 100
VEC_DEFAULT_EMBEDDING_DIMENSION = 512
_UPLOAD_TYPES = ["md", "txt", "zip"]

# Open-range fallback used only if a selected model is ever absent from the
# library catalog; the catalog covers every id in EMBEDDING_MODEL_OPTIONS.
_UNKNOWN_MODEL_INFO = EmbeddingModelInfo(
    model_id="",
    kind="unknown",
    default_dimension=VEC_DEFAULT_EMBEDDING_DIMENSION,
    supported_dimensions=None,
    min_dimension=1,
    max_dimension=None,
)


def embedding_model_info_for(model_id: str) -> EmbeddingModelInfo:
    """Return catalog metadata for *model_id*, or an open-range fallback."""
    return get_embedding_model_info(model_id) or _UNKNOWN_MODEL_INFO


def embedding_model_label(model_id: str, strings: Strings) -> str:
    """Return a selectbox label tagging a model as local or cloud."""
    info = get_embedding_model_info(model_id)
    if info is None:
        return model_id
    tag_key = "VEC_MODEL_TAG_LOCAL" if info.kind == "local" else "VEC_MODEL_TAG_CLOUD"
    return f"{model_id} · {strings[tag_key]}"


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


def _render_dimension_input(
    info: EmbeddingModelInfo,
    model: str,
    *,
    strings: Strings,
    fields_disabled: bool,
) -> int:
    """Render the dimension input constrained to what *model* supports."""
    label = strings["VEC_EMBEDDING_DIMENSION_LABEL"]
    help_text = strings["VEC_EMBEDDING_DIMENSION_HELP"]
    key = f"vector_index_embedding_dimension_{model}"
    if info.supported_dimensions is not None:
        option_list = list(info.supported_dimensions)
        return int(
            st.selectbox(
                label,
                options=option_list,
                index=option_list.index(info.default_dimension),
                help=help_text,
                disabled=fields_disabled or len(option_list) <= 1,
                key=key,
            )
        )
    return int(
        st.number_input(
            label,
            min_value=info.min_dimension or 1,
            max_value=info.max_dimension,
            value=info.default_dimension,
            step=1,
            help=help_text,
            disabled=fields_disabled,
            key=key,
        )
    )


def _render_embedding_controls(*, strings: Strings, fields_disabled: bool) -> tuple[str, int]:
    """Render the reactive embedding model + dimension inputs above the form.

    These live outside ``st.form`` so the dimension input can re-render with the
    options supported by the selected model instead of accepting any value.
    """
    model_options = list(EMBEDDING_MODEL_OPTIONS)
    cols = st.columns(2)
    with cols[0]:
        embedding_model = st.selectbox(
            strings["VEC_EMBEDDING_MODEL_LABEL"],
            options=model_options,
            index=model_options.index(DEFAULT_LOCAL_MODEL),
            format_func=lambda model: embedding_model_label(model, strings),
            help=strings["VEC_EMBEDDING_MODEL_HELP"],
            disabled=fields_disabled,
            key="vector_index_embedding_model",
        )
    info = embedding_model_info_for(embedding_model)
    with cols[1]:
        embedding_dimension = _render_dimension_input(
            info, embedding_model, strings=strings, fields_disabled=fields_disabled
        )
    if info.kind == "local":
        st.caption(strings["VEC_MODEL_INDICATOR_LOCAL"])
    elif info.kind == "cloud":
        st.caption(strings["VEC_MODEL_INDICATOR_CLOUD"])
    return embedding_model, embedding_dimension


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
    embedding_model, embedding_dimension = _render_embedding_controls(
        strings=strings, fields_disabled=fields_disabled
    )
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
