"""Default form values for the crawl4md Streamlit app."""

from __future__ import annotations

from typing import Any

DEFAULT_DELAY = 3.0
DEFAULT_ACTIVITY_LOG_SIZE = 10
DEFAULT_EXCLUDE_PATHS = "ato.gov.au/api/"
DEFAULT_EXCLUDE_TAGS = "nav, script, form, style"
DEFAULT_FLUSH_INTERVAL = 5
DEFAULT_INCLUDE_ONLY_PATHS = "ato.gov.au"
DEFAULT_LIMIT = 10
DEFAULT_MAX_DEPTH = 5
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_MAX_FILE_SIZE_MB = 10.0
DEFAULT_MAX_RETRIES = 5
DEFAULT_OUTPUT_EXTENSION = ".md"
DEFAULT_TIMEOUT = 60.0
DEFAULT_URLS = "https://www.ato.gov.au/"
DEFAULT_WAIT_FOR = 3.0
OUTPUT_EXTENSION_OPTIONS = [DEFAULT_OUTPUT_EXTENSION, ".txt"]


def default_form_values() -> dict[str, Any]:
    """Return the default crawl settings used for a new Streamlit form."""
    return {
        "urls": DEFAULT_URLS,
        "include_only_paths": DEFAULT_INCLUDE_ONLY_PATHS,
        "exclude_paths": DEFAULT_EXCLUDE_PATHS,
        "limit": DEFAULT_LIMIT,
        "max_depth": DEFAULT_MAX_DEPTH,
        "max_concurrent": DEFAULT_MAX_CONCURRENT,
        "flush_interval": DEFAULT_FLUSH_INTERVAL,
        "delay": DEFAULT_DELAY,
        "max_retries": DEFAULT_MAX_RETRIES,
        "exclude_tags": DEFAULT_EXCLUDE_TAGS,
        "include_only_tags": "",
        "wait_for": DEFAULT_WAIT_FOR,
        "timeout": DEFAULT_TIMEOUT,
        "max_file_size_mb": DEFAULT_MAX_FILE_SIZE_MB,
        "extract_main_content": True,
        "output_extension": DEFAULT_OUTPUT_EXTENSION,
        "activity_log_size": DEFAULT_ACTIVITY_LOG_SIZE,
    }
