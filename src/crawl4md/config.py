"""Configuration models for crawl4md."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

# Accepted URL schemes for seed URLs.
_VALID_URL_SCHEMES = ("http://", "https://")
# Default HTML tags excluded from extraction.
_DEFAULT_EXCLUDE_TAGS: list[str] = ["nav", "script", "form", "style"]
# Whether to strip the "www." prefix during URL normalization.
_DEFAULT_STRIP_WWW: bool = False


class CrawlerConfig(BaseModel):
    """Configuration for the web crawler."""

    urls: list[str]
    exclude_paths: list[str] = []
    include_only_paths: list[str] = []
    limit: int = 1
    max_depth: int = 1
    flush_interval: int = 10
    delay: float = 0
    stealth: bool = True
    strip_www: bool = _DEFAULT_STRIP_WWW
    headers: dict[str, str] = {}
    max_retries: int = 2

    @field_validator("urls", mode="before")
    @classmethod
    def parse_urls(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of URLs."""
        if isinstance(v, str):
            v = [u.strip() for u in v.split(",") if u.strip()]
        return v

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one URL is required.")
        for url in v:
            if not url.startswith(_VALID_URL_SCHEMES):
                raise ValueError(f"Invalid URL (must start with http:// or https://): {url}")
        return v

    @field_validator("exclude_paths", "include_only_paths", mode="before")
    @classmethod
    def parse_path_patterns(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of patterns."""
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("exclude_paths", "include_only_paths")
    @classmethod
    def validate_regex_patterns(cls, v: list[str]) -> list[str]:
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
        return v

    @field_validator("limit", "max_depth", "flush_interval")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Value must be at least 1.")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Delay must be non-negative.")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be non-negative.")
        return v


# Valid values for the Playwright navigation wait condition.
_WAIT_UNTIL_OPTIONS = Literal["domcontentloaded", "networkidle", "load", "commit"]
# Default navigation wait condition — waits until no network requests for 500ms.
_DEFAULT_WAIT_UNTIL: _WAIT_UNTIL_OPTIONS = "networkidle"
# Retry-round wait condition — faster, avoids networkidle timeout on analytics-heavy sites.
_FALLBACK_WAIT_UNTIL: _WAIT_UNTIL_OPTIONS = "domcontentloaded"


class PageConfig(BaseModel):
    """Configuration for page extraction."""

    exclude_tags: list[str] = _DEFAULT_EXCLUDE_TAGS
    include_only_tags: list[str] = []
    wait_until: _WAIT_UNTIL_OPTIONS = _DEFAULT_WAIT_UNTIL
    wait_for: float | None = None
    timeout: float = 30
    max_file_size_mb: float = 15.0
    extract_main_content: bool = True
    output_extension: Literal[".txt", ".md"] = ".txt"
    separate_items: bool = True
    item_selector: str = ""
    js_code: list[str] = []
    scan_full_page: bool = True
    scroll_delay: float = 0.4
    ocr_languages: list[str] = ["eng", "msa"]
    absolute_links: bool = True

    @field_validator("js_code", mode="before")
    @classmethod
    def parse_js_code(cls, v: Any) -> list[str]:
        """Accept a single JS string or a list of JS snippets."""
        if isinstance(v, str):
            v = v.strip()
            return [v] if v else []
        return v

    @field_validator("exclude_tags", "include_only_tags", "ocr_languages", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of tag names."""
        if isinstance(v, str):
            v = [t.strip() for t in v.split(",") if t.strip()]
        return v

    @field_validator("timeout", "scroll_delay")
    @classmethod
    def validate_non_negative_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Value must be non-negative.")
        return v

    @field_validator("max_file_size_mb")
    @classmethod
    def validate_max_file_size(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Max file size must be positive.")
        return v

    @field_validator("item_selector", mode="before")
    @classmethod
    def strip_item_selector(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def check_tag_conflict(self) -> PageConfig:
        if self.exclude_tags and self.include_only_tags:
            raise ValueError(
                "Cannot set both 'exclude_tags' and 'include_only_tags'. Use one or the other."
            )
        return self


class CrawlResult(BaseModel):
    """Result of crawling a single page."""

    url: str
    html: str = ""
    markdown: str = ""
    success: bool = True
    error: str | None = None
    redirected_url: str | None = None
    is_pdf: bool = False


class ExtractedPage(BaseModel):
    """A single page after content extraction."""

    url: str
    title: str = ""
    markdown: str = ""
