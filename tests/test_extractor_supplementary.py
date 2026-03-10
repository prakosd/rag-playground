"""Tests for crawl4md.extractor — supplementary section recovery and FAQ formatting."""

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
