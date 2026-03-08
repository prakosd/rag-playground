"""Tests for crawl4md.extractor — ContentExtractor."""

from __future__ import annotations

from unittest.mock import patch

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import _ITEM_SENTINEL, ContentExtractor
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
        text = (
            "Col A | Col B | Col C |\n"
            "val1 | val2 | val3 |\n"
            "val4 | val5 | val6 |"
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[0] == "| Col A | Col B | Col C |"
        assert lines[1] == "| --- | --- | --- |"
        assert lines[2] == "| val1 | val2 | val3 |"

    def test_preserves_existing_separator(self):
        text = (
            "| Col A | Col B |\n"
            "|---|---|\n"
            "| val1 | val2 |"
        )
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
        text = (
            "# Heading\n"
            "\n"
            "Some text.\n"
            "\n"
            "Header A | Header B |\n"
            "data1 | data2 |\n"
            "\n"
            "More text."
        )
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
        text = (
            "Product Alpha\n\n$49.90\n\n"
            "Product Beta\n\n$29.00\n\n"
            "Product Gamma\n\n$99.00"
        )
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
        text = (
            "Plan A\n\nfrom $10.00\n\n"
            "Plan B\n\nfrom $20.00\n\n"
            "Plan C\n\nfrom $30.00"
        )
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


class TestInsertItemSeparators:
    """Tests for _insert_item_separators and _find_repeated_items."""

    PRODUCT_CARDS_HTML = """
    <html><body>
    <div class="product-list">
      <div class="product-card"><h3>Galaxy S26 Ultra 5G</h3><p>from $76.16/mth</p><p>15 offers available</p></div>
      <div class="product-card"><h3>iPhone 17 Pro Max</h3><p>from $42.12/mth</p><p>12 offers available</p></div>
      <div class="product-card"><h3>Find X9 Pro 5G</h3><p>from $46.29/mth</p><p>11 offers available</p></div>
      <div class="product-card"><h3>Reno15 Pro Max 5G</h3><p>from $25.37/mth</p><p>10 offers available</p></div>
    </div>
    </body></html>
    """

    def test_auto_detect_inserts_sentinels(self):
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=True)
        # Should insert sentinels between items (3 separators for 4 items)
        assert result.count(_ITEM_SENTINEL) == 3

    def test_auto_detect_inserts_hr(self):
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=False)
        assert result.count("<hr") >= 3

    def test_explicit_selector(self):
        config = PageConfig(
            separate_items=True, item_selector="div.product-card", exclude_tags=[]
        )
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=True)
        assert result.count(_ITEM_SENTINEL) == 3

    def test_no_items_returns_unchanged(self):
        html = "<html><body><p>Just text</p></body></html>"
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(html, use_sentinel=True)
        assert _ITEM_SENTINEL not in result

    def test_fewer_than_3_items_auto_detect_skips(self):
        html = """
        <html><body>
        <div class="list">
          <div class="card"><p>Item A with enough text to pass the length threshold</p></div>
          <div class="card"><p>Item B with enough text to pass the length threshold</p></div>
        </div>
        </body></html>
        """
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(html, use_sentinel=True)
        assert _ITEM_SENTINEL not in result

    def test_nav_items_ignored_by_auto_detect(self):
        html = """
        <html><body>
        <nav>
          <div class="nav-item"><a>Home page link with enough text content</a></div>
          <div class="nav-item"><a>About page link with enough text content</a></div>
          <div class="nav-item"><a>Contact page link with enough text content</a></div>
        </nav>
        <p>Body content here.</p>
        </body></html>
        """
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(html, use_sentinel=True)
        assert _ITEM_SENTINEL not in result

    def test_integration_trafilatura_with_separators(self):
        """Full pipeline: separate_items=True with trafilatura mode."""
        config = PageConfig(
            separate_items=True, extract_main_content=True, exclude_tags=[]
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True)
        page = extractor._extract_page(result_obj)
        # The sentinel should have been replaced with ---
        assert _ITEM_SENTINEL not in page.markdown
        # Products should appear grouped (with --- separators or as structured output)
        assert "Galaxy S26" in page.markdown
        assert "iPhone 17" in page.markdown

    def test_integration_markdownify_with_separators(self):
        """Full pipeline: separate_items=True with markdownify mode."""
        config = PageConfig(
            separate_items=True, extract_main_content=False,
            exclude_tags=[], include_only_tags=[]
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True)
        page = extractor._extract_page(result_obj)
        # markdownify preserves <hr> as ---
        assert page.markdown.count("---") >= 3

    def test_separate_items_false_no_separators(self):
        """When separate_items=False, no separators are inserted."""
        config = PageConfig(separate_items=False, exclude_tags=[])
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True)
        page = extractor._extract_page(result_obj)
        assert _ITEM_SENTINEL not in page.markdown

    MIXED_CLASS_HTML = """
    <html><body>
    <div class="product-list">
      <div class="product-card bg-white"><h3>Galaxy S26 Ultra 5G</h3><p>from $76.16/mth</p><p>15 offers available</p></div>
      <div class="product-card bg-white"><h3>Galaxy S26+ 5G</h3><p>from $67.83/mth</p><p>13 offers available</p></div>
      <div class="product-card bg-tint-blue"><p>We got you covered with the new 5G Unlimited+ Discover our new plans!</p><a href="#">Learn more</a></div>
      <div class="product-card bg-white"><h3>Galaxy S26 5G</h3><p>from $59.91/mth</p><p>13 offers available</p></div>
      <div class="product-card bg-white"><h3>Magic8 Pro</h3><p>from $44.62/mth</p><p>9 offers available</p></div>
    </div>
    </body></html>
    """

    def test_interstitial_sibling_gets_separator(self):
        """A differently-classed sibling between matched items gets a separator."""
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.MIXED_CLASS_HTML, use_sentinel=True)
        # 4 bg-white items + 1 interstitial bg-tint-blue = 5 total items → 4 separators
        assert result.count(_ITEM_SENTINEL) == 4

    def test_interstitial_sibling_not_included_with_explicit_selector(self):
        """Explicit item_selector should NOT include interstitial siblings."""
        config = PageConfig(
            separate_items=True, item_selector="div.bg-white", exclude_tags=[]
        )
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.MIXED_CLASS_HTML, use_sentinel=True)
        # Only the 4 bg-white items are selected → 3 separators
        assert result.count(_ITEM_SENTINEL) == 3

    def test_interstitial_short_text_excluded(self):
        """Interstitial siblings with very short text (<20 chars) are skipped."""
        html = """
        <html><body>
        <div class="list">
          <div class="card"><p>Product Alpha with enough descriptive text for detection</p></div>
          <div class="card"><p>Product Bravo with enough descriptive text for detection</p></div>
          <div class="spacer"><p>tiny</p></div>
          <div class="card"><p>Product Charlie with enough descriptive text for detection</p></div>
          <div class="card"><p>Product Delta with enough descriptive text for detection</p></div>
        </div>
        </body></html>
        """
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(html, use_sentinel=True)
        # 4 cards matched, spacer too short → 3 separators between 4 items
        assert result.count(_ITEM_SENTINEL) == 3

    def test_integration_mixed_class_product_names(self):
        """Full pipeline (markdownify): banner div gets its own separator."""
        config = PageConfig(
            separate_items=True, extract_main_content=False,
            exclude_tags=[], include_only_tags=[],
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com", html=self.MIXED_CLASS_HTML, success=True,
        )
        page = extractor._extract_page(result_obj)
        # With interstitial separator, the banner div is isolated:
        # at least 4 --- separators (5 items) should appear in the output
        assert page.markdown.count("---") >= 4
        # Product names should remain present and separate from banner
        assert "Galaxy S26 Ultra 5G" in page.markdown
        assert "Galaxy S26 5G" in page.markdown
        assert "Magic8 Pro" in page.markdown


class TestIncludeInterstitialSiblings:
    """Tests for _include_interstitial_siblings — expanding auto-detected groups."""

    def test_interstitial_included_between_matched(self):
        from bs4 import BeautifulSoup, Tag
        html = """
        <div class="list">
          <div class="card">Product A with enough text</div>
          <div class="banner">Banner promo with enough text here</div>
          <div class="card">Product B with enough text</div>
          <div class="card">Product C with enough text</div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.card")
        result = ContentExtractor._include_interstitial_siblings(cards)
        # 3 cards + 1 banner between them = 4 elements
        assert len(result) == 4
        # Banner should be in position 1 (between first card and second card)
        assert "banner" in result[1].get("class", [])

    def test_no_interstitial_when_all_adjacent(self):
        from bs4 import BeautifulSoup
        html = """
        <div class="list">
          <div class="card">Product A with enough text</div>
          <div class="card">Product B with enough text</div>
          <div class="card">Product C with enough text</div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.card")
        result = ContentExtractor._include_interstitial_siblings(cards)
        assert len(result) == 3

    def test_empty_items_returns_empty(self):
        result = ContentExtractor._include_interstitial_siblings([])
        assert result == []

    def test_single_item_returns_unchanged(self):
        from bs4 import BeautifulSoup
        html = '<div class="list"><div class="card">One product</div></div>'
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.card")
        result = ContentExtractor._include_interstitial_siblings(cards)
        assert len(result) == 1


class TestMultiPriceProductListings:
    """Tests for _compact_product_listings handling multi-price products."""

    def test_standalone_from_merged_into_price(self):
        """Standalone 'from' on its own line should be merged into the price."""
        text = (
            "Galaxy S26\n\nfrom\n\n$76.16/mth\n\n"
            "iPhone 17\n\nfrom\n\n$42.12/mth\n\n"
            "Find X9\n\nfrom\n\n$46.29/mth"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26** — from $76.16/mth" in result
        assert "- **iPhone 17** — from $42.12/mth" in result
        assert "- **Find X9** — from $46.29/mth" in result

    def test_multi_price_monthly_plus_outright(self):
        """Monthly + outright prices on separate lines should be joined."""
        text = (
            "Galaxy S26\n\n$76.16/mth\n\nor$2,128.00$1,828.00\n\n"
            "iPhone 17\n\n$42.12/mth\n\nor$$1,299.00\n\n"
            "Find X9\n\n$46.29/mth\n\nor$$1,599.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26**" in result
        assert "$76.16/mth" in result
        assert "~~$2,128.00~~ $1,828.00" in result
        assert "- **iPhone 17**" in result
        assert "$1,299.00" in result
        assert "- **Find X9**" in result

    def test_starhub_full_pattern(self):
        """Realistic StarHub pattern: badge + name + from + monthly + outright + offers."""
        text = (
            "Preorder\n\nGalaxy S26 Ultra 5G\n\nfrom\n\n$76.16/mth\n\n"
            "or$2,128.00$1,828.00\n\n15 offers available\n\n"
            "LNY Offers\n\niPhone 17\n\nfrom\n\n$42.12/mth\n\n"
            "or$$1,299.00\n\n12 offers available\n\n"
            "New\n\nReno15 Pro Max 5G\n\nfrom\n\n$25.37/mth\n\n"
            "or$$1,049.00\n\n10 offers available"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26 Ultra 5G**" in result
        assert "from $76.16/mth" in result
        assert "~~$2,128.00~~ $1,828.00" in result
        assert "Preorder" in result
        assert "15 offers available" in result
        assert "- **iPhone 17**" in result
        assert "LNY Offers" in result
        assert "- **Reno15 Pro Max 5G**" in result

    def test_from_not_in_product_name(self):
        """Standalone 'from' should not appear in the product name."""
        text = (
            "Product A\n\nfrom\n\n$10.00\n\n"
            "Product B\n\nfrom\n\n$20.00\n\n"
            "Product C\n\nfrom\n\n$30.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Product A** — from $10.00" in result
        assert "Product A from" not in result
        assert "- **Product B** — from $20.00" in result
        assert "- **Product C** — from $30.00" in result


class TestUpdatedPriceRegex:
    """Tests for the updated price regex in _compact_product_listings."""

    def test_price_with_mth_suffix(self):
        text = (
            "Galaxy S26\n\n$76.16/mth\n\n"
            "iPhone 17\n\n$42.12/mth\n\n"
            "Find X9\n\n$46.29/mth"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26** — $76.16/mth" in result
        assert "- **iPhone 17** — $42.12/mth" in result

    def test_price_with_or_prefix(self):
        text = (
            "Product A\n\nor$1,499.00\n\n"
            "Product B\n\nor$1,299.00\n\n"
            "Product C\n\nor$999.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Product A** — or $1,499.00" in result

    def test_double_price_original_discounted(self):
        text = (
            "Galaxy S26 Ultra\n\n$2,128.00$1,828.00\n\n"
            "Galaxy S26+\n\n$1,928.00$1,628.00\n\n"
            "Galaxy S26\n\n$1,738.00$1,438.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26 Ultra** — $2,128.00$1,828.00" in result
        assert "- **Galaxy S26+** — $1,928.00$1,628.00" in result


class TestSupplementarySections:
    """Tests for _extract_supplementary_sections — auto-detection of FAQ/accordion content."""

    def test_css_class_faq_detected(self):
        html = """
        <html><body>
        <main><p>Main content here, long enough for trafilatura.</p></main>
        <div class="faqs">
          <h3>What is the return policy?</h3>
          <p>You can return items within 30 days.</p>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "return policy" in sections[0]

    def test_css_id_faq_detected(self):
        html = """
        <html><body>
        <div id="faq-section">
          <h3>How do I cancel?</h3>
          <p>Go to account settings to cancel your plan easily.</p>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "cancel" in sections[0]

    def test_accordion_class_detected(self):
        html = """
        <html><body>
        <div class="accordion">
          <div class="accordion-item"><p>Question about billing and how it works</p></div>
          <div class="accordion-item"><p>Question about shipping and delivery options</p></div>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "billing" in sections[0]

    def test_schema_org_faqpage_detected(self):
        html = """
        <html><body>
        <div itemscope itemtype="https://schema.org/FAQPage">
          <div itemprop="mainEntity" itemscope itemtype="https://schema.org/Question">
            <h3 itemprop="name">What payment methods do you accept?</h3>
            <div itemprop="acceptedAnswer" itemscope itemtype="https://schema.org/Answer">
              <p itemprop="text">We accept Visa, Mastercard, and PayPal.</p>
            </div>
          </div>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "payment methods" in sections[0]

    def test_details_summary_detected(self):
        html = """
        <html><body>
        <div class="help">
          <details><summary>How do I reset my password?</summary><p>Click forgot password on the login page.</p></details>
          <details><summary>Can I change my email?</summary><p>Yes, go to account settings to update it.</p></details>
          <details><summary>Where is my order?</summary><p>Check your order status in your account dashboard.</p></details>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "reset my password" in sections[0]
        assert "change my email" in sections[0]

    def test_heading_with_faq_text_detected(self):
        html = """
        <html><body>
        <div>
          <h2>Frequently Asked Questions</h2>
          <p>Here are some common questions about our service and how to use it.</p>
          <p>We accept returns within 14 days of purchase for all products.</p>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1
        assert "common questions" in sections[0]

    def test_no_faq_sections_returns_empty(self):
        html = """
        <html><body>
        <main><p>Just a normal page with nothing FAQ-related.</p></main>
        <footer><p>Copyright 2026</p></footer>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert sections == []

    def test_small_fragment_ignored(self):
        """Elements with very little text (<30 chars) are skipped."""
        html = """
        <html><body>
        <div class="faq"><span>Short</span></div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert sections == []

    def test_deduplication_across_heuristics(self):
        """An element matched by both class and heading heuristics appears only once."""
        html = """
        <html><body>
        <div class="faq-section">
          <h3>FAQ</h3>
          <p>This section has answers to frequently asked questions about our products.</p>
        </div>
        </body></html>
        """
        sections = ContentExtractor._extract_supplementary_sections(html)
        assert len(sections) == 1

    def test_integration_main_content_includes_faq(self):
        """Full pipeline: trafilatura + supplementary FAQ recovery."""
        html = """
        <html><head><title>Store</title></head>
        <body>
        <main>
          <h1>Our Products</h1>
          <p>We offer a wide range of products for everyday use. Browse our catalog and
          find exactly what you need at competitive prices with free shipping.</p>
        </main>
        <div class="faqs">
          <h3>Frequently Asked Questions</h3>
          <p>How long does shipping take? We typically deliver within 3-5 business days
          across all regions in the country.</p>
        </div>
        </body></html>
        """
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/store", html=html, success=True)
        page = extractor._extract_page(result)
        assert "shipping take" in page.markdown


class TestFaqFormatting:
    """Tests for _format_faq_questions — promoting Q&A lines to headings."""

    def test_question_lines_promoted_to_headings(self):
        text = "What is your return policy?\n\nYou can return within 30 days."
        result = ContentExtractor._format_faq_questions(text)
        assert result == "### What is your return policy?\n\nYou can return within 30 days."

    def test_multiple_questions(self):
        text = (
            "What payment methods do you accept?\n\n"
            "We accept Visa and Mastercard.\n\n"
            "How long does shipping take?\n\n"
            "Delivery takes 3-5 business days."
        )
        result = ContentExtractor._format_faq_questions(text)
        assert "### What payment methods do you accept?" in result
        assert "### How long does shipping take?" in result
        assert "We accept Visa and Mastercard." in result
        assert "Delivery takes 3-5 business days." in result

    def test_existing_headings_not_doubled(self):
        text = "### What is this?\n\nAn answer."
        result = ContentExtractor._format_faq_questions(text)
        assert result.count("###") == 1

    def test_answers_not_promoted(self):
        text = "What is this?\n\nThis is a long answer that explains everything."
        result = ContentExtractor._format_faq_questions(text)
        assert "### What is this?" in result
        assert "### This is a long answer" not in result

    def test_list_items_not_promoted(self):
        text = "- Is this a question?\n\nSome answer."
        result = ContentExtractor._format_faq_questions(text)
        assert "### - Is this" not in result

    def test_multiline_paragraph_not_promoted(self):
        text = "First line\nends with question?\n\nAnswer."
        result = ContentExtractor._format_faq_questions(text)
        assert "###" not in result

    def test_integration_faq_formatted_in_pipeline(self):
        """Full pipeline: supplementary FAQ section gets question headings."""
        html = """
        <html><head><title>Store</title></head>
        <body>
        <main>
          <h1>Our Products</h1>
          <p>We offer a wide range of products for everyday use. Browse our catalog and
          find exactly what you need at competitive prices with free shipping.</p>
        </main>
        <div class="faqs">
          <h3>Frequently Asked Questions</h3>
          <p>What is your return policy?</p>
          <p>You can return items within 30 days of purchase for a full refund.</p>
          <p>How long does shipping take?</p>
          <p>We typically deliver within 3-5 business days across all regions.</p>
        </div>
        </body></html>
        """
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/store", html=html, success=True)
        page = extractor._extract_page(result)
        assert "### What is your return policy?" in page.markdown
        assert "### How long does shipping take?" in page.markdown


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


class TestSentinelOrdering:
    """Tests that sentinel replacement happens before _clean_markdown."""

    def test_sentinels_replaced_before_product_compaction(self):
        """Products separated by sentinels should not bleed across boundaries."""
        config = PageConfig(
            separate_items=True, extract_main_content=True, exclude_tags=[],
        )
        extractor = ContentExtractor(config)

        # Simulate trafilatura output with sentinels between products
        trafilatura_output = (
            "Galaxy S26 Ultra 5G\n\n"
            "from $76.16/mth\n\n"
            f"{_ITEM_SENTINEL}\n\n"
            "iPhone 17 Pro\n\n"
            "from $42.12/mth\n\n"
            f"{_ITEM_SENTINEL}\n\n"
            "Find X9 Pro 5G\n\n"
            "from $46.29/mth"
        )
        html = "<html><head><title>Store</title></head><body><p>content</p></body></html>"
        result = CrawlResult(url="https://example.com", html=html, success=True)

        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = trafilatura_output
            page = extractor._extract_page(result)

        # Sentinels must be gone
        assert _ITEM_SENTINEL not in page.markdown
        # --- separators should be present
        assert "---" in page.markdown


class TestReformatSeparatedItems:
    """Tests for _reformat_separated_items — structured product formatting."""

    def test_basic_product_sections(self):
        text = (
            "---\n\n"
            "Galaxy S26 Ultra 5G\n\nfrom $76.16/mth\n\nor$2,128.00$1,828.00\n\n"
            "Preorder\n\n15 offers available\n\n"
            "---\n\n"
            "iPhone 17 Pro\n\nfrom $42.12/mth\n\nor$$1,299.00\n\n"
            "LNY Offers\n\n12 offers available\n\n"
            "---\n\n"
            "Find X9 Pro 5G\n\nfrom $46.29/mth\n\nor$$1,599.00\n\n"
            "LNY Offers\n\n11 offers available\n\n"
            "---\n\n"
            "Reno15 5G\n\nfrom $25.37/mth\n\nor$$829.00\n\n"
            "New\n\n9 offers available"
        )
        result = ContentExtractor._reformat_separated_items(text)
        # Product names should be bold
        assert "- **Galaxy S26 Ultra 5G**" in result
        assert "- **iPhone 17 Pro**" in result
        assert "- **Find X9 Pro 5G**" in result
        assert "- **Reno15 5G**" in result

    def test_strikethrough_price_preserved(self):
        text = (
            "---\n\n"
            "Galaxy S26 Ultra 5G\n\nfrom $76.16/mth\n\n"
            "or~~$2,128.00~~$1,828.00\n\n15 offers available\n\n"
            "---\n\n"
            "Galaxy S26+ 5G\n\nfrom $67.83/mth\n\n"
            "or~~$1,928.00~~$1,628.00\n\n13 offers available\n\n"
            "---\n\n"
            "Galaxy S26 5G\n\nfrom $59.91/mth\n\n"
            "or~~$1,738.00~~$1,438.00\n\n13 offers available\n\n"
            "---"
        )
        result = ContentExtractor._reformat_separated_items(text)
        assert "- **Galaxy S26 Ultra 5G**" in result
        assert "~~" in result  # Strikethrough preserved

    def test_double_dollar_normalized(self):
        text = (
            "---\n\n"
            "iPhone 17\n\nfrom $42.12/mth\n\nor$$1,299.00\n\n12 offers available\n\n"
            "---\n\n"
            "iPhone Air\n\nfrom $37.95/mth\n\nor$$1,599.00\n\n11 offers available\n\n"
            "---\n\n"
            "iPhone 17 Pro\n\nfrom $72.87/mth\n\nor$$1,749.00\n\n12 offers available\n\n"
            "---"
        )
        result = ContentExtractor._reformat_separated_items(text)
        assert "- **iPhone 17**" in result
        # Double dollar should be normalized
        assert "$$" not in result

    def test_fewer_than_3_separators_passes_through(self):
        text = "Hello\n\n---\n\nWorld\n\n---\n\nEnd"
        result = ContentExtractor._reformat_separated_items(text)
        assert result == text

    def test_non_product_sections_pass_through(self):
        """Sections without prices are left unchanged."""
        text = (
            "# Main heading\n\n"
            "---\n\n"
            "Galaxy S26\n\nfrom $76.16/mth\n\n15 offers available\n\n"
            "---\n\n"
            "iPhone 17\n\nfrom $42.12/mth\n\n12 offers available\n\n"
            "---\n\n"
            "Find X9\n\nfrom $46.29/mth\n\n11 offers available\n\n"
            "---\n\n"
            "Some article text without any prices at all"
        )
        result = ContentExtractor._reformat_separated_items(text)
        assert "- **Galaxy S26**" in result
        assert "Some article text without any prices at all" in result

    def test_badges_collected(self):
        text = (
            "---\n\n"
            "Galaxy S26\n\nPreorder\n\nfrom $76.16/mth\n\n15 offers available\n\n"
            "---\n\n"
            "iPhone 17\n\nLNY Offers\n\nfrom $42.12/mth\n\n12 offers available\n\n"
            "---\n\n"
            "Find X9\n\nNew\n\nfrom $46.29/mth\n\n11 offers available\n\n"
            "---"
        )
        result = ContentExtractor._reformat_separated_items(text)
        assert "Preorder" in result
        assert "LNY Offers" in result
        assert "New" in result

    def test_banner_text_not_used_as_product_name(self):
        """Banner text in a section should not become the product name."""
        text = (
            "---\n\n"
            "We got you covered with the new 5G Unlimited+ Discover our new mobile plans!\n\n"
            "Preorder\n\nGalaxy S26 5G\n\nfrom $59.91/mth\n\n"
            "or~~$1,738.00~~$1,438.00\n\n13 offers available\n\n"
            "---\n\n"
            "Galaxy S26 Ultra 5G\n\nPreorder\n\nfrom $76.16/mth\n\n"
            "or~~$2,128.00~~$1,828.00\n\n15 offers available\n\n"
            "---\n\n"
            "Galaxy S26+ 5G\n\nPreorder\n\nfrom $67.83/mth\n\n"
            "or~~$1,928.00~~$1,628.00\n\n13 offers available\n\n"
            "---"
        )
        result = ContentExtractor._reformat_separated_items(text)
        # Product name should be the short actual name, not the banner
        assert "- **Galaxy S26 5G**" in result
        assert "- **Galaxy S26 Ultra 5G**" in result
        # Banner text should NOT appear as a product name
        assert "- **We got you covered" not in result

    def test_name_prefers_last_short_line(self):
        """When multiple unclassified lines exist, prefer the last short one."""
        text = (
            "---\n\n"
            "Some long promotional banner text that describes various features and benefits\n\n"
            "iPhone 17 Pro\n\nfrom $72.87/mth\n\n12 offers available\n\n"
            "---\n\n"
            "Another promotional line about amazing deals and great pricing options\n\n"
            "Find X9 Pro 5G\n\nfrom $46.29/mth\n\n11 offers available\n\n"
            "---\n\n"
            "More banner text about new plans\n\n"
            "Reno15 5G\n\nfrom $25.37/mth\n\n9 offers available\n\n"
            "---"
        )
        result = ContentExtractor._reformat_separated_items(text)
        assert "- **iPhone 17 Pro**" in result
        assert "- **Find X9 Pro 5G**" in result
        assert "- **Reno15 5G**" in result


class TestFormatOutrightPrice:
    """Tests for _format_outright_price — normalizing price display."""

    def test_double_dollar_normalized(self):
        assert ContentExtractor._format_outright_price("or$$1,499.00") == "or $1,499.00"

    def test_concatenated_prices_get_strikethrough(self):
        result = ContentExtractor._format_outright_price("or$2,128.00$1,828.00")
        assert result == "or ~~$2,128.00~~ $1,828.00"

    def test_already_strikethrough_preserved(self):
        result = ContentExtractor._format_outright_price("or~~$2,128.00~~$1,828.00")
        assert "~~$2,128.00~~" in result

    def test_simple_price_gets_space(self):
        assert ContentExtractor._format_outright_price("or$999.00") == "or $999.00"

    def test_concatenated_no_prefix(self):
        result = ContentExtractor._format_outright_price("$2,128.00$1,828.00")
        assert result == "~~$2,128.00~~ $1,828.00"


class TestUpdatedPriceRegexExtended:
    """Tests for price regex handling $$, ~~, and other patterns."""

    def test_double_dollar_price(self):
        text = (
            "Product A\n\nor$$1,499.00\n\n"
            "Product B\n\nor$$1,299.00\n\n"
            "Product C\n\nor$$999.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Product A**" in result

    def test_strikethrough_price(self):
        text = (
            "Galaxy S26\n\n~~$2,128.00~~$1,828.00\n\n"
            "Galaxy S26+\n\n~~$1,928.00~~$1,628.00\n\n"
            "Galaxy S26 5G\n\n~~$1,738.00~~$1,438.00"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26**" in result


class TestBadgeVsNameHeuristic:
    """Tests for the improved badge-vs-name classification."""

    def test_product_name_not_classified_as_badge(self):
        """Short product names should NOT be peeled off as badges."""
        text = (
            "Galaxy S26 Ultra 5G\n\n$76.16/mth\n\n"
            "iPhone 17 Pro\n\n$42.12/mth\n\n"
            "Find X9 Pro 5G\n\n$46.29/mth"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26 Ultra 5G** — $76.16/mth" in result
        assert "- **iPhone 17 Pro** — $42.12/mth" in result
        assert "- **Find X9 Pro 5G** — $46.29/mth" in result

    def test_known_badge_still_peeled(self):
        """Known badge keywords before a product name should be classified as badges."""
        text = (
            "New\n\nGalaxy S26 Ultra 5G\n\n$76.16/mth\n\n"
            "Preorder\n\niPhone 17 Pro\n\n$42.12/mth\n\n"
            "LNY Offers\n\nFind X9 Pro 5G\n\n$46.29/mth"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26 Ultra 5G** — $76.16/mth" in result
        assert "  New" in result
        assert "- **iPhone 17 Pro** — $42.12/mth" in result
        assert "  Preorder" in result
        assert "- **Find X9 Pro 5G** — $46.29/mth" in result
        assert "  LNY Offers" in result

    def test_exclamation_mark_text_treated_as_badge(self):
        """Lines ending with ! are still treated as promotional badges."""
        text = (
            "Limited time only!\n\nGalaxy S26\n\n$76.16/mth\n\n"
            "Don't miss out!\n\niPhone 17\n\n$42.12/mth\n\n"
            "Best deal ever!\n\nFind X9\n\n$46.29/mth"
        )
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26** — $76.16/mth" in result
        assert "  Limited time only!" in result


class TestExtractTitle:
    """Tests for _extract_title — multi-source title extraction with fallbacks."""

    def test_specific_title_tag_preferred(self):
        html = '<html><head><title>Buy New Samsung Phones</title></head><body></body></html>'
        assert ContentExtractor._extract_title(html) == "Buy New Samsung Phones"

    def test_generic_title_falls_back_to_og(self):
        html = (
            "<html><head>"
            "<title>Product PLP/PDP</title>"
            '<meta property="og:title" content="Galaxy S26 Ultra 5G">'
            "</head><body></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "Galaxy S26 Ultra 5G"

    def test_generic_title_falls_back_to_h1(self):
        html = (
            "<html><head><title>Product PLP/PDP</title></head>"
            "<body><h1>Galaxy S26 Ultra 5G</h1></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "Galaxy S26 Ultra 5G"

    def test_og_title_not_used_when_title_is_specific(self):
        html = (
            "<html><head>"
            "<title>StarHub 5G Unlimited+ SIM Only Mobile Plans</title>"
            '<meta property="og:title" content="StarHub Plans">'
            "</head><body></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "StarHub 5G Unlimited+ SIM Only Mobile Plans"

    def test_h1_with_inner_html_stripped(self):
        html = (
            "<html><head><title>Home</title></head>"
            "<body><h1><span>Welcome</span> to <b>StarHub</b></h1></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "Welcome to StarHub"

    def test_no_title_returns_empty(self):
        html = "<html><body><p>No title here.</p></body></html>"
        assert ContentExtractor._extract_title(html) == ""

    def test_empty_og_title_falls_through(self):
        html = (
            '<html><head><title>Home</title>'
            '<meta property="og:title" content="">'
            "</head><body><h1>Real Title Here</h1></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "Real Title Here"

    def test_existing_good_titles_preserved(self):
        """Regression: known good titles from our crawl must not change."""
        cases = [
            ("Buy New Mobile Phones and Pay later with 0% instalments",
             "Buy New Mobile Phones and Pay later with 0% instalments"),
            ("Buy Latest Apple Phones and Pay later with 0% instalments",
             "Buy Latest Apple Phones and Pay later with 0% instalments"),
            ("StarHub 5G Unlimited+ SIM Only Mobile Plans",
             "StarHub 5G Unlimited+ SIM Only Mobile Plans"),
            ("Activating Your StarHub Welcome Plan | StarHub Support",
             "Activating Your StarHub Welcome Plan | StarHub Support"),
        ]
        for title_text, expected in cases:
            html = f"<html><head><title>{title_text}</title></head><body></body></html>"
            assert ContentExtractor._extract_title(html) == expected

    def test_og_meta_with_reversed_attributes(self):
        """og:title with content before property attribute."""
        html = (
            "<html><head>"
            "<title>Product PLP/PDP</title>"
            '<meta content="Galaxy S26 Ultra" property="og:title">'
            "</head></html>"
        )
        assert ContentExtractor._extract_title(html) == "Galaxy S26 Ultra"


class TestProductHeaderRecovery:
    """Tests for _extract_product_header — JSON-LD and OG meta product detection."""

    def test_jsonld_product_extracted(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Galaxy S26 Ultra 5G",
         "brand": {"@type": "Brand", "name": "Samsung"},
         "offers": {"@type": "AggregateOffer", "lowPrice": "1828", "highPrice": "2128"}}
        </script>
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is not None
        assert result["name"] == "Galaxy S26 Ultra 5G"
        assert result["brand"] == "Samsung"
        assert result["price"] == "1828"
        assert result["high_price"] == "2128"

    def test_jsonld_graph_product_extracted(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@graph": [
          {"@type": "WebPage", "name": "Store"},
          {"@type": "Product", "name": "iPhone 17 Pro",
           "brand": {"@type": "Brand", "name": "Apple"},
           "offers": {"price": "1749"}}
        ]}
        </script>
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is not None
        assert result["name"] == "iPhone 17 Pro"
        assert result["brand"] == "Apple"
        assert result["price"] == "1749"

    def test_og_product_extracted(self):
        html = """
        <html><head>
        <meta property="og:title" content="Galaxy S26 Ultra 5G">
        <meta property="product:price:amount" content="1828.00">
        <meta property="product:brand" content="Samsung">
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is not None
        assert result["name"] == "Galaxy S26 Ultra 5G"
        assert result["brand"] == "Samsung"
        assert result["price"] == "1828.00"

    def test_no_product_on_listing_page(self):
        """PLP/listing pages must NOT return a product header."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "ItemList", "name": "Mobile Phones",
         "itemListElement": [{"@type": "ListItem", "name": "Galaxy S26"}]}
        </script>
        <meta property="og:title" content="Buy New Mobile Phones">
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is None

    def test_no_product_on_faq_page(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "FAQPage", "mainEntity": []}
        </script>
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is None

    def test_no_structured_data_returns_none(self):
        html = "<html><head><title>Just a page</title></head><body></body></html>"
        result = ContentExtractor._extract_product_header(html)
        assert result is None

    def test_invalid_jsonld_skipped(self):
        html = """
        <html><head>
        <script type="application/ld+json">NOT VALID JSON</script>
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is None

    def test_format_product_price_with_discount(self):
        product = {"price": "1828", "high_price": "2128"}
        assert ContentExtractor._format_product_price(product) == "~~$2128~~ $1828"

    def test_format_product_price_single(self):
        product = {"price": "1499", "high_price": ""}
        assert ContentExtractor._format_product_price(product) == "$1499"

    def test_format_product_price_empty(self):
        product = {"price": "", "high_price": ""}
        assert ContentExtractor._format_product_price(product) == ""

    def test_jsonld_product_list_offers(self):
        """Product with offers as a list instead of a single object."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Test Phone",
         "brand": "TestBrand",
         "offers": [{"price": "999"}]}
        </script>
        </head><body></body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is not None
        assert result["price"] == "999"
        assert result["brand"] == "TestBrand"

    def test_integration_product_header_prepended(self):
        """Full pipeline: product header from JSON-LD is prepended to markdown."""
        html = """
        <html><head>
        <title>Product PLP/PDP</title>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Galaxy S26 Ultra 5G",
         "brand": {"@type": "Brand", "name": "Samsung"},
         "offers": {"lowPrice": "1828", "highPrice": "2128"}}
        </script>
        </head>
        <body>
        <main>
        <p>Preorder now for exclusive offers on the latest Samsung flagship phone
           with amazing features and specifications.</p>
        </main>
        </body></html>
        """
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/product", html=html, success=True)
        page = extractor._extract_page(result)
        assert page.title == "Galaxy S26 Ultra 5G"
        assert "**Samsung**" in page.markdown
        assert "## Galaxy S26 Ultra 5G" in page.markdown
        assert "~~$2128~~ $1828" in page.markdown

    def test_integration_no_product_header_on_plp(self):
        """Regression: PLP pages must NOT get a product header prepended."""
        html = """
        <html><head>
        <title>Buy New Mobile Phones</title>
        <script type="application/ld+json">
        {"@type": "ItemList", "name": "Mobile Phones"}
        </script>
        </head>
        <body>
        <main>
        <p>Browse our selection of the latest mobile phones from top brands with
           amazing deals and 0% instalment plans available.</p>
        </main>
        </body></html>
        """
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/phones", html=html, success=True)
        page = extractor._extract_page(result)
        assert page.title == "Buy New Mobile Phones"
        assert "**Samsung**" not in page.markdown
        assert "Retail price" not in page.markdown


class TestPromoteSectionLabels:
    """Tests for _promote_section_labels — promoting standalone labels to headings."""

    def test_label_before_bullets_promoted(self):
        text = "Front camera\n\n- 12.0 MP\n- 50.0 MP"
        result = ContentExtractor._promote_section_labels(text)
        assert "### Front camera" in result
        assert "- 12.0 MP" in result

    def test_label_before_long_block_promoted(self):
        text = (
            "Display\n\n"
            "6.9-inch, 3120 x 1440 (Quad HD+), Dynamic AMOLED 2X, 120 Hz — "
            "the latest display technology with incredible color accuracy"
        )
        result = ContentExtractor._promote_section_labels(text)
        assert "### Display" in result

    def test_multiple_labels_promoted(self):
        text = (
            "Front camera\n\n- 12.0 MP\n\n"
            "Battery Life\n\n- 5000 mAh\n\n"
            "CPU\n\n- Snapdragon 8 Elite Gen5 (3nm)"
        )
        result = ContentExtractor._promote_section_labels(text)
        assert "### Front camera" in result
        assert "### Battery Life" in result
        assert "### CPU" in result

    def test_heading_not_double_promoted(self):
        text = "## Already a heading\n\n- Some content"
        result = ContentExtractor._promote_section_labels(text)
        assert "### ## Already" not in result
        assert "## Already a heading" in result

    def test_price_not_promoted(self):
        text = "from $76.16/mth\n\n- Some content here\n- More content"
        result = ContentExtractor._promote_section_labels(text)
        assert "### from" not in result

    def test_badge_keyword_not_promoted(self):
        text = "Preorder\n\n- Some content here\n- More content"
        result = ContentExtractor._promote_section_labels(text)
        assert "### Preorder" not in result

    def test_offers_line_not_promoted(self):
        text = "15 offers available\n\n- Some content here\n- More content"
        result = ContentExtractor._promote_section_labels(text)
        assert "### 15 offers" not in result

    def test_bold_text_not_promoted(self):
        text = "**Galaxy S26 Ultra 5G**\n\n- from $76.16/mth"
        result = ContentExtractor._promote_section_labels(text)
        assert "### **Galaxy" not in result

    def test_label_at_end_not_promoted(self):
        """Label with nothing following should NOT be promoted."""
        text = "Some content\n\nTrending Brands"
        result = ContentExtractor._promote_section_labels(text)
        assert "### Trending" not in result

    def test_label_before_short_text_not_promoted(self):
        """Label before a very short non-bullet paragraph should NOT be promoted."""
        text = "Colour\n\nCobalt Violet"
        result = ContentExtractor._promote_section_labels(text)
        assert "### Colour" not in result

    def test_existing_list_item_not_promoted(self):
        text = "- Already a list\n\n- More items"
        result = ContentExtractor._promote_section_labels(text)
        assert "### - Already" not in result

    def test_long_label_not_promoted(self):
        """Labels over 60 chars (like promotional text) should NOT be promoted."""
        text = (
            "We got you covered with the new 5G Unlimited+ Discover our plans now for great deals\n\n"
            "- Some content"
        )
        result = ContentExtractor._promote_section_labels(text)
        assert "###" not in result

    def test_hr_separator_not_promoted(self):
        text = "---\n\n- Some content"
        result = ContentExtractor._promote_section_labels(text)
        assert "### ---" not in result

    def test_plp_footer_not_promoted(self):
        """Regression: PLP footer text like 'Trending Brands' followed by short
        metadata should NOT be promoted."""
        text = (
            "- **Galaxy S26** — from $76.16/mth\n\n"
            "Trending Brands\n\n"
            "Mobile Devices35 products"
        )
        result = ContentExtractor._promote_section_labels(text)
        assert "### Trending Brands" not in result
        assert "### Mobile Devices" not in result

    def test_integration_spec_labels_in_full_pipeline(self):
        """Full pipeline: spec labels in a PDP-like context get promoted."""
        text = (
            "Preorder\n\n"
            "Free storage upgrade to 512GB\n\n"
            "Colour: Cobalt Violet\n\n"
            "Front camera\n\n"
            "- 12.0 MP\n\n"
            "Battery Life\n\n"
            "- 5000 mAh\n\n"
            "CPU\n\n"
            "- Snapdragon 8 Elite Gen5 (3nm)\n\n"
            "Display\n\n"
            "- 6.9-inch, 3120 x 1440 (Quad HD+), Dynamic AMOLED 2X, 120 Hz"
        )
        result = ContentExtractor._clean_markdown(text)
        assert "### Front camera" in result
        assert "### Battery Life" in result
        assert "### CPU" in result
        assert "### Display" in result
        # Non-spec labels should NOT be promoted
        assert "### Preorder" not in result

    def test_support_article_headings_untouched(self):
        """Regression: existing ## headings in support articles must survive pipeline."""
        text = (
            "## What is the Welcome Plan offer all about?\n\n"
            "The Welcome Plan is a free mobile line that you can enjoy.\n\n"
            "## How can I get a Welcome Plan?\n\n"
            "Sign up or recontract to any of the following services."
        )
        result = ContentExtractor._clean_markdown(text)
        assert "## What is the Welcome Plan offer all about?" in result
        assert "## How can I get a Welcome Plan?" in result
        assert "### ##" not in result


class TestStripTemplateVariables:
    """Tests for _strip_template_variables — removing leaked SPA variables."""

    def test_var_prefix_stripped(self):
        text = "Some content\n\nVar_IsEligible: True\nVar_PayLaterStatus: normal\n\nMore content"
        result = ContentExtractor._strip_template_variables(text)
        assert "Var_IsEligible" not in result
        assert "Var_PayLaterStatus" not in result
        assert "Some content" in result
        assert "More content" in result

    def test_in_prefix_stripped(self):
        text = "In_PayLaterErrorCode: 0\nIn_BNPLErrorCode: 0"
        result = ContentExtractor._strip_template_variables(text)
        assert "In_PayLaterErrorCode" not in result
        assert "In_BNPLErrorCode" not in result

    def test_isoutofstock_stripped(self):
        text = "isOutOfStock: False\nPrice: $1,828"
        result = ContentExtractor._strip_template_variables(text)
        assert "isOutOfStock" not in result
        assert "Price: $1,828" in result

    def test_paylater_option_list_stripped(self):
        text = "PayLaterOptionList.Current.NumberOfMonths: 24\nVar_MaxMonthOfInstallment: 36"
        result = ContentExtractor._strip_template_variables(text)
        assert "PayLaterOptionList" not in result
        assert "Var_MaxMonthOfInstallment" not in result

    def test_numberofmonths_stripped(self):
        text = "NumberOfMonths: 24\nSome real content here."
        result = ContentExtractor._strip_template_variables(text)
        assert "NumberOfMonths" not in result
        assert "Some real content here." in result

    def test_concatenated_var_dump_stripped(self):
        text = "TrueVar_IsProcessing: FalseVar_PayLaterStatus: normalVar_PayLaterError:"
        result = ContentExtractor._strip_template_variables(text)
        assert "TrueVar_IsProcessing" not in result

    def test_normal_content_preserved(self):
        text = (
            "### Dimension\n\n"
            "- Size (mm): 163.6 x 78.1 x 7.9 mm\n"
            "- Weight: 214g\n\n"
            "### Battery Life\n\n"
            "- 5000 mAh"
        )
        result = ContentExtractor._strip_template_variables(text)
        assert result == text

    def test_bullet_with_var_stripped(self):
        text = "- In_IsAddOnAccessory: False, In_IsAddOnDevice: False, IsResetData: False"
        result = ContentExtractor._strip_template_variables(text)
        assert "In_IsAddOnAccessory" not in result

    def test_var_error_suffix_stripped(self):
        text = "Var_PayLaterError:\nSome content"
        result = ContentExtractor._strip_template_variables(text)
        assert "Var_PayLaterError" not in result
        assert "Some content" in result

    def test_integration_in_clean_markdown(self):
        """Template variables are stripped as part of the full _clean_markdown pipeline."""
        text = (
            "Preorder\n\n"
            "isOutOfStock: False\n"
            "Var_IsEligible: True\n"
            "Var_PayLaterStatus: normal\n\n"
            "### Battery Life\n\n"
            "- 5000 mAh"
        )
        result = ContentExtractor._clean_markdown(text)
        assert "Var_IsEligible" not in result
        assert "isOutOfStock" not in result
        assert "### Battery Life" in result
        assert "5000 mAh" in result


class TestTitleFromUrl:
    """Tests for _title_from_url — deriving titles from URL slugs."""

    def test_product_slug(self):
        url = "https://consumer.starhub.com/personal/store/mobile/devices/samsung/galaxy-s26-ultra-5g"
        result = ContentExtractor._title_from_url(url)
        assert result == "Galaxy S26 Ultra 5G"

    def test_simple_slug(self):
        url = "https://example.com/products/iphone-17-pro"
        result = ContentExtractor._title_from_url(url)
        assert result == "Iphone 17 PRO"

    def test_trailing_slash_ignored(self):
        url = "https://example.com/devices/samsung/galaxy-s26-ultra-5g/"
        result = ContentExtractor._title_from_url(url)
        assert result == "Galaxy S26 Ultra 5G"

    def test_root_url_returns_empty(self):
        assert ContentExtractor._title_from_url("https://example.com/") == ""
        assert ContentExtractor._title_from_url("https://example.com") == ""

    def test_short_slug_ignored(self):
        assert ContentExtractor._title_from_url("https://example.com/ab") == ""

    def test_numeric_slug_ignored(self):
        assert ContentExtractor._title_from_url("https://example.com/12345") == ""

    def test_tech_abbreviations_uppercased(self):
        url = "https://example.com/devices/galaxy-tab-s11-5g-wifi-lte"
        result = ContentExtractor._title_from_url(url)
        assert "5G" in result
        assert "WIFI" in result
        assert "LTE" in result

    def test_underscore_slug(self):
        url = "https://example.com/products/smart_watch_pro"
        result = ContentExtractor._title_from_url(url)
        assert result == "Smart Watch PRO"

    def test_url_slug_fallback_in_extract_title(self):
        """When title is generic and no OG/h1, URL slug is used."""
        html = "<html><head><title>Product PLP/PDP</title></head><body></body></html>"
        url = "https://consumer.starhub.com/personal/store/mobile/devices/samsung/galaxy-s26-ultra-5g"
        result = ContentExtractor._extract_title(html, url=url)
        assert result == "Galaxy S26 Ultra 5G"

    def test_url_slug_not_used_when_title_is_good(self):
        """Specific title trumps URL slug."""
        html = "<html><head><title>Buy Samsung Phones</title></head><body></body></html>"
        url = "https://example.com/some-page-slug"
        result = ContentExtractor._extract_title(html, url=url)
        assert result == "Buy Samsung Phones"

    def test_url_slug_not_used_when_h1_available(self):
        """h1 trumps URL slug."""
        html = (
            "<html><head><title>Product PLP/PDP</title></head>"
            "<body><h1>Galaxy S26 Ultra 5G</h1></body></html>"
        )
        result = ContentExtractor._extract_title(html, url="https://example.com/foo")
        assert result == "Galaxy S26 Ultra 5G"


class TestProductFromDom:
    """Tests for _product_from_dom — DOM fallback product detection."""

    def test_strikethrough_del_tag_detected(self):
        html = """
        <html><head>
        <link rel="canonical" href="https://store.com/devices/samsung/galaxy-s26-ultra-5g">
        </head><body>
        <h2>Galaxy S26 Ultra 5G</h2>
        <div class="price">
            <del>$2,128.00</del> <span>$1,828.00</span>
        </div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is not None
        assert result["high_price"] == "2,128.00"
        assert result["price"] == "1,828.00"
        assert result["name"] == "Galaxy S26 Ultra 5G"
        assert result["brand"] == "Samsung"

    def test_strikethrough_s_tag_detected(self):
        html = """
        <html><body>
        <h1>Test Product</h1>
        <div><s>$999.00</s> <span>$799.00</span></div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is not None
        assert result["high_price"] == "999.00"
        assert result["price"] == "799.00"
        assert result["name"] == "Test Product"

    def test_no_strikethrough_returns_none(self):
        html = """
        <html><body>
        <h1>Some Product</h1>
        <div>$1,499.00</div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is None

    def test_listing_page_no_false_positive(self):
        """PLP with no strikethrough prices should not trigger DOM fallback."""
        html = """
        <html><body>
        <h1>Buy Mobile Phones</h1>
        <div class="product"><span>Galaxy S26</span> $1,828.00</div>
        <div class="product"><span>iPhone 17</span> $1,299.00</div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is None

    def test_brand_from_canonical_url(self):
        html = """
        <html><head>
        <link rel="canonical" href="https://store.com/mobile/devices/apple/iphone-17-pro">
        </head><body>
        <h2>iPhone 17 Pro</h2>
        <div><del>$1,999.00</del> $1,749.00</div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is not None
        assert result["brand"] == "Apple"

    def test_brand_from_og_url(self):
        html = """
        <html><head>
        <meta property="og:url" content="https://store.com/devices/oppo/find-x9-pro">
        </head><body>
        <h3>Find X9 Pro</h3>
        <div><del>$1,800.00</del> $1,599.00</div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is not None
        assert result["brand"] == "Oppo"

    def test_generic_brand_segment_skipped(self):
        """URL segments like 'devices' or 'store' should not become brand."""
        html = """
        <html><head>
        <link rel="canonical" href="https://store.com/devices/galaxy-s26">
        </head><body>
        <h1>Galaxy S26</h1>
        <div><del>$999.00</del> $799.00</div>
        </body></html>
        """
        result = ContentExtractor._product_from_dom(html)
        assert result is not None
        assert result["brand"] == ""

    def test_dom_fallback_in_extract_product_header(self):
        """DOM fallback is called when JSON-LD and OG are absent."""
        html = """
        <html><head><title>Product PLP/PDP</title></head>
        <body>
        <h2>Galaxy S26 Ultra 5G</h2>
        <div><del>$2,128.00</del> $1,828.00</div>
        </body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result is not None
        assert result["name"] == "Galaxy S26 Ultra 5G"
        assert result["high_price"] == "2,128.00"
        assert result["price"] == "1,828.00"

    def test_jsonld_still_preferred_over_dom(self):
        """JSON-LD takes priority even when DOM has strikethrough prices."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "From JSON-LD",
         "brand": {"@type": "Brand", "name": "TestBrand"},
         "offers": {"price": "999"}}
        </script>
        </head><body>
        <h2>From DOM</h2>
        <div><del>$1,200.00</del> $999.00</div>
        </body></html>
        """
        result = ContentExtractor._extract_product_header(html)
        assert result["name"] == "From JSON-LD"
        assert result["brand"] == "TestBrand"

    def test_integration_dom_header_prepended(self):
        """Full pipeline: DOM-detected product header prepended to markdown."""
        html = """
        <html><head><title>Product PLP/PDP</title>
        <link rel="canonical"
              href="https://store.com/devices/samsung/galaxy-s26-ultra-5g">
        </head>
        <body>
        <main>
        <h2>Galaxy S26 Ultra 5G</h2>
        <div class="price"><del>$2,128.00</del> <span>$1,828.00</span></div>
        <p>Preorder now for exclusive offers on the latest Samsung flagship phone
           with amazing camera and battery life improvements.</p>
        </main>
        </body></html>
        """
        config = PageConfig(extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        cr = CrawlResult(
            url="https://store.com/devices/samsung/galaxy-s26-ultra-5g",
            html=html, success=True,
        )
        page = extractor._extract_page(cr)
        assert page.title == "Galaxy S26 Ultra 5G"
        assert "**Samsung**" in page.markdown
        assert "## Galaxy S26 Ultra 5G" in page.markdown
        assert "~~$2,128.00~~ $1,828.00" in page.markdown

    def test_integration_full_html_path_also_recovers(self):
        """Product header recovery also works in the markdownify path."""
        html = """
        <html><head><title>Product PLP/PDP</title>
        <link rel="canonical"
              href="https://store.com/devices/samsung/galaxy-s26-ultra-5g">
        </head>
        <body>
        <h2>Galaxy S26 Ultra 5G</h2>
        <div><del>$2,128.00</del> $1,828.00</div>
        <p>Some content here about the product.</p>
        </body></html>
        """
        config = PageConfig(extract_main_content=False, exclude_tags=[])
        extractor = ContentExtractor(config)
        cr = CrawlResult(
            url="https://store.com/devices/samsung/galaxy-s26-ultra-5g",
            html=html, success=True,
        )
        page = extractor._extract_page(cr)
        assert "**Samsung**" in page.markdown
        assert "## Galaxy S26 Ultra 5G" in page.markdown
        assert "~~$2,128.00~~ $1,828.00" in page.markdown
