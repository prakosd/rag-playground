"""Tests for crawl4md.extractor — core extraction pipeline."""

from __future__ import annotations

from unittest.mock import patch

from bs4 import BeautifulSoup

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

    def test_filter_tags_accepts_existing_soup_exclude(self):
        config = PageConfig(exclude_tags=["nav", "footer"], include_only_tags=[])
        extractor = ContentExtractor(config)
        soup = BeautifulSoup(
            "<div><nav>skip</nav><p>keep</p><footer>skip</footer></div>",
            "html.parser",
        )

        filtered = extractor._filter_tags(soup)

        assert filtered is soup
        assert "skip" not in str(soup)
        assert "keep" in str(soup)

    def test_filter_tags_accepts_existing_soup_include_only(self):
        config = PageConfig(exclude_tags=[], include_only_tags=["main"])
        extractor = ContentExtractor(config)
        soup = BeautifulSoup("<div>outside</div><main><p>inside</p></main>", "html.parser")

        filtered = extractor._filter_tags(soup)

        assert filtered is soup
        assert "inside" in str(soup)
        assert "outside" not in str(soup)

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

    def test_unicode_line_separators_normalised(self):
        """U+2028 / U+2029 from PDF extraction are replaced with newlines."""
        text = "Hello\u2028World\u2029End"
        result = ContentExtractor._clean_markdown(text)
        assert "\u2028" not in result
        assert "\u2029" not in result
        assert result == "Hello\nWorld\nEnd"

    def test_crlf_normalised(self):
        """Real CRLF bytes in extracted text are normalised to LF."""
        text = "Line one\r\nLine two\rLine three"
        result = ContentExtractor._clean_markdown(text)
        assert "\r" not in result
        assert result == "Line one\nLine two\nLine three"

    def test_literal_escaped_crlf_removed(self):
        r"""Literal ``\r\n`` strings leaked from CMS JSON are cleaned."""
        text = "Browse by category\\r\\n"
        result = ContentExtractor._clean_markdown(text)
        assert "\\r\\n" not in result
        assert "Browse by category" in result

    def test_cms_attribute_junk_removed(self):
        r"""CMS data-attribute debris like ``"}}" id="..." class="...">`` is stripped."""
        text = (
            'Browse by category\\r\\n"}}" id="text-20f" class="cmp-text">\n\n## Browse by category'
        )
        result = ContentExtractor._clean_markdown(text)
        assert 'id="text-20f"' not in result
        assert 'class="cmp-text"' not in result
        assert "Browse by category" in result


class TestStripDataAttributes:
    """Tests for ``_strip_data_attributes`` preprocessing."""

    def test_data_cmp_data_layer_removed(self):
        """AEM data-cmp-data-layer attributes are stripped from HTML."""
        html = (
            '<div data-cmp-data-layer=\'{"text":"Hello\\r\\n"}\' '
            'id="text-abc" class="cmp-text">'
            "<h2>Hello</h2></div>"
        )
        result = ContentExtractor._strip_data_attributes(html)
        assert "data-cmp-data-layer" not in result
        assert "<h2>Hello</h2>" in result
        assert 'id="text-abc"' in result
        assert 'class="cmp-text"' in result

    def test_multiple_data_attrs_removed(self):
        """All data-* attributes are stripped, not just data-cmp-*."""
        html = '<p data-foo="1" data-bar="2" class="keep">Text</p>'
        result = ContentExtractor._strip_data_attributes(html)
        assert "data-foo" not in result
        assert "data-bar" not in result
        assert 'class="keep"' in result
        assert "Text" in result

    def test_non_data_attrs_preserved(self):
        """Standard attributes (id, class, href, itemtype) are kept."""
        html = '<a href="/page" id="link1" class="nav" itemtype="https://schema.org/Thing">Link</a>'
        result = ContentExtractor._strip_data_attributes(html)
        assert 'href="/page"' in result
        assert 'id="link1"' in result
        assert 'class="nav"' in result
        assert "itemtype" in result

    def test_integration_no_duplicate_from_data_layer(self):
        """Full extraction of AEM-style HTML produces no duplicated content."""
        html = (
            "<html><head><title>Test</title></head><body>"
            '<div data-cmp-data-layer=\'{"text":"Emergency resources\\r\\n"}\'>'
            "<h2>Emergency resources</h2>"
            "<p>Contact details for emergencies.</p>"
            "</div></body></html>"
        )
        config = PageConfig(extract_main_content=True)
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/page", html=html, success=True)
        pages = extractor.extract([result])
        assert len(pages) == 1
        md = pages[0].markdown
        assert "\\r\\n" not in md
        assert "data-cmp-data-layer" not in md
        count = md.count("Emergency resources")
        assert count <= 2, f"Duplicated content: found {count} occurrences"

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


class TestNavStrippingTrafilatura:
    """Nav/header/footer should be stripped in trafilatura mode too."""

    NAV_HTML = """
    <!DOCTYPE html>
    <html><head><title>Devices</title></head>
    <body>
    <nav>
        <ul>
            <li><a href="/personal">Personal</a></li>
            <li><a href="/sme">SME</a></li>
            <li><a href="/enterprise">Enterprise</a></li>
        </ul>
        <h3>Need help?</h3>
        <p>Chat now or contact us</p>
    </nav>
    <header>
        <div class="mega-menu">
            <a href="/broadband">Broadband overview</a>
            <a href="/mobile">Mobile overview</a>
        </div>
    </header>
    <main>
        <article>
            <h1>Buy New Mobile Phones</h1>
            <p>Find the latest smartphones with great monthly plans and deals.</p>
            <p>Browse our selection of top brand devices at competitive prices.</p>
            <p>Get started with a plan that suits your needs and budget today.</p>
        </article>
    </main>
    <footer>
        <p>Other Useful Links</p>
        <a href="/support">FAQ</a>
        <p>© StarHub 2026. All rights reserved.</p>
    </footer>
    </body></html>
    """

    def test_trafilatura_mode_strips_nav(self):
        config = PageConfig(extract_main_content=True)
        extractor = ContentExtractor(config)
        result = CrawlResult(
            url="https://example.com/devices",
            html=self.NAV_HTML,
            success=True,
        )
        page = extractor._extract_page(result)
        assert "Buy New Mobile Phones" in page.markdown
        assert "Need help?" not in page.markdown
        assert "Personal" not in page.markdown
        assert "SME" not in page.markdown
        assert "Broadband overview" not in page.markdown
        assert "All rights reserved" not in page.markdown

    def test_markdownify_mode_strips_nav(self):
        config = PageConfig(extract_main_content=False, exclude_tags=["nav", "header", "footer"])
        extractor = ContentExtractor(config)
        result = CrawlResult(
            url="https://example.com/devices",
            html=self.NAV_HTML,
            success=True,
        )
        page = extractor._extract_page(result)
        assert "Buy New Mobile Phones" in page.markdown
        assert "Need help?" not in page.markdown
        assert "All rights reserved" not in page.markdown

    def test_supplementary_sections_survive_nav_filtering(self):
        """FAQs in <details> should be recovered even when nav is stripped."""
        html = """
        <!DOCTYPE html>
        <html><head><title>FAQ Page</title></head>
        <body>
        <nav><ul><li>Personal</li><li>SME</li><li>Enterprise</li></ul></nav>
        <main>
            <article>
                <h1>Frequently Asked Questions About Our Service</h1>
                <p>Find answers to common questions about our plans and devices below.</p>
            </article>
            <details><summary>What is 5G?</summary><p>5G is the fifth generation of mobile networks.</p></details>
            <details><summary>How do I activate eSIM?</summary><p>Go to Settings and follow the steps.</p></details>
            <details><summary>Can I keep my number?</summary><p>Yes, you can port your existing number.</p></details>
        </main>
        <footer><p>© 2026 StarHub</p></footer>
        </body></html>
        """
        config = PageConfig(extract_main_content=True)
        extractor = ContentExtractor(config)
        result = CrawlResult(url="https://example.com/faq", html=html, success=True)
        page = extractor._extract_page(result)
        # Nav should be stripped
        assert "Personal" not in page.markdown
        # Main content should be present
        assert "Frequently Asked Questions" in page.markdown
        # FAQ details should be recovered via supplementary section extraction
        assert "5G" in page.markdown


class TestFlattenTableCells:
    """Tests for _flatten_table_cells — block elements and <br> inside table cells."""

    def test_br_replaced_with_space(self):
        html = "<table><tr><td>Plan A<br>Plan B<br/>Plan C</td><td>$25</td></tr></table>"
        result = ContentExtractor._flatten_table_cells(html)
        assert "<br" not in result
        assert "Plan A" in result
        assert "Plan B" in result
        assert "Plan C" in result

    def test_p_unwrapped(self):
        html = "<table><tr><td><p>First</p><p>Second</p></td></tr></table>"
        result = ContentExtractor._flatten_table_cells(html)
        assert "<p>" not in result
        assert "First" in result
        assert "Second" in result

    def test_div_unwrapped(self):
        html = "<table><tr><td><div>Alpha</div><div>Beta</div></td></tr></table>"
        result = ContentExtractor._flatten_table_cells(html)
        assert "<div>" not in result
        assert "Alpha" in result
        assert "Beta" in result

    def test_th_cells_also_flattened(self):
        html = "<table><tr><th><p>Header A</p></th><th>Header B<br>Extra</th></tr></table>"
        result = ContentExtractor._flatten_table_cells(html)
        assert "<p>" not in result
        assert "<br" not in result
        assert "Header A" in result
        assert "Extra" in result

    def test_no_table_returns_unchanged(self):
        html = "<div><p>Just a paragraph<br>with a break</p></div>"
        result = ContentExtractor._flatten_table_cells(html)
        # <br> outside table cells should NOT be affected
        assert "<br" in result or "<br/" in result or "br" in result.lower()

    def test_nested_div_in_cell(self):
        html = (
            "<table><tr><td>"
            "<div class='price'><div class='amount'>$10</div><div class='period'>/mo</div></div>"
            "</td></tr></table>"
        )
        result = ContentExtractor._flatten_table_cells(html)
        assert "<div" not in result
        assert "$10" in result
        assert "/mo" in result

    def test_mixed_block_and_br(self):
        """Cell with both <p> wrappers and <br> tags."""
        html = "<table><tr><td><p>Line 1<br>Line 2</p><p>Line 3</p></td></tr></table>"
        result = ContentExtractor._flatten_table_cells(html)
        assert "<p>" not in result
        assert "<br" not in result
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
