"""Crawl settings form UI for the crawl4md Streamlit app."""

from __future__ import annotations

from typing import Any

import streamlit as st

from crawl4md_streamlit.controls import crawl_action_buttons
from crawl4md_streamlit.form_defaults import (
    DEFAULT_DELAY,
    DEFAULT_EXCLUDE_PATHS,
    DEFAULT_EXCLUDE_TAGS,
    DEFAULT_FLUSH_INTERVAL,
    DEFAULT_INCLUDE_ONLY_PATHS,
    DEFAULT_LIMIT,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_RETRIES,
    DEFAULT_OUTPUT_EXTENSION,
    DEFAULT_TIMEOUT,
    DEFAULT_URLS,
    DEFAULT_WAIT_FOR,
    OUTPUT_EXTENSION_OPTIONS,
)
from crawl4md_streamlit.i18n import Strings

# The Website URLs field is keyed so the crawl page can move focus to it on entry.
URLS_WIDGET_KEY = "crawl_urls"


def render_crawl_form(
    *,
    fields_disabled: bool,
    expanded: bool,
    state: str,
    job_alive: bool,
    strings: Strings,
    defaults: dict[str, Any],
    activity_log_size: int,
) -> dict[str, Any]:
    """Render the crawl settings form and return submitted values."""
    st.subheader(strings["FORM_SUBHEADER"], anchor="form-subheader")
    st.caption(strings["FORM_CAPTION"])
    with (
        st.expander(strings["FORM_EXPANDER_LABEL"], expanded=expanded),
        st.form("crawl_settings", enter_to_submit=False),
    ):
        urls = st.text_area(
            strings["FORM_URLS_LABEL"],
            value=str(defaults.get("urls", DEFAULT_URLS)),
            height=68,
            help=strings["FORM_URLS_HELP"],
            disabled=fields_disabled,
            key=URLS_WIDGET_KEY,
        )
        include_only_paths = st.text_area(
            strings["FORM_INCLUDE_PATHS_LABEL"],
            value=str(defaults.get("include_only_paths", DEFAULT_INCLUDE_ONLY_PATHS)),
            height=68,
            help=strings["FORM_INCLUDE_PATHS_HELP"],
            disabled=fields_disabled,
        )
        exclude_paths = st.text_area(
            strings["FORM_EXCLUDE_PATHS_LABEL"],
            value=str(defaults.get("exclude_paths", DEFAULT_EXCLUDE_PATHS)),
            height=68,
            help=strings["FORM_EXCLUDE_PATHS_HELP"],
            disabled=fields_disabled,
        )
        basic_cols = st.columns(3)
        with basic_cols[0]:
            limit = st.number_input(
                strings["FORM_LIMIT_LABEL"],
                min_value=1,
                value=int(defaults.get("limit", DEFAULT_LIMIT)),
                help=strings["FORM_LIMIT_HELP"],
                disabled=fields_disabled,
            )
            delay = st.number_input(
                strings["FORM_DELAY_LABEL"],
                min_value=0.0,
                value=float(defaults.get("delay", DEFAULT_DELAY)),
                step=0.5,
                help=strings["FORM_DELAY_HELP"],
                disabled=fields_disabled,
            )
        with basic_cols[1]:
            max_depth = st.number_input(
                strings["FORM_DEPTH_LABEL"],
                min_value=1,
                value=int(defaults.get("max_depth", DEFAULT_MAX_DEPTH)),
                help=strings["FORM_DEPTH_HELP"],
                disabled=fields_disabled,
            )
            max_retries = st.number_input(
                strings["FORM_RETRIES_LABEL"],
                min_value=2,
                value=int(defaults.get("max_retries", DEFAULT_MAX_RETRIES)),
                help=strings["FORM_RETRIES_HELP"],
                disabled=fields_disabled,
            )
        with basic_cols[2]:
            output_extension = st.segmented_control(
                strings["FORM_OUTPUT_FORMAT_LABEL"],
                OUTPUT_EXTENSION_OPTIONS,
                default=str(defaults.get("output_extension", DEFAULT_OUTPUT_EXTENSION)),
                help=strings["FORM_OUTPUT_FORMAT_HELP"],
                disabled=fields_disabled,
            )
            # A checkbox has no label row above it, so it floats higher than the
            # adjacent column's "Retry rounds" input; this spacer drops it to line up.
            st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            extract_main_content = st.checkbox(
                strings["FORM_EXTRACT_MAIN_LABEL"],
                value=bool(defaults.get("extract_main_content", True)),
                help=strings["FORM_EXTRACT_MAIN_HELP"],
                disabled=fields_disabled,
            )

        with st.expander(strings["FORM_ADVANCED_LABEL"]):
            advanced_cols = st.columns(3)
            with advanced_cols[0]:
                flush_interval = st.number_input(
                    strings["FORM_FLUSH_LABEL"],
                    min_value=1,
                    value=int(defaults.get("flush_interval", DEFAULT_FLUSH_INTERVAL)),
                    help=strings["FORM_FLUSH_HELP"],
                    disabled=fields_disabled,
                )
                max_file_size_mb = st.number_input(
                    strings["FORM_MAX_FILE_SIZE_LABEL"],
                    min_value=0.1,
                    value=float(defaults.get("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB)),
                    step=0.5,
                    help=strings["FORM_MAX_FILE_SIZE_HELP"],
                    disabled=fields_disabled,
                )
            with advanced_cols[1]:
                wait_for = st.number_input(
                    strings["FORM_WAIT_FOR_LABEL"],
                    min_value=0.0,
                    value=float(defaults.get("wait_for", DEFAULT_WAIT_FOR)),
                    step=0.5,
                    help=strings["FORM_WAIT_FOR_HELP"],
                    disabled=fields_disabled,
                )
                timeout = st.number_input(
                    strings["FORM_TIMEOUT_LABEL"],
                    min_value=0.0,
                    value=float(defaults.get("timeout", DEFAULT_TIMEOUT)),
                    step=5.0,
                    help=strings["FORM_TIMEOUT_HELP"],
                    disabled=fields_disabled,
                )
            with advanced_cols[2]:
                activity_log_size_value = st.number_input(
                    strings["FORM_ACTIVITY_LOG_LABEL"],
                    min_value=1,
                    value=int(defaults.get("activity_log_size", activity_log_size)),
                    help=strings["FORM_ACTIVITY_LOG_HELP"],
                    disabled=fields_disabled,
                )
                max_concurrent = st.number_input(
                    strings["FORM_MAX_CONCURRENT_LABEL"],
                    min_value=1,
                    value=int(defaults.get("max_concurrent", DEFAULT_MAX_CONCURRENT)),
                    help=strings["FORM_MAX_CONCURRENT_HELP"],
                    disabled=fields_disabled,
                )
            exclude_tags = st.text_input(
                strings["FORM_EXCLUDE_TAGS_LABEL"],
                value=str(defaults.get("exclude_tags", DEFAULT_EXCLUDE_TAGS)),
                help=strings["FORM_EXCLUDE_TAGS_HELP"],
                disabled=fields_disabled,
            )
            include_only_tags = st.text_input(
                strings["FORM_INCLUDE_ONLY_TAGS_LABEL"],
                value=str(defaults.get("include_only_tags", "")),
                help=strings["FORM_INCLUDE_ONLY_TAGS_HELP"],
                disabled=fields_disabled,
            )

        submitted = False
        stop_submitted = False
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
                    key=action_button.action.capitalize(),
                )
            if action_button.action == "start":
                submitted = pressed
            elif action_button.action == "stop":
                stop_submitted = pressed
    return {
        "submitted": submitted,
        "stop_submitted": stop_submitted,
        "urls": urls,
        "include_only_paths": include_only_paths,
        "exclude_paths": exclude_paths,
        "limit": limit,
        "max_depth": max_depth,
        "max_concurrent": max_concurrent,
        "flush_interval": flush_interval,
        "delay": delay,
        "max_retries": max_retries,
        "exclude_tags": exclude_tags,
        "include_only_tags": include_only_tags,
        "wait_for": wait_for,
        "timeout": timeout,
        "max_file_size_mb": max_file_size_mb,
        "extract_main_content": extract_main_content,
        "output_extension": output_extension or DEFAULT_OUTPUT_EXTENSION,
        "activity_log_size": activity_log_size_value,
    }
