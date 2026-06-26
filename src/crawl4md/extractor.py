"""ContentExtractor — converts crawled HTML to clean Markdown text."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import unquote, urljoin, urlparse

import mdformat
import trafilatura
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from crawl4md._internal.html_preprocess import HTMLPreprocessor
from crawl4md._internal.markdown_pipeline import MarkdownPipeline
from crawl4md._internal.product_metadata import ProductMetadataExtractor
from crawl4md.config import CrawlResult, ExtractedPage, PageConfig
from crawl4md.progress import ProgressReporter

# Sentinel inserted between repeated items *before* trafilatura extraction.
# trafilatura strips <hr> but preserves plain text in <p> tags.
_ITEM_SENTINEL = "CRAWL4MD_ITEM_BREAK"
_ITEM_SENTINEL_MARKDOWN_RE = re.compile(r"(?m)^[ \t]*(?:[-*+]\s*)?CRAWL4MD\\?_ITEM\\?_BREAK[ \t]*$")

# Regex that strips Markdown syntax characters but keeps content tokens
# (words, numbers, currency signs, punctuation used in prose).
_MD_SYNTAX_RE = re.compile(r"[#*`>|~\[\]\\]")

# If trafilatura captures less than this fraction of the page's visible text,
# fall back to markdownify to avoid losing significant content.
_COVERAGE_THRESHOLD = 0.15

# ------------------------------------------------------------------
# Extraction parameters
# ------------------------------------------------------------------

# Tags stripped during markdownify conversion (images removed from output)
_MARKDOWNIFY_STRIP_TAGS = ["img"]
# Heading style for markdownify output
_MARKDOWNIFY_HEADING_STYLE = "ATX"
# BeautifulSoup parser used throughout the extractor
_HTML_PARSER = "html.parser"
# Tags excluded from visible-text coverage calculations
_NON_VISIBLE_TEXT_TAGS = frozenset({"script", "style", "noscript"})
# mdformat extension for GitHub Flavoured Markdown validation
_MDFORMAT_EXTENSIONS = ("gfm",)
# Markdown separator replacing item sentinels after extraction
_ITEM_SEPARATOR_MD = "\n\n---\n\n"

# ------------------------------------------------------------------
# Item detection thresholds
# ------------------------------------------------------------------

# Minimum text length (chars) for a child element to count as a repeated item
_MIN_ITEM_TEXT_LEN = 20
# Minimum number of same-signature children to qualify as a repeated group
_MIN_REPEATED_GROUP = 3
# Minimum text length for interstitial siblings between item groups
_MIN_INTERSTITIAL_LEN = 20
# Parent tags to skip when scanning for repeated items (navigation chrome, tables)
_ITEM_SKIP_TAGS = frozenset({"nav", "header", "footer", "table", "thead", "tbody", "tfoot"})

# ------------------------------------------------------------------
# Supplementary / FAQ detection thresholds
# ------------------------------------------------------------------

# Minimum text length for a supplementary section fragment to be included
_MIN_SUPPLEMENT_TEXT_LEN = 30
# Minimum <details> siblings to trigger FAQ/accordion grouping
_MIN_FAQ_DETAILS = 3
# Minimum URL slug length for title derivation
_MIN_SLUG_LEN = 3

# ------------------------------------------------------------------
# Fragment link resolution
# ------------------------------------------------------------------

# Matches Markdown fragment-only links like ](#section-name)
_FRAGMENT_LINK_RE = re.compile(r"\]\(#([^)]*)\)")

# Matches Markdown links with relative hrefs (not absolute, mailto, tel, or fragment-only)
_RELATIVE_LINK_RE = re.compile(r"\]\((?!https?://|mailto:|tel:|#)([^)]+)\)")

# ------------------------------------------------------------------
# HTML title / metadata extraction regexes
# ------------------------------------------------------------------

# Extracts content of <title> tag
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# Extracts og:title from <meta> tag (property-first attribute order)
_OG_TITLE_RE_1 = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# Extracts og:title from <meta> tag (content-first attribute order)
_OG_TITLE_RE_2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.IGNORECASE,
)
# Extracts content of first <h1> tag
_H1_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
# Strips all HTML tags (used for plain-text extraction from HTML fragments)
_HTML_TAG_STRIP_RE = re.compile(r"<[^>]+>")

# ------------------------------------------------------------------
# FAQ / supplementary section detection regexes
# ------------------------------------------------------------------

# Matches heading tag names h2 through h4 (used for FAQ heading search)
_FAQ_HEADING_RANGE_RE = re.compile(r"^h[2-4]$")
# Matches text containing "FAQ" or "Frequently Asked" keywords
_FAQ_KEYWORD_RE = re.compile(r"\bfaq\b|frequently\s+asked", re.IGNORECASE)
# Matches Schema.org FAQ itemtype values
_FAQ_SCHEMA_RE = re.compile(r"FAQPage", re.IGNORECASE)
# ------------------------------------------------------------------
# Product metadata string constants
# ------------------------------------------------------------------

# Prefix for retail price display in product headers
_RETAIL_PRICE_PREFIX = "Retail price: "

# ------------------------------------------------------------------
# DOM / content thresholds
# ------------------------------------------------------------------

_HtmlOrSoup = str | BeautifulSoup


class ContentExtractor:
    """Extracts readable Markdown content from crawled pages.

    Uses **trafilatura** when ``extract_main_content`` is enabled (strips
    navigation, headers, footers) and **markdownify** for full-HTML mode.
    """

    def __init__(self, page_config: PageConfig | None = None) -> None:
        self.page_config = page_config or PageConfig()

    def extract(self, results: list[CrawlResult]) -> list[ExtractedPage]:
        """Convert a list of crawl results into extracted Markdown pages."""
        successful = [r for r in results if r.success]
        progress = ProgressReporter(len(successful), action="Extracted")
        pages: list[ExtractedPage] = []
        for result in successful:
            page = self._extract_page(result)
            progress.update(result.url)
            if page.markdown.strip():
                pages.append(page)
        progress.finish()
        return pages

    def _extract_page(self, result: CrawlResult) -> ExtractedPage:
        """Extract content from a single crawl result."""
        if result.is_pdf:
            return self._extract_pdf_page(result)
        if result.is_docx:
            return self._extract_docx_page(result)
        if self.page_config.extract_main_content:
            return self._extract_main_content(result)
        return self._extract_full_html(result)

    def _prepare_soup(
        self,
        result: CrawlResult,
        *,
        use_sentinel: bool,
        recover_supplements: bool = False,
    ) -> tuple[BeautifulSoup, list[str], dict | None]:
        preprocessor = HTMLPreprocessor(self.page_config)
        soup = BeautifulSoup(result.html, _HTML_PARSER)
        preprocessor.strip_data_attributes(soup)
        product = self._extract_product_header(result.html, soup=soup)
        supplements = self._extract_supplementary_sections(soup) if recover_supplements else []
        preprocessor.preprocess_soup(soup)
        if self.page_config.separate_items:
            self._insert_item_separators(soup, use_sentinel=use_sentinel)
        return soup, supplements, product

    def _extract_pdf_page(self, result: CrawlResult) -> ExtractedPage:
        """Extract content from a PDF crawl result (Markdown already generated)."""
        return self._extract_document_page(result, extension=".pdf")

    def _extract_docx_page(self, result: CrawlResult) -> ExtractedPage:
        """Extract content from a DOCX crawl result (Markdown already generated)."""
        return self._extract_document_page(result, extension=".docx")

    def _extract_document_page(self, result: CrawlResult, *, extension: str) -> ExtractedPage:
        """Build an ExtractedPage from a binary document's pre-generated Markdown.

        Skips all HTML preprocessing (the Markdown was produced by the matching
        downloader, e.g. pymupdf4llm for PDF or mammoth for DOCX) and derives the
        title from the URL filename.
        """
        path = urlparse(result.url).path
        filename = unquote(path.rsplit("/", 1)[-1])
        # Strip the document extension and replace separators with spaces.
        if filename.lower().endswith(extension):
            filename = filename[: -len(extension)]
        title = filename.replace("_", " ").replace("-", " ").strip() or result.url

        md = self._clean_markdown(result.markdown)
        md = self._validate_markdown(md)

        return ExtractedPage(url=result.url, title=title, markdown=md)

    def _extract_main_content(self, result: CrawlResult) -> ExtractedPage:
        """Use trafilatura to extract the main body content.

        Falls back to markdownify when trafilatura captures less than
        ``_COVERAGE_THRESHOLD`` of the page's visible text.
        """
        soup, supplements, product = self._prepare_soup(
            result,
            use_sentinel=True,
            recover_supplements=True,
        )
        html = str(soup)
        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            favor_recall=True,
        )
        md = self._fix_markdown_tables(extracted or "")
        if self.page_config.separate_items:
            md = self._replace_item_sentinels(md)
        md = self._clean_markdown(md)

        # Fall back to markdownify when trafilatura captured too little.
        visible_len = self._visible_text_length_from_soup(soup)
        if visible_len > 0 and len(md.strip()) / visible_len < _COVERAGE_THRESHOLD:
            return self._extract_full_html(result, soup=soup, product=product, product_checked=True)

        for fragment in supplements:
            formatted = self._format_faq_questions(fragment)
            cleaned = self._clean_markdown(formatted)
            if cleaned.strip():
                md = md.rstrip() + _ITEM_SEPARATOR_MD + cleaned

        return self._finalize_extracted_page(
            result=result,
            markdown=md,
            product=product,
            product_checked=True,
        )

    def _extract_full_html(
        self,
        result: CrawlResult,
        *,
        soup: BeautifulSoup | None = None,
        product: dict | None = None,
        product_checked: bool = False,
    ) -> ExtractedPage:
        """Use markdownify on the (optionally tag-filtered) HTML."""
        if soup is None:
            soup, _, product = self._prepare_soup(result, use_sentinel=False)
            product_checked = True
        html = str(soup)
        md = markdownify(
            html,
            heading_style=_MARKDOWNIFY_HEADING_STYLE,
            strip=_MARKDOWNIFY_STRIP_TAGS,
            table_infer_header=True,
        )
        md = self._replace_item_sentinels(md)
        md = self._clean_markdown(md)

        return self._finalize_extracted_page(
            result=result,
            markdown=md,
            product=product,
            product_checked=product_checked,
        )

    def _finalize_extracted_page(
        self,
        *,
        result: CrawlResult,
        markdown: str,
        product: dict | None = None,
        product_checked: bool = False,
    ) -> ExtractedPage:
        if not product_checked:
            product = self._extract_product_header(result.html)
        title = self._extract_title(result.html, url=result.url)
        if product:
            product_name = product.get("name", "")
            if product_name:
                title = product_name
            header_parts: list[str] = []
            if product.get("brand"):
                header_parts.append(f"**{product['brand']}**")
            if product_name:
                header_parts.append(f"## {product_name}")
            price_display = self._format_product_price(product)
            if price_display:
                header_parts.append(f"{_RETAIL_PRICE_PREFIX}{price_display}")
            if header_parts:
                markdown = "\n\n".join(header_parts) + "\n\n" + markdown

        markdown = self._resolve_fragment_links(markdown, result.url)
        if self.page_config.absolute_links:
            markdown = self._resolve_relative_links(markdown, result.url)
        markdown = self._validate_markdown(markdown)

        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=markdown,
        )

    # ------------------------------------------------------------------
    # Fragment link resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_fragment_links(text: str, page_url: str) -> str:
        """Resolve fragment-only links to absolute URLs.

        Replaces ``](#fragment)`` with ``](page_url#fragment)`` so that
        fragment-only hrefs (common JS placeholders) point to the
        actual page.
        """

        def _replacer(m: re.Match[str]) -> str:
            fragment = m.group(1)
            return "](" + urljoin(page_url, "#" + fragment) + ")"

        return _FRAGMENT_LINK_RE.sub(_replacer, text)

    @staticmethod
    def _resolve_relative_links(text: str, page_url: str) -> str:
        """Resolve relative links to absolute URLs.

        Replaces ``](relative/path)`` with ``](https://host/resolved/path)``
        using ``urljoin`` against the page's own URL.  Skips links that
        are already absolute (``http(s)://``), ``mailto:``, ``tel:``, or
        fragment-only (``#``).
        """
        if not page_url:
            return text

        def _replacer(m: re.Match[str]) -> str:
            relative = m.group(1)
            return "](" + urljoin(page_url, relative) + ")"

        return _RELATIVE_LINK_RE.sub(_replacer, text)

    # ------------------------------------------------------------------
    # CMS data-attribute stripping
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_soup(html: _HtmlOrSoup) -> tuple[BeautifulSoup, bool]:
        return HTMLPreprocessor.coerce_soup(html)

    @staticmethod
    def _return_html_or_soup(soup: BeautifulSoup, stringify: bool) -> _HtmlOrSoup:
        return HTMLPreprocessor.return_html_or_soup(soup, stringify)

    @staticmethod
    def _strip_data_attributes(html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor.strip_data_attributes(html)

    # ------------------------------------------------------------------
    # Empty link population
    # ------------------------------------------------------------------

    @staticmethod
    def _link_text_from_href(href: str) -> str:
        return HTMLPreprocessor.link_text_from_href(href)

    @staticmethod
    def _populate_empty_links(html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor.populate_empty_links(html)

    # ------------------------------------------------------------------
    # Heading child spacing
    # ------------------------------------------------------------------

    @staticmethod
    def _space_heading_children(html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor.space_heading_children(html)

    # ------------------------------------------------------------------
    # Strikethrough preservation
    # ------------------------------------------------------------------

    @staticmethod
    def _preserve_strikethrough(html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor.preserve_strikethrough(html)

    # ------------------------------------------------------------------
    # Table cell flattening (prevent multi-line Markdown table cells)
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_table_cells(html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor.flatten_table_cells(html)

    # ------------------------------------------------------------------
    # Item separation (structured product/card grouping)
    # ------------------------------------------------------------------

    def _insert_item_separators(self, html: _HtmlOrSoup, *, use_sentinel: bool) -> _HtmlOrSoup:
        """Insert separators between repeated structural items in the HTML.

        When *use_sentinel* is ``True`` (trafilatura mode), a ``<p>`` with
        a unique text sentinel is inserted because trafilatura strips
        ``<hr>`` elements.  When ``False`` (markdownify mode), a plain
        ``<hr>`` is used.

        If ``page_config.item_selector`` is set, that CSS selector
        identifies items directly.  Otherwise, auto-detection finds all
        qualifying groups of repeated same-tag-and-class siblings and
        inserts separators into each group.
        """
        soup, stringify = ContentExtractor._coerce_soup(html)

        if self.page_config.item_selector:
            all_groups = [soup.select(self.page_config.item_selector)]
        else:
            all_groups = self._find_repeated_items(soup)
            all_groups = [self._include_interstitial_siblings(g) for g in all_groups]

        modified = False
        for items in all_groups:
            if len(items) < 2:
                continue
            modified = True
            if use_sentinel:
                # Leading sentinel before the first item isolates preceding
                # page content (nav, filters) from the product cards.
                lead = soup.new_tag("p")
                lead.string = _ITEM_SENTINEL
                items[0].insert_before(lead)
                for item in items[:-1]:
                    sep = soup.new_tag("p")
                    sep.string = _ITEM_SENTINEL
                    item.append(sep)
            else:
                lead_hr = soup.new_tag("hr")
                items[0].insert_before(lead_hr)
                for item in reversed(items[1:]):
                    sep = soup.new_tag("hr")
                    item.insert_before(sep)

        if not modified:
            return html
        return ContentExtractor._return_html_or_soup(soup, stringify)

    @staticmethod
    def _find_repeated_items(soup: BeautifulSoup) -> list[list[Tag]]:
        """Auto-detect all qualifying groups of repeated structural elements.

        Walks the DOM looking for parents whose direct children share the
        same ``(tag_name, frozenset_of_classes)`` signature.  Groups must
        have at least 3 members, each with at least 20 characters of text.

        Returns **all** qualifying groups (sorted by descending score so
        the highest-scoring group comes first).  Groups whose items are
        already covered by a higher-scoring group are deduplicated.

        Elements inside ``<nav>``, ``<header>``, ``<footer>`` are ignored
        to avoid picking up navigation links.
        """
        skip_parents = _ITEM_SKIP_TAGS
        min_text_len = _MIN_ITEM_TEXT_LEN
        groups: dict[tuple, list[Tag]] = {}

        for parent in soup.find_all(True):
            if parent.name in skip_parents:
                continue
            # Check if any ancestor is a skip_parents tag
            if any(a.name in skip_parents for a in parent.parents if isinstance(a, Tag)):
                continue

            children_by_sig: dict[tuple, list[Tag]] = {}
            for child in parent.children:
                if not isinstance(child, Tag):
                    continue
                classes = frozenset(child.get("class", []))
                sig = (child.name, classes)
                children_by_sig.setdefault(sig, []).append(child)

            for sig, children in children_by_sig.items():
                if len(children) < _MIN_REPEATED_GROUP:
                    continue
                # Filter: each child must have meaningful text
                qualified = [c for c in children if len(c.get_text(strip=True)) >= min_text_len]
                if len(qualified) < _MIN_REPEATED_GROUP:
                    continue
                key = (id(parent), sig)
                groups[key] = qualified

        if not groups:
            return []

        # Score: count * average text length — favours large groups of content-rich items
        def score(items: list[Tag]) -> float:
            avg_len = sum(len(t.get_text(strip=True)) for t in items) / len(items)
            return len(items) * avg_len

        # Sort by score descending and deduplicate: if any item in a group
        # is already covered by a higher-scoring group, skip that group.
        ranked = sorted(groups.values(), key=score, reverse=True)
        seen_ids: set[int] = set()
        result: list[list[Tag]] = []
        for items in ranked:
            item_ids = {id(t) for t in items}
            if item_ids & seen_ids:
                continue
            seen_ids.update(item_ids)
            result.append(items)
        return result

    @staticmethod
    def _include_interstitial_siblings(items: list[Tag]) -> list[Tag]:
        """Expand *items* to include non-matching siblings between them.

        When auto-detection finds a dominant group of same-signature
        siblings, differently-classed siblings interspersed among them
        (e.g. promotional banners) are missed.  This method walks the
        shared parent's direct children and includes any Tag siblings
        that sit **between** the first and last matched item and have
        at least 20 characters of text.
        """
        if len(items) < 2:
            return items

        parent = items[0].parent
        if parent is None:
            return items

        # Verify all items share the same parent
        if not all(item.parent is parent for item in items):
            return items

        items_set = set(id(item) for item in items)
        siblings = [child for child in parent.children if isinstance(child, Tag)]

        # Find index range of matched items among siblings
        matched_indices = [i for i, sib in enumerate(siblings) if id(sib) in items_set]
        if not matched_indices:
            return items

        first_idx, last_idx = matched_indices[0], matched_indices[-1]

        # Collect all siblings between first and last, including interstitials
        expanded: list[Tag] = []
        for i in range(first_idx, last_idx + 1):
            sib = siblings[i]
            if id(sib) in items_set or len(sib.get_text(strip=True)) >= _MIN_INTERSTITIAL_LEN:
                expanded.append(sib)

        return expanded

    @staticmethod
    def _fix_markdown_tables(text: str) -> str:
        return MarkdownPipeline.fix_markdown_tables(text)

    @staticmethod
    def _normalize_table_block(block: list[str]) -> list[str]:
        return MarkdownPipeline.normalize_table_block(block)

    def _filter_tags(self, html: _HtmlOrSoup) -> _HtmlOrSoup:
        return HTMLPreprocessor(self.page_config).filter_tags(html)

    # ------------------------------------------------------------------
    # Markdown validation
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content_tokens(text: str) -> Counter:
        """Extract a multiset of content tokens from Markdown text.

        Strips Markdown syntax characters (``# * ` > | ~ [ ] \\``) and
        splits on whitespace.  The resulting tokens represent the actual
        human-readable content: words, numbers, currency signs, commas,
        periods, etc.
        """
        stripped = _MD_SYNTAX_RE.sub(" ", text)
        return Counter(stripped.split())

    @staticmethod
    def _validate_markdown(md: str) -> str:
        """Format *md* with mdformat and return the result.

        A **content-preservation guard** compares the plain-text tokens
        (words, numbers, punctuation) before and after formatting.  If
        any content tokens were lost, the original text is returned
        unchanged so that no information is silently dropped.

        If mdformat raises an exception the original text is also
        returned unchanged (graceful degradation).
        """
        if not md or not md.strip():
            return md
        try:
            formatted = mdformat.text(md, extensions=list(_MDFORMAT_EXTENSIONS))
        except Exception:  # noqa: BLE001 — never crash the crawl
            return md

        # Content-preservation check: every token present in the
        # original must still be present in the formatted output.
        original_tokens = ContentExtractor._extract_content_tokens(md)
        formatted_tokens = ContentExtractor._extract_content_tokens(formatted)
        lost = original_tokens - formatted_tokens
        if lost:
            return md

        return formatted

    # ------------------------------------------------------------------
    # Markdown post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_markdown(text: str) -> str:
        return MarkdownPipeline.clean(text)

    @staticmethod
    def _replace_item_sentinels(text: str) -> str:
        text = _ITEM_SENTINEL_MARKDOWN_RE.sub(_ITEM_SEPARATOR_MD, text)
        return text.replace(_ITEM_SENTINEL, _ITEM_SEPARATOR_MD)

    @staticmethod
    def _strip_template_variables(text: str) -> str:
        return MarkdownPipeline.strip_template_variables(text)

    @staticmethod
    def _collapse_blank_lines(text: str) -> str:
        return MarkdownPipeline.collapse_blank_lines(text)

    # ------------------------------------------------------------------
    # Separated-item reformatter (product cards split by ---)
    # ------------------------------------------------------------------

    @staticmethod
    def _reformat_separated_items(text: str) -> str:
        return MarkdownPipeline.reformat_separated_items(text)

    @staticmethod
    def _parse_product_section(section: str) -> str | None:
        return MarkdownPipeline.parse_product_section(section)

    @staticmethod
    def _format_outright_price(price: str) -> str:
        return MarkdownPipeline.format_outright_price(price)

    @staticmethod
    def _compact_product_listings(text: str) -> str:
        return MarkdownPipeline.compact_product_listings(text)

    @staticmethod
    def _try_parse_product_entry(
        lines: list[str],
        start: int,
        price_re: re.Pattern[str],
        heading_re: re.Pattern[str],
        hr_re: re.Pattern[str],
    ) -> tuple[dict | None, int]:
        return MarkdownPipeline.try_parse_product_entry(lines, start, price_re, heading_re, hr_re)

    @staticmethod
    def _dedup_paragraphs(text: str) -> str:
        return MarkdownPipeline.dedup_paragraphs(text)

    @staticmethod
    def _compact_short_paragraphs(text: str) -> str:
        return MarkdownPipeline.compact_short_paragraphs(text)

    # ------------------------------------------------------------------
    # Coverage check
    # ------------------------------------------------------------------

    @staticmethod
    def _visible_text_length(html: str) -> int:
        """Approximate the length of human-visible text in HTML."""
        soup = BeautifulSoup(html, _HTML_PARSER)
        return ContentExtractor._visible_text_length_from_soup(soup)

    @staticmethod
    def _visible_text_length_from_soup(soup: BeautifulSoup) -> int:
        parts: list[str] = []
        for text_node in soup.find_all(string=True):
            parent = text_node.parent
            if parent is None:
                continue
            if any(
                getattr(ancestor, "name", None) in _NON_VISIBLE_TEXT_TAGS
                for ancestor in (parent, *parent.parents)
            ):
                continue
            text = text_node.strip()
            if text:
                parts.append(text)
        return len(" ".join(parts))

    # ------------------------------------------------------------------
    # FAQ formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_faq_questions(text: str) -> str:
        return MarkdownPipeline.format_faq_questions(text)

    # ------------------------------------------------------------------
    # Supplementary section recovery (FAQ, accordion, Q&A)
    # ------------------------------------------------------------------

    _SUPP_CLASS_KEYWORDS = re.compile(
        r"faq|frequently.asked|accordion|q.and.a|questions?.and.answers?",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_supplementary_sections(html: _HtmlOrSoup) -> list[str]:
        """Detect FAQ / accordion sections that trafilatura would strip.

        Returns a list of Markdown fragments (one per detected section).
        Uses four heuristics, deduplicates by element identity, and
        converts each matched subtree to Markdown via *markdownify*.
        """
        soup, _ = ContentExtractor._coerce_soup(html)
        seen_ids: set[int] = set()
        sections: list[str] = []

        def _add(tag: Tag) -> None:
            tid = id(tag)
            if tid in seen_ids:
                return
            # Skip tiny fragments that are unlikely to be real content.
            if len(tag.get_text(strip=True)) < _MIN_SUPPLEMENT_TEXT_LEN:
                return
            seen_ids.add(tid)
            # Also mark all descendants so later heuristics skip them.
            for desc in tag.find_all(True):
                seen_ids.add(id(desc))
            md = markdownify(
                str(tag), heading_style=_MARKDOWNIFY_HEADING_STYLE, strip=_MARKDOWNIFY_STRIP_TAGS
            )
            if md.strip():
                sections.append(md)

        # 1. Schema.org FAQPage structured data
        for el in soup.find_all(attrs={"itemtype": _FAQ_SCHEMA_RE}):
            if isinstance(el, Tag):
                _add(el)

        # 2. HTML5 <details>/<summary> groups (≥ 3 siblings)
        for parent in soup.find_all(True):
            details = [c for c in parent.children if isinstance(c, Tag) and c.name == "details"]
            if len(details) >= _MIN_FAQ_DETAILS and id(parent) not in seen_ids:
                _add(parent)

        # 3. CSS class / id keyword matching
        for el in soup.find_all(True):
            if id(el) in seen_ids:
                continue
            classes = " ".join(el.get("class", []))
            el_id = el.get("id", "") or ""
            if ContentExtractor._SUPP_CLASS_KEYWORDS.search(
                classes
            ) or ContentExtractor._SUPP_CLASS_KEYWORDS.search(el_id):
                _add(el)

        # 4. Heading (h2-h4) whose text mentions FAQ / Frequently Asked
        for heading in soup.find_all(_FAQ_HEADING_RANGE_RE):
            if id(heading) in seen_ids:
                continue
            if _FAQ_KEYWORD_RE.search(heading.get_text()):
                parent = heading.parent
                if parent and isinstance(parent, Tag) and id(parent) not in seen_ids:
                    _add(parent)

        return sections

    # Known-generic titles that should be replaced by a better source.
    _GENERIC_TITLES = re.compile(
        r"^(product\s+plp/?pdp|home|untitled|welcome|page)$",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_title(html: str, *, url: str = "") -> str:
        """Extract the best page title from multiple HTML sources.

        Priority order:
        1. ``<title>`` tag — used if it looks specific (not generic).
        2. ``<meta property="og:title">`` — common on product / listing pages.
        3. First ``<h1>`` in the body.
        4. URL slug — derive a human-readable title from the URL path.
        5. Fall back to the (possibly generic) ``<title>``.

        Returns an empty string when no usable title is found.
        """
        # 1. <title> tag
        title_match = _TITLE_TAG_RE.search(html)
        title_text = title_match.group(1).strip() if title_match else ""

        if title_text and not ContentExtractor._GENERIC_TITLES.match(title_text):
            return title_text

        # 2. og:title meta tag
        og_match = _OG_TITLE_RE_1.search(html)
        if not og_match:
            og_match = _OG_TITLE_RE_2.search(html)
        if og_match:
            og_text = og_match.group(1).strip()
            if og_text and not ContentExtractor._GENERIC_TITLES.match(og_text):
                return og_text

        # 3. First <h1>
        h1_match = _H1_TAG_RE.search(html)
        if h1_match:
            # Strip inner HTML tags to get plain text.
            h1_text = _HTML_TAG_STRIP_RE.sub("", h1_match.group(1)).strip()
            if h1_text:
                return h1_text

        # 4. URL slug
        if url:
            slug_title = ContentExtractor._title_from_url(url)
            if slug_title:
                return slug_title

        # 5. Fall back to the (possibly generic) <title>.
        return title_text

    # Known tech-product suffixes to upper-case after title-casing a slug.
    _SLUG_UPPER = re.compile(
        r"\b(5g|4g|lte|wifi|nfc|gb|tb|mb|ram|cpu|gpu|oled|amoled|ai|se|pro|max)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Derive a human-readable title from the last URL path segment."""
        path = urlparse(url).path.rstrip("/")
        if not path or path == "/":
            return ""
        slug = path.rsplit("/", 1)[-1]
        # Ignore slugs that look like IDs / hashes / query-like.
        if not slug or len(slug) < _MIN_SLUG_LEN or slug.isdigit():
            return ""
        title = slug.replace("-", " ").replace("_", " ").strip()
        title = title.title()
        # Fix common tech abbreviations.
        title = ContentExtractor._SLUG_UPPER.sub(
            lambda m: m.group(1).upper(),
            title,
        )
        return title

    # ------------------------------------------------------------------
    # Product header recovery (JSON-LD / OG meta)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_product_header(html: str, *, soup: BeautifulSoup | None = None) -> dict | None:
        return ProductMetadataExtractor.extract(html, soup=soup)

    @staticmethod
    def _product_from_jsonld(html: str) -> dict | None:
        return ProductMetadataExtractor.from_jsonld(html)

    @staticmethod
    def _find_product_in_jsonld(data: object) -> dict | None:
        return ProductMetadataExtractor.find_in_jsonld(data)

    @staticmethod
    def _product_from_og(html: str) -> dict | None:
        return ProductMetadataExtractor.from_open_graph(html)

    @staticmethod
    def _product_from_dom(html: str) -> dict | None:
        return ProductMetadataExtractor.from_dom(html)

    @staticmethod
    def _format_product_price(product: dict) -> str:
        return ProductMetadataExtractor.format_price(product)

    # ------------------------------------------------------------------
    # Section-label promotion
    # ------------------------------------------------------------------

    @staticmethod
    def _promote_section_labels(text: str) -> str:
        return MarkdownPipeline.promote_section_labels(text)
