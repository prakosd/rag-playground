"""Tests for crawl4md.extractor — link population and heading children."""

from __future__ import annotations

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor


class TestPopulateEmptyLinks:
    """Tests for ContentExtractor._populate_empty_links."""

    def test_empty_anchor_gets_slug_text(self):
        html = '<a href="https://example.com/personal/broadband.html"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Broadband<" in result

    def test_hyphenated_slug(self):
        html = '<a href="/store/mobile-plans"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Mobile Plans<" in result

    def test_underscored_slug(self):
        html = '<a href="/store/my_account"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">My Account<" in result

    def test_fallback_to_link_for_root_path(self):
        html = '<a href="https://example.com/"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Link<" in result

    def test_fallback_to_link_for_empty_path(self):
        html = '<a href="https://example.com"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Link<" in result

    def test_title_attribute_preferred(self):
        html = '<a href="/page" title="My Title"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">My Title<" in result

    def test_aria_label_used_when_no_title(self):
        html = '<a href="/page" aria-label="Accessible Label"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Accessible Label<" in result

    def test_title_takes_precedence_over_aria_label(self):
        html = '<a href="/page" title="Title" aria-label="Aria"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Title<" in result

    def test_skip_hash_href(self):
        html = '<a href="#section"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert result == html

    def test_skip_javascript_href(self):
        html = '<a href="javascript:void(0)"></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert result == html

    def test_skip_empty_href(self):
        html = '<a href=""></a>'
        result = ContentExtractor._populate_empty_links(html)
        assert result == html

    def test_non_empty_link_unchanged(self):
        html = '<a href="/page">Click here</a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Click here<" in result

    def test_whitespace_only_treated_as_empty(self):
        html = '<a href="/personal/broadband.html">   </a>'
        result = ContentExtractor._populate_empty_links(html)
        assert ">Broadband<" in result

    def test_multiple_empty_links(self):
        html = """
        <div>
            <a href="/broadband.html"></a>
            <a href="/mobile-plans"></a>
            <a href="/entertainment.html"></a>
        </div>
        """
        result = ContentExtractor._populate_empty_links(html)
        assert ">Broadband<" in result
        assert ">Mobile Plans<" in result
        assert ">Entertainment<" in result

    def test_card_overlay_pattern(self):
        """Realistic card pattern: empty overlay <a> relocated after sibling content."""
        html = """
        <div class="card">
            <a class="card-link" href="https://www.example.com/personal/broadband.html"></a>
            <div class="card-body">
                <h6>Broadband plans</h6>
                <p>From $39.91/mth</p>
            </div>
        </div>
        """
        result = ContentExtractor._populate_empty_links(html)
        assert ">Broadband<" in result
        assert "Broadband plans" in result
        # Overlay link should be moved AFTER the card-body content
        body_pos = result.index("Broadband plans")
        link_pos = result.index(">Broadband<")
        assert link_pos > body_pos, "Overlay link should appear after card body content"

    def test_overlay_with_img_child_not_relocated(self):
        """An <a> containing an <img> has children — should be skipped entirely."""
        html = """
        <div class="card">
            <a href="/page"><img src="banner.jpg" alt="Banner"></a>
            <div class="card-body">
                <h6>Product title with enough text here</h6>
            </div>
        </div>
        """
        result = ContentExtractor._populate_empty_links(html)
        # The <a> has an <img> child so it's skipped entirely (no text added)
        assert ">Page<" not in result

    def test_overlay_in_low_content_parent_not_relocated(self):
        """An empty <a> whose parent has < 30 chars sibling text stays in place."""
        html = '<div><a href="/page"></a><span>Hi</span></div>'
        result = ContentExtractor._populate_empty_links(html)
        # Not relocated because sibling text "Hi" < 30 chars
        # Link text should still be populated
        assert ">Page<" in result
        # Order: link before "Hi" (not moved)
        assert result.index(">Page<") < result.index("Hi")

    def test_multiple_overlay_links_across_cards(self):
        """Each overlay link in its respective card is moved to end of its card."""
        html = """
        <div class="cards">
            <div class="card">
                <a href="/broadband.html"></a>
                <div class="body"><h6>Broadband plans with details</h6><p>From $39.91/mth for peace of mind</p></div>
            </div>
            <div class="card">
                <a href="/mobile-plans"></a>
                <div class="body"><h6>Mobile plans for everyone</h6><p>Stay connected from $28/mth always</p></div>
            </div>
        </div>
        """
        result = ContentExtractor._populate_empty_links(html)
        # Both overlay links relocated after their card bodies
        assert "Broadband plans" in result
        assert "Mobile plans" in result
        # Each link text appears after its card body
        broadband_body = result.index("Broadband plans")
        broadband_link = result.index(">Broadband<")
        assert broadband_link > broadband_body
        mobile_body = result.index("Mobile plans")
        mobile_link = result.index(">Mobile Plans<")
        assert mobile_link > mobile_body


class TestPopulateEmptyLinksIntegration:
    """Integration tests: empty links survive full extraction pipelines."""

    CARD_HTML = """
    <!DOCTYPE html>
    <html><head><title>Cards Page</title></head>
    <body>
    <main>
    <div class="card">
        <a class="card-link" href="https://www.example.com/personal/broadband.html"></a>
        <div class="card-body">
            <h6>Broadband For seamless connection</h6>
            <p>All-inclusive plans from $39.91/mth for broadband peace of mind.</p>
        </div>
    </div>
    <div class="card">
        <a class="card-link" href="https://www.example.com/personal/mobile-plans"></a>
        <div class="card-body">
            <h6>Mobile plans for everyone</h6>
            <p>Stay connected with unlimited data from $28/mth.</p>
        </div>
    </div>
    </main>
    </body></html>
    """

    def test_trafilatura_path_contains_link(self):
        config = PageConfig(extract_main_content=True)
        extractor = ContentExtractor(config)
        result = CrawlResult(
            url="https://www.example.com/cards",
            html=self.CARD_HTML,
            success=True,
        )
        page = extractor._extract_page(result)
        assert "broadband.html" in page.markdown

    def test_markdownify_path_contains_link(self):
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        result = CrawlResult(
            url="https://www.example.com/cards",
            html=self.CARD_HTML,
            success=True,
        )
        page = extractor._extract_page(result)
        assert "broadband.html" in page.markdown
        assert "mobile-plans" in page.markdown


class TestLinkTextFromHref:
    """Tests for ContentExtractor._link_text_from_href."""

    def test_simple_path(self):
        assert ContentExtractor._link_text_from_href("/broadband.html") == "Broadband"

    def test_nested_path(self):
        assert (
            ContentExtractor._link_text_from_href(
                "https://example.com/personal/bundles/premier-league.html"
            )
            == "Premier League"
        )

    def test_no_extension(self):
        assert ContentExtractor._link_text_from_href("/store/mobile-plans") == "Mobile Plans"

    def test_root_path(self):
        assert ContentExtractor._link_text_from_href("https://example.com/") == "Link"

    def test_empty_string(self):
        assert ContentExtractor._link_text_from_href("") == "Link"

    def test_trailing_slash_stripped(self):
        assert ContentExtractor._link_text_from_href("/personal/broadband/") == "Broadband"


class TestSpaceHeadingChildren:
    """Tests for ContentExtractor._space_heading_children."""

    def test_adjacent_spans_get_space(self):
        html = "<h6><span>Broadband</span><span>For seamless connection</span></h6>"
        result = ContentExtractor._space_heading_children(html)
        # The space is inserted between the span elements
        assert "BroadbandFor" not in result
        # After extraction, get_text should have a space between them
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(result, "html.parser")
        assert "Broadband For" in soup.get_text()

    def test_single_child_unchanged(self):
        html = "<h6><span>Single</span></h6>"
        result = ContentExtractor._space_heading_children(html)
        assert "Single" in result

    def test_plain_text_heading_unchanged(self):
        html = "<h6>Normal heading text</h6>"
        result = ContentExtractor._space_heading_children(html)
        assert "Normal heading text" in result

    def test_text_between_tags_not_doubled(self):
        """When there's already a text node between tags, no extra space is added."""
        html = "<h3><span>A</span> <span>B</span></h3>"
        result = ContentExtractor._space_heading_children(html)
        # Should not produce double spaces
        assert "A  B" not in result or "A B" in result

    def test_multiple_headings(self):
        html = """
        <h6><span>Mobile</span><span>Save $288</span></h6>
        <h6><span>Entertainment</span><span>Divided by rivalry</span></h6>
        """
        result = ContentExtractor._space_heading_children(html)
        assert "MobileSave" not in result
        assert "EntertainmentDivided" not in result

    def test_h1_through_h6_all_handled(self):
        for level in range(1, 7):
            html = f"<h{level}><span>A</span><span>B</span></h{level}>"
            result = ContentExtractor._space_heading_children(html)
            assert "AB" not in result or "A B" in result


class TestOverlayLinkIntegration:
    """Integration test: overlay links appear after card body in full pipeline."""

    CARDS_HTML = """
    <!DOCTYPE html>
    <html><head><title>Offers Page</title></head>
    <body>
    <main>
    <div class="tiles">
        <div class="tile">
            <a class="card-link" href="https://www.example.com/broadband.html"></a>
            <div class="body">
                <h6>Broadband For seamless connection we got you</h6>
                <p>All-inclusive plans from $39.91/mth for broadband peace of mind.</p>
                <a href="#">Sign up now</a>
            </div>
        </div>
        <div class="tile">
            <a class="card-link" href="https://www.example.com/mobile-plans"></a>
            <div class="body">
                <h6>Mobile plans for everyone to explore</h6>
                <p>Stay connected with unlimited data from $28/mth always on.</p>
                <a href="#">Sign up now</a>
            </div>
        </div>
        <div class="tile">
            <a class="card-link" href="https://www.example.com/entertainment.html"></a>
            <div class="body">
                <h6>Entertainment for the whole family to enjoy</h6>
                <p>Watch Premier League in Dolby Atmos multidimensional sound.</p>
                <a href="#">Find out more</a>
            </div>
        </div>
    </div>
    </main>
    </body></html>
    """

    def test_markdownify_link_after_body(self):
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com/offers",
            html=self.CARDS_HTML,
            success=True,
        )
        page = extractor._extract_page(result_obj)
        # "Broadband" card body should appear before [Broadband] link text
        assert "seamless connection" in page.markdown
        assert "broadband.html" in page.markdown
