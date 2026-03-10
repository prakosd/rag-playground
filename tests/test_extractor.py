"""Tests for crawl4md.extractor — core extraction pipeline."""

from __future__ import annotations

from unittest.mock import patch

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor
from tests.conftest import MINIMAL_HTML, SIMPLE_HTML


class TestContentExtractor:
    def test_extract_skips_failed_results(self, failed_crawl_result):
        extractor = ContentExtractor()
        pages = extractor.extract([failed_crawl_result])
        assert pages == []

    def test_extract_main_content_with_trafilatura(self, simple_crawl_result):
        extractor = ContentExtractor(PageConfig(extract_main_content=True))
        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = "# Hello World\n\nMain content."
            pages = extractor.extract([simple_crawl_result])

        assert len(pages) == 1
        assert pages[0].url == "https://example.com/test"
        assert "Main content" in pages[0].markdown

    def test_extract_full_html_with_markdownify(self, simple_crawl_result):
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        pages = extractor.extract([simple_crawl_result])

        assert len(pages) == 1
        assert pages[0].url == "https://example.com/test"
        # markdownify should produce some markdown
        assert len(pages[0].markdown) > 0

    def test_extract_title(self):
        extractor = ContentExtractor()
        title = extractor._extract_title(SIMPLE_HTML)
        assert title == "Test Page"

    def test_extract_title_missing(self):
        extractor = ContentExtractor()
        title = extractor._extract_title("<html><body>no title</body></html>")
        assert title == ""

    def test_filter_tags_exclude(self):
        config = PageConfig(exclude_tags=["nav", "footer"], include_only_tags=[])
        extractor = ContentExtractor(config)
        html = "<div><nav>skip</nav><p>keep</p><footer>skip</footer></div>"
        filtered = extractor._filter_tags(html)
        assert "skip" not in filtered
        assert "keep" in filtered

    def test_filter_tags_include_only(self):
        config = PageConfig(exclude_tags=[], include_only_tags=["main"])
        extractor = ContentExtractor(config)
        html = "<div>outside</div><main><p>inside</p></main>"
        filtered = extractor._filter_tags(html)
        assert "inside" in filtered
        assert "outside" not in filtered

    def test_empty_html_produces_no_pages(self):
        result = CrawlResult(url="https://example.com", html="", success=True)
        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = ""
            extractor = ContentExtractor()
            pages = extractor.extract([result])
        assert pages == []

    def test_extract_multiple_results(self):
        results = [
            CrawlResult(url=f"https://example.com/p{i}", html=MINIMAL_HTML, success=True)
            for i in range(3)
        ]
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        pages = extractor.extract(results)
        assert len(pages) == 3


class TestFixMarkdownTables:
    """Tests for the _fix_markdown_tables post-processing."""

    def test_inserts_separator_when_missing(self):
        text = "Col A | Col B | Col C |\nval1 | val2 | val3 |\nval4 | val5 | val6 |"
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[0] == "| Col A | Col B | Col C |"
        assert lines[1] == "| --- | --- | --- |"
        assert lines[2] == "| val1 | val2 | val3 |"

    def test_preserves_existing_separator(self):
        text = "| Col A | Col B |\n|---|---|\n| val1 | val2 |"
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[0] == "| Col A | Col B |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| val1 | val2 |"

    def test_no_table_passes_through(self):
        text = "Just some text.\n\nNo tables here."
        result = ContentExtractor._fix_markdown_tables(text)
        assert result == text

    def test_single_row_table_no_separator_added(self):
        text = "Only | one | row |"
        result = ContentExtractor._fix_markdown_tables(text)
        # A single row doesn't need a separator (no data rows follow)
        assert "---" not in result

    def test_mixed_content_with_table(self):
        text = "# Heading\n\nSome text.\n\nHeader A | Header B |\ndata1 | data2 |\n\nMore text."
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[4] == "| Header A | Header B |"
        assert lines[5] == "| --- | --- |"
        assert lines[6] == "| data1 | data2 |"

    def test_trafilatura_table_output(self):
        """Simulate the actual trafilatura output for the HomeHub+ pricing table."""
        text = (
            "**HomeHub+ 5G**\n"
            "\n"
            "Ala Carte (price/month) | HomeHub+ 5G (price/month) | Savings | |\n"
            "TV+ Pass (Entertainment+/Asian+) | $30.56 | $82.00 | Save up to $16.54/mth |\n"
            "| 5Gbps Broadband | $45.00 | ||\n"
            "| Netflix Standard Plan (2 screens) | $22.98 | ||\n"
            "| Total monthly subscription | $98.54 |"
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        # Header normalized with leading pipe
        assert lines[2].startswith("| Ala Carte")
        # Separator should be inserted after header row
        assert "---" in lines[3]
        # First data row should follow with consistent pipes
        assert "$30.56" in lines[4]
        assert lines[4].startswith("|")
        # Rows with || get expanded to empty cells and padded to 4 columns
        assert lines[5].count("|") == lines[2].count("|")
        # Short row padded
        assert "Total monthly subscription" in lines[7]
        assert lines[7].count("|") == lines[2].count("|")


class TestCleanMarkdown:
    """Tests for the _clean_markdown post-processing pipeline."""

    def test_collapse_blank_lines(self):
        text = "Hello\n\n\n\n\nWorld\n\n\n\nEnd"
        result = ContentExtractor._collapse_blank_lines(text)
        assert result == "Hello\n\nWorld\n\nEnd"

    def test_collapse_blank_lines_preserves_single(self):
        text = "A\n\nB\n\nC"
        result = ContentExtractor._collapse_blank_lines(text)
        assert result == "A\n\nB\n\nC"

    def test_compact_product_listings_basic(self):
        text = "Product Alpha\n\n$49.90\n\nProduct Beta\n\n$29.00\n\nProduct Gamma\n\n$99.00"
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Product Alpha** \u2014 $49.90" in result
        assert "- **Product Beta** \u2014 $29.00" in result
        assert "- **Product Gamma** \u2014 $99.00" in result

    def test_compact_product_listings_with_badges(self):
        text = (
            "New\n\nProduct Alpha\n\n$49.90\n\n"
            "LNY Offers\n\nProduct Beta\n\n$29.00\n\n3 offers available\n\n"
            "Product Gamma\n\n$99.00\n\nAdd selected accessories!"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Product Alpha** \u2014 $49.90" in result
        assert "  New" in result
        assert "- **Product Beta** \u2014 $29.00" in result
        assert "  LNY Offers" in result
        assert "  3 offers available" in result
        assert "- **Product Gamma** \u2014 $99.00" in result
        assert "  Add selected accessories!" in result

    def test_compact_product_listings_no_trigger_below_threshold(self):
        """Fewer than 3 product-price pairs should NOT be compacted."""
        text = "Widget A\n\n$10.00\n\nWidget B\n\n$20.00\n\nSome article text."
        result = ContentExtractor._compact_product_listings(text)
        # Should remain unchanged — no bullet list
        assert "- **" not in result
        assert "Widget A" in result
        assert "$10.00" in result

    def test_compact_product_listings_with_from_prefix(self):
        text = "Plan A\n\nfrom $10.00\n\nPlan B\n\nfrom $20.00\n\nPlan C\n\nfrom $30.00"
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Plan A** \u2014 from $10.00" in result
        assert "- **Plan B** \u2014 from $20.00" in result
        assert "- **Plan C** \u2014 from $30.00" in result

    def test_compact_preserves_headings_and_tables(self):
        text = (
            "# Category\n\n"
            "Product A\n\n$10.00\n\n"
            "Product B\n\n$20.00\n\n"
            "Product C\n\n$30.00\n\n"
            "| Col | Val |\n| --- | --- |\n| a | 1 |"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert result.startswith("# Category")
        assert "- **Product A** \u2014 $10.00" in result
        assert "| Col | Val |" in result

    def test_dedup_paragraphs(self):
        text = "Hello world\n\nHello world\n\nSomething else\n\nSomething else\n\nFinal"
        result = ContentExtractor._dedup_paragraphs(text)
        assert result.count("Hello world") == 1
        assert result.count("Something else") == 1
        assert "Final" in result

    def test_dedup_paragraphs_non_consecutive_kept(self):
        text = "A\n\nB\n\nA\n\nC"
        result = ContentExtractor._dedup_paragraphs(text)
        assert result.count("A") == 2  # Non-consecutive A kept

    def test_clean_markdown_full_pipeline(self):
        """End-to-end: blank line collapse + product compaction + dedup."""
        text = (
            "Banner promo\n\n\n\n\n"
            "Banner promo\n\n"
            "iPhone Case\n\n$39.90\n\n"
            "Galaxy Case\n\n$58.00\n\n"
            "New\n\nAirPods\n\n$249.00"
        )
        result = ContentExtractor._clean_markdown(text)
        # Blank lines collapsed
        assert "\n\n\n" not in result
        # Dedup fired
        assert result.count("Banner promo") == 1
        # Product compaction fired (Banner promo becomes part of first name
        # since it's not a recognised badge keyword)
        assert "- **" in result
        assert "- **Galaxy Case** \u2014 $58.00" in result
        assert "- **AirPods** \u2014 $249.00" in result
        assert "  New" in result

    def test_article_content_not_compacted(self):
        """Normal article text with no price patterns should pass through."""
        text = (
            "# Heading\n\n"
            "This is an article about technology.\n\n"
            "It has multiple paragraphs with interesting content.\n\n"
            "And a conclusion at the end."
        )
        result = ContentExtractor._clean_markdown(text)
        assert "- **" not in result
        assert "# Heading" in result

    def test_compact_short_paragraphs_basic(self):
        text = "Line one\n\nLine two\n\nLine three\n\nLine four"
        result = ContentExtractor._compact_short_paragraphs(text)
        assert "- Line one" in result
        assert "- Line two" in result
        assert "- Line three" in result
        assert "- Line four" in result

    def test_compact_short_paragraphs_preserves_headings(self):
        text = "# Heading\n\nShort A\n\nShort B\n\nShort C\n\n## Another"
        result = ContentExtractor._compact_short_paragraphs(text)
        assert result.startswith("# Heading")
        assert "- Short A" in result
        assert "## Another" in result
        assert "- ## Another" not in result

    def test_compact_short_paragraphs_skips_multiline(self):
        """Multi-line paragraphs break the run and are kept as-is."""
        text = "Short A\n\nShort B\n\nThis is a longer\nmulti-line paragraph.\n\nShort C"
        result = ContentExtractor._compact_short_paragraphs(text)
        # Only 2 shorts before the multiline — below threshold
        assert "- Short A" not in result
        assert "multi-line paragraph" in result

    def test_compact_short_paragraphs_below_threshold(self):
        text = "Only two\n\nshort lines"
        result = ContentExtractor._compact_short_paragraphs(text)
        assert "- " not in result

    def test_compact_short_paragraphs_preserves_existing_lists(self):
        """Lines already formatted as list items act as boundaries."""
        text = "Item A\n\nItem B\n\nItem C\n\n- Already a list\n\nItem D"
        result = ContentExtractor._compact_short_paragraphs(text)
        assert "- Item A" in result
        assert "- Item B" in result
        assert "- Already a list" in result
        assert "- - Already" not in result


class TestCoverageFallback:
    """Tests for automatic trafilatura-to-markdownify fallback on low coverage."""

    def test_fallback_triggers_on_low_coverage(self):
        """When trafilatura returns very little, markdownify is used instead."""
        html = (
            "<html><head><title>Plans</title></head><body>"
            + "".join(
                f'<div class="plan"><h3>Plan {i}</h3>'
                f"<p>Details about plan {i} with features and pricing info.</p></div>"
                for i in range(30)
            )
            + "</body></html>"
        )
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/plans", html=html, success=True)

        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            # Simulate trafilatura returning almost nothing
            mock_traf.extract.return_value = "tiny"
            page = extractor._extract_page(result)

        # Should contain markdownify output (all plans present)
        assert "Plan 0" in page.markdown
        assert "Plan 29" in page.markdown

    def test_no_fallback_when_coverage_is_good(self):
        """When trafilatura returns enough content, no fallback happens."""
        html = (
            "<html><head><title>Test</title></head><body>"
            "<p>Main content here with enough detail.</p></body></html>"
        )
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com", html=html, success=True)

        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = "Main content here with enough detail."
            page = extractor._extract_page(result)

        assert "Main content here" in page.markdown


class TestPreserveStrikethrough:
    """Tests for _preserve_strikethrough — converting <del>/<s> to ~~text~~."""

    def test_del_tag_converted(self):
        html = "<p><del>$2,128.00</del>$1,828.00</p>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert "~~$2,128.00~~$1,828.00" in result
        assert "<del>" not in result

    def test_s_tag_converted(self):
        html = "<span><s>$1,928.00</s>$1,628.00</span>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert "~~$1,928.00~~$1,628.00" in result
        assert "<s>" not in result

    def test_strike_tag_converted(self):
        html = "<p><strike>$500.00</strike>$399.00</p>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert "~~$500.00~~$399.00" in result

    def test_no_strikethrough_passes_through(self):
        html = "<p>$1,828.00</p>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert result == html

    def test_multiple_strikethroughs(self):
        html = "<p><del>$100</del>$80</p><p><del>$200</del>$150</p>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert "~~$100~~$80" in result
        assert "~~$200~~$150" in result

    def test_case_insensitive(self):
        html = "<p><DEL>$100</DEL>$80</p>"
        result = ContentExtractor._preserve_strikethrough(html)
        assert "~~$100~~$80" in result


class TestValidateMarkdown:
    """Tests for ContentExtractor._validate_markdown."""

    def test_valid_markdown_passes_through(self):
        md = "# Hello\n\nSome paragraph with **bold** and *italic*.\n"
        result = ContentExtractor._validate_markdown(md)
        assert "Hello" in result
        assert "bold" in result
        assert "italic" in result

    def test_empty_string_returns_unchanged(self):
        assert ContentExtractor._validate_markdown("") == ""
        assert ContentExtractor._validate_markdown("   ") == "   "

    def test_preserves_words_numbers_punctuation(self):
        md = "The price is $49.99, discounted from $79.99; save 37%!\n"
        result = ContentExtractor._validate_markdown(md)
        for token in ["price", "$49.99,", "$79.99;", "37%!"]:
            assert token in result

    def test_preserves_table_content(self):
        md = "| Product | Price |\n| --- | --- |\n| Widget A | $19.99 |\n| Widget B | $29.99 |\n"
        result = ContentExtractor._validate_markdown(md)
        assert "Widget A" in result
        assert "$19.99" in result
        assert "Widget B" in result
        assert "$29.99" in result

    def test_preserves_strikethrough(self):
        md = "~~old price~~ new price\n"
        result = ContentExtractor._validate_markdown(md)
        assert "old" in result
        assert "price" in result
        assert "new" in result

    def test_preserves_links(self):
        md = "Visit [Example Site](https://example.com) for details.\n"
        result = ContentExtractor._validate_markdown(md)
        assert "Example Site" in result
        assert "https://example.com" in result
        assert "details" in result

    def test_graceful_degradation_on_exception(self):
        md = "# Some valid content\n\nWith paragraphs.\n"
        with patch("crawl4md.extractor.mdformat") as mock_mdf:
            mock_mdf.text.side_effect = RuntimeError("parse failed")
            result = ContentExtractor._validate_markdown(md)
        assert result == md

    def test_content_loss_returns_original(self):
        md = "# Title\n\nImportant content with $100 price.\n"
        with patch("crawl4md.extractor.mdformat") as mock_mdf:
            # Simulate mdformat dropping content
            mock_mdf.text.return_value = "# Title\n\nImportant content.\n"
            result = ContentExtractor._validate_markdown(md)
        # Original should be returned because "$100" and "price." were lost
        assert result == md

    def test_content_preserved_returns_formatted(self):
        md = "# Title\n\nSome   content  here.\n"
        with patch("crawl4md.extractor.mdformat") as mock_mdf:
            # mdformat normalizes whitespace but keeps all tokens
            mock_mdf.text.return_value = "# Title\n\nSome content here.\n"
            result = ContentExtractor._validate_markdown(md)
        assert result == "# Title\n\nSome content here.\n"


class TestExtractContentTokens:
    """Tests for ContentExtractor._extract_content_tokens."""

    def test_strips_md_syntax(self):
        md = "# Hello **world** and `code`"
        tokens = ContentExtractor._extract_content_tokens(md)
        assert tokens["Hello"] == 1
        assert tokens["world"] == 1
        assert tokens["code"] == 1
        # MD syntax chars should not form standalone tokens
        assert "#" not in tokens

    def test_preserves_currency_and_numbers(self):
        md = "Price: $49.99, was $79.99"
        tokens = ContentExtractor._extract_content_tokens(md)
        assert tokens["$49.99,"] == 1
        assert tokens["$79.99"] == 1
        assert tokens["Price:"] == 1

    def test_counts_duplicates(self):
        md = "hello hello hello world"
        tokens = ContentExtractor._extract_content_tokens(md)
        assert tokens["hello"] == 3
        assert tokens["world"] == 1
