"""Tests for crawl4md.extractor — product and price extraction."""

from __future__ import annotations

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor


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
        text = "Galaxy S26\n\n$76.16/mth\n\niPhone 17\n\n$42.12/mth\n\nFind X9\n\n$46.29/mth"
        result = ContentExtractor._compact_product_listings(text)
        assert "- **Galaxy S26** — $76.16/mth" in result
        assert "- **iPhone 17** — $42.12/mth" in result

    def test_price_with_or_prefix(self):
        text = "Product A\n\nor$1,499.00\n\nProduct B\n\nor$1,299.00\n\nProduct C\n\nor$999.00"
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
        text = "Product A\n\nor$$1,499.00\n\nProduct B\n\nor$$1,299.00\n\nProduct C\n\nor$$999.00"
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
            html=html,
            success=True,
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
            html=html,
            success=True,
        )
        page = extractor._extract_page(cr)
        assert "**Samsung**" in page.markdown
        assert "## Galaxy S26 Ultra 5G" in page.markdown
        assert "~~$2,128.00~~ $1,828.00" in page.markdown
