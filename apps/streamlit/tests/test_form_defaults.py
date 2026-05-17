from __future__ import annotations

from crawl4md_streamlit.form_defaults import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    DEFAULT_OUTPUT_EXTENSION,
    DEFAULT_URLS,
    OUTPUT_EXTENSION_OPTIONS,
    default_form_values,
)
from crawl4md_streamlit.support import build_configs


def test_default_form_values_include_required_build_config_keys() -> None:
    values = default_form_values()

    assert values["urls"] == DEFAULT_URLS
    assert values["output_extension"] == DEFAULT_OUTPUT_EXTENSION
    assert values["activity_log_size"] == DEFAULT_ACTIVITY_LOG_SIZE
    assert set(OUTPUT_EXTENSION_OPTIONS) >= {DEFAULT_OUTPUT_EXTENSION, ".txt"}
    assert {
        "exclude_paths",
        "include_only_paths",
        "limit",
        "max_depth",
        "flush_interval",
        "delay",
        "max_retries",
        "exclude_tags",
        "include_only_tags",
        "wait_for",
        "timeout",
        "max_file_size_mb",
        "extract_main_content",
    }.issubset(values)


def test_default_form_values_returns_independent_dicts() -> None:
    first = default_form_values()
    second = default_form_values()

    first["urls"] = "https://changed.example"

    assert second["urls"] == DEFAULT_URLS


def test_default_form_values_build_valid_configs() -> None:
    crawler_config, page_config, activity_log_size = build_configs(default_form_values())

    assert crawler_config.urls == [DEFAULT_URLS]
    assert page_config.output_extension == DEFAULT_OUTPUT_EXTENSION
    assert activity_log_size == DEFAULT_ACTIVITY_LOG_SIZE
