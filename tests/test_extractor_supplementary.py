"""Tests for crawl4md.extractor — supplementary sections, FAQ, titles, labels, template vars."""

from __future__ import annotations

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor


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


class TestExtractTitle:
    """Tests for _extract_title — multi-source title extraction with fallbacks."""

    def test_specific_title_tag_preferred(self):
        html = "<html><head><title>Buy New Samsung Phones</title></head><body></body></html>"
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
        assert (
            ContentExtractor._extract_title(html) == "StarHub 5G Unlimited+ SIM Only Mobile Plans"
        )

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
            "<html><head><title>Home</title>"
            '<meta property="og:title" content="">'
            "</head><body><h1>Real Title Here</h1></body></html>"
        )
        assert ContentExtractor._extract_title(html) == "Real Title Here"

    def test_existing_good_titles_preserved(self):
        """Regression: known good titles from our crawl must not change."""
        cases = [
            (
                "Buy New Mobile Phones and Pay later with 0% instalments",
                "Buy New Mobile Phones and Pay later with 0% instalments",
            ),
            (
                "Buy Latest Apple Phones and Pay later with 0% instalments",
                "Buy Latest Apple Phones and Pay later with 0% instalments",
            ),
            (
                "StarHub 5G Unlimited+ SIM Only Mobile Plans",
                "StarHub 5G Unlimited+ SIM Only Mobile Plans",
            ),
            (
                "Activating Your StarHub Welcome Plan | StarHub Support",
                "Activating Your StarHub Welcome Plan | StarHub Support",
            ),
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
        text = "- **Galaxy S26** — from $76.16/mth\n\nTrending Brands\n\nMobile Devices35 products"
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
        url = (
            "https://consumer.starhub.com/personal/store/mobile/devices/samsung/galaxy-s26-ultra-5g"
        )
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
        url = (
            "https://consumer.starhub.com/personal/store/mobile/devices/samsung/galaxy-s26-ultra-5g"
        )
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
