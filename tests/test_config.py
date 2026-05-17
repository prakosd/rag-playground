"""Tests for crawl4md.config — Pydantic model validation."""

import pytest

from crawl4md.config import CrawlerConfig, PageConfig


class TestCrawlerConfig:
    def test_valid_single_url(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.urls == ["https://example.com"]

    def test_valid_multiple_urls(self):
        cfg = CrawlerConfig(urls=["https://a.com", "https://b.com"])
        assert len(cfg.urls) == 2

    def test_urls_from_comma_string(self):
        cfg = CrawlerConfig(urls="https://a.com, https://b.com")
        assert cfg.urls == ["https://a.com", "https://b.com"]

    def test_empty_urls_rejected(self):
        with pytest.raises(ValueError, match="At least one URL"):
            CrawlerConfig(urls=[])

    def test_invalid_url_rejected(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            CrawlerConfig(urls=["not-a-url"])

    def test_defaults(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.limit == 1
        assert cfg.max_depth == 1
        assert cfg.exclude_paths == []
        assert cfg.include_only_paths == []
        assert cfg.max_concurrent == 1
        assert cfg.stealth is True
        assert cfg.headers == {}

    def test_stealth_disabled(self):
        cfg = CrawlerConfig(urls=["https://example.com"], stealth=False)
        assert cfg.stealth is False

    def test_headers_accepted(self):
        cfg = CrawlerConfig(urls=["https://example.com"], headers={"Accept-Language": "en"})
        assert cfg.headers == {"Accept-Language": "en"}

    def test_limit_must_be_positive(self):
        with pytest.raises(ValueError, match="at least 1"):
            CrawlerConfig(urls=["https://example.com"], limit=0)

    def test_max_depth_must_be_positive(self):
        with pytest.raises(ValueError, match="at least 1"):
            CrawlerConfig(urls=["https://example.com"], max_depth=0)

    @pytest.mark.parametrize("value", [0, -1])
    def test_max_concurrent_must_be_positive(self, value: int):
        with pytest.raises(ValueError, match="at least 1"):
            CrawlerConfig(urls=["https://example.com"], max_concurrent=value)

    @pytest.mark.parametrize("value", [1, 5])
    def test_max_concurrent_accepts_positive_values(self, value: int):
        cfg = CrawlerConfig(urls=["https://example.com"], max_concurrent=value)
        assert cfg.max_concurrent == value

    def test_exclude_paths_from_string(self):
        cfg = CrawlerConfig(urls=["https://example.com"], exclude_paths="/admin, /login")
        assert cfg.exclude_paths == ["/admin", "/login"]

    def test_invalid_regex_rejected(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            CrawlerConfig(urls=["https://example.com"], exclude_paths=["[invalid"])

    def test_include_only_paths_validated(self):
        cfg = CrawlerConfig(
            urls=["https://example.com"],
            include_only_paths=[r"/blog/.*"],
        )
        assert cfg.include_only_paths == [r"/blog/.*"]

    def test_compiled_path_patterns_are_cached_private_attrs(self):
        cfg = CrawlerConfig(
            urls=["https://example.com"],
            exclude_paths=[r"/admin"],
            include_only_paths=[r"/blog"],
        )

        assert cfg.compiled_exclude_paths[0].search("https://example.com/admin")
        assert cfg.compiled_include_only_paths[0].search("https://example.com/blog")
        dumped = cfg.model_dump(mode="json")
        assert "compiled_exclude_paths" not in dumped
        assert "compiled_include_only_paths" not in dumped

    def test_compiled_path_patterns_refresh_after_mutation(self):
        cfg = CrawlerConfig(urls=["https://example.com"], exclude_paths=[r"/admin"])

        cfg.exclude_paths.append(r"/private")

        assert [pattern.pattern for pattern in cfg.compiled_exclude_paths] == [
            r"/admin",
            r"/private",
        ]

    def test_compiled_path_patterns_refresh_after_model_copy_update(self):
        cfg = CrawlerConfig(urls=["https://example.com"], exclude_paths=[r"/admin"])

        updated = cfg.model_copy(update={"exclude_paths": [r"/private"]})

        assert [pattern.pattern for pattern in updated.compiled_exclude_paths] == [r"/private"]

    def test_max_retries_default(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.max_retries == 2

    def test_max_retries_zero_clamped(self):
        cfg = CrawlerConfig(urls=["https://example.com"], max_retries=0)
        assert cfg.max_retries == 2

    def test_max_retries_one_clamped(self):
        cfg = CrawlerConfig(urls=["https://example.com"], max_retries=1)
        assert cfg.max_retries == 2

    def test_max_retries_negative_clamped(self):
        cfg = CrawlerConfig(urls=["https://example.com"], max_retries=-1)
        assert cfg.max_retries == 2

    def test_max_retries_above_minimum_kept(self):
        cfg = CrawlerConfig(urls=["https://example.com"], max_retries=5)
        assert cfg.max_retries == 5


class TestPageConfig:
    def test_defaults(self):
        cfg = PageConfig()
        assert cfg.exclude_tags == ["nav", "script", "form", "style"]
        assert cfg.include_only_tags == []
        assert cfg.wait_until == "networkidle"
        assert cfg.wait_for is None
        assert cfg.timeout == 30
        assert cfg.max_file_size_mb == 15.0
        assert cfg.extract_main_content is True
        assert cfg.scan_full_page is True
        assert cfg.scroll_delay == 0.4
        assert cfg.flatten_shadow_dom is True

    def test_flatten_shadow_dom_can_be_disabled(self):
        cfg = PageConfig(flatten_shadow_dom=False)
        assert cfg.flatten_shadow_dom is False

    def test_wait_until_accepts_valid_values(self):
        for value in ("domcontentloaded", "networkidle", "load", "commit"):
            cfg = PageConfig(wait_until=value)
            assert cfg.wait_until == value

    def test_wait_until_rejects_invalid_value(self):
        with pytest.raises(ValueError):
            PageConfig(wait_until="invalid")

    def test_scroll_delay_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            PageConfig(scroll_delay=-1)

    def test_exclude_tags_from_string(self):
        cfg = PageConfig(exclude_tags="nav, footer", include_only_tags=[])
        assert cfg.exclude_tags == ["nav", "footer"]

    def test_tag_conflict_rejected(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            PageConfig(exclude_tags=["nav"], include_only_tags=["main"])

    def test_include_only_tags_clears_default_exclude(self):
        cfg = PageConfig(exclude_tags=[], include_only_tags=["main", "article"])
        assert cfg.include_only_tags == ["main", "article"]
        assert cfg.exclude_tags == []

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            PageConfig(timeout=-1)

    def test_zero_file_size_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            PageConfig(max_file_size_mb=0)

    def test_output_extension_default(self):
        cfg = PageConfig()
        assert cfg.output_extension == ".txt"

    def test_output_extension_md(self):
        cfg = PageConfig(output_extension=".md")
        assert cfg.output_extension == ".md"

    def test_output_extension_invalid_rejected(self):
        with pytest.raises(ValueError):
            PageConfig(output_extension=".html")

    def test_separate_items_default(self):
        cfg = PageConfig()
        assert cfg.separate_items is True

    def test_separate_items_disabled(self):
        cfg = PageConfig(separate_items=False)
        assert cfg.separate_items is False

    def test_item_selector_default(self):
        cfg = PageConfig()
        assert cfg.item_selector == ""

    def test_item_selector_stripped(self):
        cfg = PageConfig(item_selector="  div.product-card  ")
        assert cfg.item_selector == "div.product-card"

    def test_js_code_default(self):
        cfg = PageConfig()
        assert cfg.js_code == []

    def test_js_code_from_string(self):
        cfg = PageConfig(js_code="document.querySelector('button').click()")
        assert cfg.js_code == ["document.querySelector('button').click()"]

    def test_js_code_empty_string(self):
        cfg = PageConfig(js_code="")
        assert cfg.js_code == []

    def test_js_code_from_list(self):
        snippets = ["console.log('a')", "console.log('b')"]
        cfg = PageConfig(js_code=snippets)
        assert cfg.js_code == snippets
