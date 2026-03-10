"""Tests for crawl4md.extractor — item detection, separation, and sentinel handling."""

from __future__ import annotations

from unittest.mock import patch

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import _ITEM_SENTINEL, ContentExtractor


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
        # 1 leading sentinel + 3 between items = 4 total for 4 items
        assert result.count(_ITEM_SENTINEL) == 4

    def test_auto_detect_inserts_hr(self):
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=False)
        assert result.count("<hr") >= 3

    def test_explicit_selector(self):
        config = PageConfig(separate_items=True, item_selector="div.product-card", exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=True)
        # 1 leading + 3 between = 4
        assert result.count(_ITEM_SENTINEL) == 4

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
        config = PageConfig(separate_items=True, extract_main_content=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True
        )
        page = extractor._extract_page(result_obj)
        # The sentinel should have been replaced with ---
        assert _ITEM_SENTINEL not in page.markdown
        # Products should appear grouped (with --- separators or as structured output)
        assert "Galaxy S26" in page.markdown
        assert "iPhone 17" in page.markdown

    def test_integration_markdownify_with_separators(self):
        """Full pipeline: separate_items=True with markdownify mode."""
        config = PageConfig(
            separate_items=True, extract_main_content=False, exclude_tags=[], include_only_tags=[]
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True
        )
        page = extractor._extract_page(result_obj)
        # markdownify preserves <hr> as ---
        assert page.markdown.count("---") >= 3

    def test_separate_items_false_no_separators(self):
        """When separate_items=False, no separators are inserted."""
        config = PageConfig(separate_items=False, exclude_tags=[])
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com", html=self.PRODUCT_CARDS_HTML, success=True
        )
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
        # 4 bg-white + 1 interstitial = 5 items → 1 leading + 4 between = 5
        assert result.count(_ITEM_SENTINEL) == 5

    def test_interstitial_sibling_not_included_with_explicit_selector(self):
        """Explicit item_selector should NOT include interstitial siblings."""
        config = PageConfig(separate_items=True, item_selector="div.bg-white", exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.MIXED_CLASS_HTML, use_sentinel=True)
        # Only 4 bg-white items → 1 leading + 3 between = 4
        assert result.count(_ITEM_SENTINEL) == 4

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
        # 4 cards matched, spacer too short → 1 leading + 3 between = 4
        assert result.count(_ITEM_SENTINEL) == 4

    def test_integration_mixed_class_product_names(self):
        """Full pipeline (markdownify): banner div gets its own separator."""
        config = PageConfig(
            separate_items=True,
            extract_main_content=False,
            exclude_tags=[],
            include_only_tags=[],
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(
            url="https://example.com",
            html=self.MIXED_CLASS_HTML,
            success=True,
        )
        page = extractor._extract_page(result_obj)
        # With interstitial separator, the banner div is isolated:
        # at least 4 --- separators (5 items) should appear in the output
        assert page.markdown.count("---") >= 4
        # Product names should remain present and separate from banner
        assert "Galaxy S26 Ultra 5G" in page.markdown
        assert "Galaxy S26 5G" in page.markdown
        assert "Magic8 Pro" in page.markdown

    def test_trafilatura_banner_not_merged_with_product(self):
        """Full pipeline (trafilatura): banner text must not merge with next product name."""
        # Use richer HTML so trafilatura extracts product names reliably.
        html = """
        <html><head><title>Buy New Mobile Phones</title></head><body>
        <main>
        <h1>Buy New Mobile Phones</h1>
        <div class="product-list">
          <div class="product-card bg-white">
            <h3>Galaxy S26 Ultra 5G</h3>
            <p>The latest flagship from Samsung with advanced AI features and titanium build.</p>
            <p>from $76.16/mth</p><p>or $1,828.00</p><p>15 offers available</p>
          </div>
          <div class="product-card bg-white">
            <h3>Galaxy S26+ 5G</h3>
            <p>Premium performance with a large display and pro camera system.</p>
            <p>from $67.83/mth</p><p>or $1,628.00</p><p>13 offers available</p>
          </div>
          <div class="product-card bg-tint-blue">
            <p>We got you covered with the new 5G Unlimited+ Discover our new mobile plans with unlimited local and roaming features, all in!</p>
            <a href="#">Learn more</a>
          </div>
          <div class="product-card bg-white">
            <h3>Galaxy S26 5G</h3>
            <p>Flagship Galaxy experience with Snapdragon processor and vibrant display.</p>
            <p>from $59.91/mth</p><p>or $1,438.00</p><p>13 offers available</p>
          </div>
          <div class="product-card bg-white">
            <h3>Magic8 Pro</h3>
            <p>Powerful performance with cutting-edge camera technology and fast charging.</p>
            <p>from $44.62/mth</p><p>or $1,499.00</p><p>9 offers available</p>
          </div>
        </div>
        </main>
        </body></html>
        """
        config = PageConfig(
            separate_items=True,
            extract_main_content=True,
            exclude_tags=[],
        )
        extractor = ContentExtractor(config)
        result_obj = CrawlResult(url="https://example.com", html=html, success=True)
        page = extractor._extract_page(result_obj)
        # No line should contain both "Discover" (banner) and "Galaxy S26 5G" (product)
        for line in page.markdown.split("\n"):
            if "Galaxy S26 5G" in line:
                assert "Discover" not in line, f"Banner text merged with product name: {line!r}"

    def test_sentinel_placed_inside_items_not_as_sibling(self):
        """Between-item sentinels must be inside items; leading sentinel is a sibling."""
        from bs4 import BeautifulSoup

        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=True)
        soup = BeautifulSoup(result, "html.parser")
        sentinel_ps = soup.find_all("p", string=_ITEM_SENTINEL)
        # Leading sentinel is a sibling of product-card divs
        leading = sentinel_ps[0]
        assert leading.parent is not None
        assert "product-list" in " ".join(leading.parent.get("class", []))
        # Remaining sentinels should be inside product-card divs
        for sentinel_p in sentinel_ps[1:]:
            assert sentinel_p.parent is not None
            assert "product-card" in " ".join(sentinel_p.parent.get("class", []))

    MULTI_GROUP_HTML = """
    <html><body>
    <section class="offers">
      <div class="tile"><h3>Reno15 Pro Max 5G</h3><p>Get the all-new Reno 15 Pro Max at the price of Reno 15.</p></div>
      <div class="tile"><h3>400 Pro 5G</h3><p>Save $288 plus 1-year extended warranty included.</p></div>
      <div class="tile"><h3>Premier League</h3><p>Watch the Premier League in Dolby Atmos sound.</p></div>
      <div class="tile"><h3>Broadband</h3><p>All-inclusive plans from $39.91/mth for broadband peace of mind.</p></div>
    </section>
    <section class="gear">
      <div class="tile"><h3>Multi-line discount</h3><p>Enjoy greater discounts with multiple lines.</p></div>
      <div class="tile"><h3>DeviceDollars</h3><p>Learn how to redeem your DeviceDollars on purchase.</p></div>
      <div class="tile"><h3>ScamSafe</h3><p>Defend against scam calls and SMS fraud filtering.</p></div>
    </section>
    </body></html>
    """

    def test_multi_group_both_get_sentinels(self):
        """Two distinct tile groups should both receive sentinels."""
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.MULTI_GROUP_HTML, use_sentinel=True)
        # 4 offers: 1 leading + 3 between = 4; 3 gear: 1 leading + 2 between = 3; total = 7
        assert result.count(_ITEM_SENTINEL) == 7

    def test_multi_group_both_get_hr(self):
        """Two distinct tile groups should both receive <hr> separators."""
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.MULTI_GROUP_HTML, use_sentinel=False)
        assert result.count("<hr") >= 5

    def test_single_group_still_works(self):
        """Existing single-group behavior is preserved."""
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.PRODUCT_CARDS_HTML, use_sentinel=True)
        # 1 leading + 3 between = 4
        assert result.count(_ITEM_SENTINEL) == 4


class TestIncludeInterstitialSiblings:
    """Tests for _include_interstitial_siblings — expanding auto-detected groups."""

    def test_interstitial_included_between_matched(self):
        from bs4 import BeautifulSoup

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


class TestSentinelOrdering:
    """Tests that sentinel replacement happens before _clean_markdown."""

    def test_sentinels_replaced_before_product_compaction(self):
        """Products separated by sentinels should not bleed across boundaries."""
        config = PageConfig(
            separate_items=True,
            extract_main_content=True,
            exclude_tags=[],
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


class TestTableRowsNotSeparated:
    """Table rows must not be treated as repeated items."""

    TABLE_HTML = """
    <html><body>
    <table>
      <thead><tr><th>Service</th><th>Channel</th><th>Price</th></tr></thead>
      <tbody>
        <tr><td>4G SIM-only Plans with enough text for detection threshold</td><td>Shop</td><td>$25</td></tr>
        <tr><td>Mobile+ SIM-only Plans with enough text for detection threshold</td><td>Online</td><td>$38</td></tr>
        <tr><td>Mobile+ 2-year Plans with enough text for detection threshold</td><td>Shop</td><td>$69</td></tr>
        <tr><td>Broadband 2-year Plans with enough text for detection threshold</td><td>Telesales</td><td>$45</td></tr>
      </tbody>
    </table>
    </body></html>
    """

    def test_table_rows_no_sentinels(self):
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.TABLE_HTML, use_sentinel=True)
        assert _ITEM_SENTINEL not in result

    def test_table_rows_no_hr(self):
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(self.TABLE_HTML, use_sentinel=False)
        assert "<hr" not in result

    def test_items_outside_table_still_detected(self):
        """Items outside a table should still get separators even when a table is present."""
        html = """
        <html><body>
        <table><tr><td>Row A data</td></tr><tr><td>Row B data</td></tr></table>
        <div class="list">
          <div class="card"><p>Product Alpha with enough descriptive text for detection</p></div>
          <div class="card"><p>Product Bravo with enough descriptive text for detection</p></div>
          <div class="card"><p>Product Charlie with enough descriptive text for detection</p></div>
        </div>
        </body></html>
        """
        config = PageConfig(separate_items=True, exclude_tags=[])
        extractor = ContentExtractor(config)
        result = extractor._insert_item_separators(html, use_sentinel=True)
        # Cards outside the table should still be detected
        assert _ITEM_SENTINEL in result
