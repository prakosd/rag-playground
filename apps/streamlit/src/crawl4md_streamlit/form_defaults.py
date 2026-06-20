"""Default form values for the crawl4md Streamlit app."""

from __future__ import annotations

from typing import Any

from crawl4md_streamlit.settings import get_settings

_settings = get_settings()

DEFAULT_DELAY = _settings.crawl_delay
DEFAULT_ACTIVITY_LOG_SIZE = _settings.crawl_activity_log_size
DEFAULT_EXCLUDE_PATHS = "ato.gov.au/api/"
DEFAULT_EXCLUDE_TAGS = "nav, script, form, style"
DEFAULT_FLUSH_INTERVAL = _settings.crawl_flush_interval
DEFAULT_INCLUDE_ONLY_PATHS = "ato.gov.au"
DEFAULT_LIMIT = _settings.crawl_limit
DEFAULT_MAX_DEPTH = _settings.crawl_max_depth
DEFAULT_MAX_CONCURRENT = _settings.crawl_max_concurrent
DEFAULT_MAX_FILE_SIZE_MB = _settings.crawl_max_file_size_mb
DEFAULT_MAX_RETRIES = _settings.crawl_max_retries
DEFAULT_OUTPUT_EXTENSION = ".md"
DEFAULT_TIMEOUT = _settings.crawl_timeout
DEFAULT_URLS = "https://www.ato.gov.au/"
DEFAULT_WAIT_FOR = _settings.crawl_wait_for
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
