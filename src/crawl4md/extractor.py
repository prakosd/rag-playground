"""ContentExtractor — converts crawled HTML to clean Markdown text."""

from __future__ import annotations

import json
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

import mdformat
import trafilatura
from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify

from crawl4md.config import CrawlResult, ExtractedPage, PageConfig
from crawl4md.progress import ProgressReporter

# Sentinel inserted between repeated items *before* trafilatura extraction.
# trafilatura strips <hr> but preserves plain text in <p> tags.
_ITEM_SENTINEL = "CRAWL4MD_ITEM_BREAK"

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
# mdformat extension for GitHub Flavoured Markdown validation
_MDFORMAT_EXTENSIONS = ("gfm",)
# Markdown separator replacing item sentinels after extraction
_ITEM_SEPARATOR_MD = "\n\n---\n\n"

# ------------------------------------------------------------------
# Strikethrough preservation
# ------------------------------------------------------------------

# Regex matching HTML strikethrough tags (<del>, <s>, <strike>)
_STRIKETHROUGH_RE = re.compile(
    r"<(del|s|strike)\b[^>]*>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
# Markdown replacement pattern for strikethrough tags
_STRIKETHROUGH_MD = r"~~\2~~"

# ------------------------------------------------------------------
# Heading detection
# ------------------------------------------------------------------

# Regex matching heading tag names (h1 through h6)
_HEADING_TAG_RE = re.compile(r"^h[1-6]$")

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
# Block-level tags to unwrap inside table cells during preprocessing
_TABLE_CELL_BLOCK_TAGS = frozenset({"p", "div"})

# ------------------------------------------------------------------
# Empty link population thresholds
# ------------------------------------------------------------------

# Minimum combined child-text length for wrapper <a> tag relocation
_MIN_WRAPPER_TEXT_LEN = 20
# Minimum sibling text length to detect CSS overlay links
_MIN_OVERLAY_SIBLING_LEN = 30
# Default text for empty links when no label can be recovered
_LINK_FALLBACK_TEXT = "Link"
# Text injected for wrapper-link references (e.g. product cards)
_WRAPPER_LINK_LABEL = "Learn more"

# ------------------------------------------------------------------
# Product parsing thresholds
# ------------------------------------------------------------------

# Maximum chars for a line to be considered a product name
_MAX_PRODUCT_NAME_LEN = 80
# Maximum chars for unclassified short lines treated as badges
_MAX_BADGE_LINE_LEN = 60
# Minimum consecutive product entries needed to trigger reformatting
_MIN_PRODUCT_ENTRIES = 3
# Minimum number of --- separators (sections - 1) to activate item reformatting
_MIN_SEPARATED_SECTIONS = 4

# ------------------------------------------------------------------
# Supplementary / FAQ detection thresholds
# ------------------------------------------------------------------

# Minimum text length for a supplementary section fragment to be included
_MIN_SUPPLEMENT_TEXT_LEN = 30
# Minimum <details> siblings to trigger FAQ/accordion grouping
_MIN_FAQ_DETAILS = 3
# Maximum question line length for FAQ heading promotion
_MAX_FAQ_QUESTION_LEN = 200
# Minimum URL slug length for title derivation
_MIN_SLUG_LEN = 3

# ------------------------------------------------------------------
# Short-paragraph compaction
# ------------------------------------------------------------------

# Maximum single-line paragraph length before it's excluded from compaction
_MAX_SHORT_PARAGRAPH_LEN = 120

# ------------------------------------------------------------------
# Markdown structure detection regexes (shared across multiple methods)
# ------------------------------------------------------------------

# Matches Markdown heading lines (# through ######)
_MD_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
# Matches Markdown horizontal rules (three or more dashes)
_MD_HORIZONTAL_RULE_RE = re.compile(r"^---+$")
# Matches Markdown unordered list items (-, *, or +)
_MD_LIST_ITEM_RE = re.compile(r"^[-*+]\s")
# Splits text on two or more consecutive newlines (paragraph boundaries)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\n+")
# Splits text on two or more newlines (variant for dedup, matches \n{2,})
_PARAGRAPH_SPLIT_2_RE = re.compile(r"\n{2,}")

# Unicode Line Separator (U+2028) and Paragraph Separator (U+2029) —
# introduced by PDF extraction (pymupdf4llm); normalised to \n early
# so downstream regex patterns (which expect only \n) work correctly.
_UNICODE_LINE_SEP_RE = re.compile("[\u2028\u2029]")

# Matches HTML data-* attribute names (e.g. data-cmp-data-layer).
# Used to strip CMS data-layer payloads that leak as visible text.
_DATA_ATTR_RE = re.compile(r"^data-")

# Matches leaked CMS attribute debris in Markdown output, e.g.
# ``\r\n"}}}" id="text-abc123" class="cmp-text">``
_CMS_ATTR_JUNK_RE = re.compile(
    r"(?:\\r\\n|\r\n|\r|\n)*"
    r'["\'}\]\)]*\}\}["\'>]*'
    r'(?:\s+[a-z][a-z\-]*="[^"]*")*'
    r"\s*>",
)

# Matches literal escaped CRLF sequences (4-char ``\r\n``) that leak
# from CMS JSON payloads embedded in HTML data attributes.
_LITERAL_CRLF_RE = re.compile(r"\\r\\n")

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
# JSON-LD / structured data extraction
# ------------------------------------------------------------------

# Extracts <script type="application/ld+json"> blocks from HTML
_JSON_LD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Table normalization regexes
# ------------------------------------------------------------------

# Matches a line containing at least one pipe separator (potential table row)
_PIPE_LINE_RE = re.compile(r"^\|?.+\|.+\|?\s*$")
# Matches a Markdown table separator row (e.g. | --- | --- |)
_TABLE_SEPARATOR_RE = re.compile(r"^\|?(\s*-{3,}\s*\|)+\s*-{3,}\s*\|?\s*$")

# ------------------------------------------------------------------
# FAQ / supplementary section detection regexes
# ------------------------------------------------------------------

# Matches heading tag names h2 through h4 (used for FAQ heading search)
_FAQ_HEADING_RANGE_RE = re.compile(r"^h[2-4]$")
# Matches text containing "FAQ" or "Frequently Asked" keywords
_FAQ_KEYWORD_RE = re.compile(r"\bfaq\b|frequently\s+asked", re.IGNORECASE)

# ------------------------------------------------------------------
# Price detection regexes (compact product listing)
# ------------------------------------------------------------------

# Matches a full product price line (from $XX.XX/mth, or ~~$XX.XX~~$XX.XX, etc.)
_PRICE_LINE_RE = re.compile(
    r"^(?:from\s+)?(?:or\s*)?(?:~~)?\$\$?[\d,]+(?:\.\d{2})?(?:~~)?"
    r"(?:/mth)?(?:\$\$?[\d,]+(?:\.\d{2})?)?$"
)
# Matches any dollar-amount price pattern (e.g. $1,234.56)
_PRICE_DETECT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")

# ------------------------------------------------------------------
# Product metadata string constants
# ------------------------------------------------------------------

# Prefix for retail price display in product headers
_RETAIL_PRICE_PREFIX = "Retail price: "
# URL path segments that are too generic to be brand names
_BRAND_EXCLUSION_KEYWORDS = frozenset(
    {"devices", "mobile", "store", "personal", "products", "shop", "buy"}
)

# ------------------------------------------------------------------
# DOM / content thresholds for product metadata extraction
# ------------------------------------------------------------------

# Lines shorter than this in badges/short-line detection are compacted
_BADGE_SHORT_LINE_THRESHOLD = 40
# Maximum parent-node depth to walk when searching for a heading
_MAX_DOM_DEPTH = 15
# Minimum content length (chars) for a section to be considered substantial
_SUBSTANTIAL_CONTENT_LEN = 80
# Maximum label length for section-label promotion to heading
_MAX_SECTION_LABEL_LEN = 60

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
        if self.page_config.extract_main_content:
            return self._extract_main_content(result)
        return self._extract_full_html(result)

    def _extract_pdf_page(self, result: CrawlResult) -> ExtractedPage:
        """Extract content from a PDF crawl result.

        Skips all HTML preprocessing since the markdown was already
        generated by pymupdf4llm.  Derives the title from the URL
        filename.
        """
        from urllib.parse import unquote, urlparse

        path = urlparse(result.url).path
        filename = unquote(path.rsplit("/", 1)[-1])
        # Strip .pdf extension and replace separators with spaces
        if filename.lower().endswith(".pdf"):
            filename = filename[:-4]
        title = filename.replace("_", " ").replace("-", " ").strip() or result.url

        md = self._clean_markdown(result.markdown)
        md = self._validate_markdown(md)

        return ExtractedPage(url=result.url, title=title, markdown=md)

    def _extract_main_content(self, result: CrawlResult) -> ExtractedPage:
        """Use trafilatura to extract the main body content.

        Falls back to markdownify when trafilatura captures less than
        ``_COVERAGE_THRESHOLD`` of the page's visible text.
        """
        soup = BeautifulSoup(result.html, _HTML_PARSER)
        self._strip_data_attributes(soup)
        # Capture supplementary sections (e.g. FAQs) before trafilatura strips them.
        supplements = self._extract_supplementary_sections(str(soup))
        self._filter_tags(soup)
        self._preserve_strikethrough(soup)
        self._space_heading_children(soup)
        self._populate_empty_links(soup)
        self._flatten_table_cells(soup)
        if self.page_config.separate_items:
            self._insert_item_separators(soup, use_sentinel=True)
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
            md = md.replace(_ITEM_SENTINEL, _ITEM_SEPARATOR_MD)
        md = self._clean_markdown(md)

        # Fall back to markdownify when trafilatura captured too little.
        visible_len = self._visible_text_length(result.html)
        if visible_len > 0 and len(md.strip()) / visible_len < _COVERAGE_THRESHOLD:
            return self._extract_full_html(result)

        for fragment in supplements:
            formatted = self._format_faq_questions(fragment)
            cleaned = self._clean_markdown(formatted)
            if cleaned.strip():
                md = md.rstrip() + _ITEM_SEPARATOR_MD + cleaned

        # Recover product metadata and use it for a richer title & header.
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
                md = "\n\n".join(header_parts) + "\n\n" + md

        md = self._resolve_fragment_links(md, result.url)
        if self.page_config.absolute_links:
            md = self._resolve_relative_links(md, result.url)
        md = self._validate_markdown(md)

        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
        )

    def _extract_full_html(self, result: CrawlResult) -> ExtractedPage:
        """Use markdownify on the (optionally tag-filtered) HTML."""
        soup = BeautifulSoup(result.html, _HTML_PARSER)
        self._strip_data_attributes(soup)
        self._filter_tags(soup)
        self._preserve_strikethrough(soup)
        self._space_heading_children(soup)
        self._populate_empty_links(soup)
        self._flatten_table_cells(soup)
        if self.page_config.separate_items:
            self._insert_item_separators(soup, use_sentinel=False)
        html = str(soup)
        md = markdownify(
            html,
            heading_style=_MARKDOWNIFY_HEADING_STYLE,
            strip=_MARKDOWNIFY_STRIP_TAGS,
            table_infer_header=True,
        )
        md = self._clean_markdown(md)

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
                md = "\n\n".join(header_parts) + "\n\n" + md

        md = self._resolve_fragment_links(md, result.url)
        if self.page_config.absolute_links:
            md = self._resolve_relative_links(md, result.url)
        md = self._validate_markdown(md)

        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
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
        if isinstance(html, BeautifulSoup):
            return html, False
        return BeautifulSoup(html, _HTML_PARSER), True

    @staticmethod
    def _return_html_or_soup(soup: BeautifulSoup, stringify: bool) -> _HtmlOrSoup:
        return str(soup) if stringify else soup

    @staticmethod
    def _strip_data_attributes(html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Remove all ``data-*`` attributes from HTML elements.

        CMS platforms (e.g. Adobe Experience Manager) embed JSON payloads
        in ``data-cmp-data-layer`` and similar attributes.  When the JSON
        contains unescaped quotes, ``html.parser`` misparses the boundary
        and the payload leaks into the DOM as visible text — producing
        duplicate content, literal ``\\r\\n``, and attribute debris in
        the Markdown output.  Stripping ``data-*`` attributes prevents
        this at source; these attributes are never browser-visible.
        """
        soup, stringify = ContentExtractor._coerce_soup(html)
        for tag in soup.find_all(True):
            names = [a for a in tag.attrs if _DATA_ATTR_RE.match(a)]
            for name in names:
                del tag[name]
        return ContentExtractor._return_html_or_soup(soup, stringify)

    # ------------------------------------------------------------------
    # Empty link population
    # ------------------------------------------------------------------

    @staticmethod
    def _link_text_from_href(href: str) -> str:
        """Derive human-readable link text from a URL.

        Fallback chain: last meaningful path segment (stripped of
        extension, hyphens/underscores converted to spaces, title-cased)
        → ``"Link"``.
        """
        path = urlparse(href).path.rstrip("/")
        if path:
            segment = path.rsplit("/", 1)[-1]
            # Strip common file extensions
            dot = segment.rfind(".")
            if dot > 0:
                segment = segment[:dot]
            if segment:
                return segment.replace("-", " ").replace("_", " ").title()
        return _LINK_FALLBACK_TEXT

    @staticmethod
    def _populate_empty_links(html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Give visible text to ``<a>`` tags that have ``href`` but no content.

        Many sites use empty ``<a>`` overlays (e.g. card-link patterns)
        that have a valid ``href`` but no inner text.  Both trafilatura
        and markdownify silently discard these, so the URL never appears
        in the extracted Markdown.

        This pre-processing step populates each empty anchor with text
        derived from: ``title`` attr → ``aria-label`` attr → URL path
        slug → ``"Link"``.

        **Overlay relocation:** when the populated anchor appears to be a
        CSS overlay (no child elements, and its parent has other children
        with ≥ 30 chars of combined text), the anchor is moved to the
        *end* of its parent so that card content appears first and the
        reference link follows.
        """
        soup, stringify = ContentExtractor._coerce_soup(html)
        relocate: list[Tag] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:")):
                continue
            had_children = bool(a.find(True))
            child_text = a.get_text(strip=True)
            # Wrapper links: <a> wrapping a card with child elements and
            # substantial text (e.g. product cards).  Unwrap and inject a
            # reference link after the promoted children so the URL is
            # preserved.
            if had_children and child_text and len(child_text) >= _MIN_WRAPPER_TEXT_LEN:
                ref = soup.new_tag("a", href=href)
                ref.string = _WRAPPER_LINK_LABEL
                a.insert_after(ref)
                ref.insert_before(" ")
                a.unwrap()
                continue
            # Only target anchors with no meaningful text content
            if child_text:
                continue
            if had_children:
                # Anchors with child elements (e.g. <img>) but no text
                # are intentional structures — skip.
                continue
            # Fallback chain for link text
            text = (
                (a.get("title") or "").strip()
                or (a.get("aria-label") or "").strip()
                or ContentExtractor._link_text_from_href(href)
            )
            a.string = text
            # Detect overlay links: truly empty (no prior child elements)
            # and parent has substantial sibling content.
            if a.parent is not None:
                sibling_text = "".join(
                    sib.get_text(strip=True)
                    for sib in a.parent.children
                    if sib is not a and isinstance(sib, Tag)
                )
                if len(sibling_text) >= _MIN_OVERLAY_SIBLING_LEN:
                    relocate.append(a)
        # Move overlay links to the end of their parent so card content
        # appears before the reference link.
        for a in relocate:
            parent = a.parent
            if parent is not None:
                a.extract()
                parent.append(a)
        return ContentExtractor._return_html_or_soup(soup, stringify)

    # ------------------------------------------------------------------
    # Heading child spacing
    # ------------------------------------------------------------------

    @staticmethod
    def _space_heading_children(html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Insert whitespace between adjacent inline children in headings.

        Headings like ``<h6><span>Broadband</span><span>For seamless
        connection</span></h6>`` produce ``BroadbandFor seamless
        connection`` after extraction because there is no whitespace
        between the sibling elements.  This inserts a single space
        between consecutive inline Tag children to prevent concatenation.
        """
        soup, stringify = ContentExtractor._coerce_soup(html)
        from itertools import pairwise

        for heading in soup.find_all(_HEADING_TAG_RE):
            children = list(heading.children)
            if len(children) < 2:
                continue
            for a, b in pairwise(children):
                if isinstance(a, Tag) and isinstance(b, Tag):
                    # Check there is no whitespace text node between them.
                    # (pairwise gives consecutive children; if the DOM has
                    # a text node between two Tags it will appear as a
                    # separate child and the pair won't be (Tag, Tag).)
                    a.insert_after(NavigableString(" "))
        return ContentExtractor._return_html_or_soup(soup, stringify)

    # ------------------------------------------------------------------
    # Strikethrough preservation
    # ------------------------------------------------------------------

    @staticmethod
    def _preserve_strikethrough(html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Convert ``<del>``, ``<s>``, and ``<strike>`` tags to ``~~text~~``.

        Trafilatura silently drops these tags, losing the visual
        distinction between original and discounted prices (e.g.
        ``<del>$2,128.00</del>$1,828.00``).  By replacing them with
        Markdown strikethrough *before* extraction, the semantic is
        preserved in the final output.
        """
        if isinstance(html, BeautifulSoup):
            for tag in html.find_all(["del", "s", "strike"]):
                tag.insert_before(NavigableString("~~"))
                tag.insert_after(NavigableString("~~"))
                tag.unwrap()
            return html
        return _STRIKETHROUGH_RE.sub(
            _STRIKETHROUGH_MD,
            html,
        )

    # ------------------------------------------------------------------
    # Table cell flattening (prevent multi-line Markdown table cells)
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_table_cells(html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Flatten block-level content inside ``<td>`` and ``<th>`` elements.

        Markdown tables require each row to be a single line.  Block
        elements (``<p>``, ``<div>``) and ``<br>`` tags inside table cells
        produce line breaks that shatter the table structure during
        conversion.  This pre-processing step:

        * Replaces ``<br>`` tags with a space.
        * Unwraps ``<p>`` and ``<div>`` wrappers (keeps inner content).
        """
        soup, stringify = ContentExtractor._coerce_soup(html)
        cells = soup.find_all(["td", "th"])
        if not cells:
            return html
        modified = False
        for cell in cells:
            for br in cell.find_all("br"):
                br.insert_before(" ")
                br.unwrap()
                modified = True
            for tag in cell.find_all(list(_TABLE_CELL_BLOCK_TAGS)):
                tag.unwrap()
                modified = True
        if not modified:
            return html
        return ContentExtractor._return_html_or_soup(soup, stringify)

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
        """Normalize pipe-delimited blocks into valid Markdown tables.

        Fixes common issues produced by HTML-to-Markdown converters when
        the original HTML uses ``colspan`` / ``rowspan``:

        * Missing ``| --- |`` separator after the header row.
        * Inconsistent leading / trailing pipes.
        * Double pipes (``||``) representing empty cells.
        * Rows with fewer columns than the header (padded with empty cells).
        """
        lines = text.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if _PIPE_LINE_RE.match(line):
                block: list[str] = []
                while i < len(lines) and _PIPE_LINE_RE.match(lines[i]):
                    block.append(lines[i])
                    i += 1
                result.extend(ContentExtractor._normalize_table_block(block))
            else:
                result.append(line)
                i += 1
        return "\n".join(result)

    @staticmethod
    def _normalize_table_block(block: list[str]) -> list[str]:
        """Turn a block of pipe-delimited lines into a well-formed Markdown table."""
        if len(block) < 2:
            return block

        has_separator = bool(_TABLE_SEPARATOR_RE.match(block[1]))

        rows_to_parse = [block[0]] + block[2:] if has_separator else list(block)

        parsed: list[list[str]] = []
        for row in rows_to_parse:
            expanded = row
            while "||" in expanded:
                expanded = expanded.replace("||", "| |")
            expanded = expanded.strip()
            if not expanded.startswith("|"):
                expanded = "| " + expanded
            if not expanded.endswith("|"):
                expanded = expanded + " |"
            cells = [c.strip() for c in expanded.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            parsed.append(cells)

        max_cols = max(len(cells) for cells in parsed)
        if max_cols < 1:
            return block

        for cells in parsed:
            while len(cells) < max_cols:
                cells.append("")

        out: list[str] = []
        for cells in parsed:
            out.append("| " + " | ".join(cells) + " |")
        sep_row = "| " + " | ".join("---" for _ in range(max_cols)) + " |"
        out.insert(1, sep_row)
        return out

    def _filter_tags(self, html: _HtmlOrSoup) -> _HtmlOrSoup:
        """Remove or keep only specified HTML tags using simple parsing."""
        from html.parser import HTMLParser
        from io import StringIO

        if not self.page_config.include_only_tags and not self.page_config.exclude_tags:
            return html

        if isinstance(html, BeautifulSoup):
            include_only = [t.lower() for t in self.page_config.include_only_tags]
            exclude = [t.lower() for t in self.page_config.exclude_tags]
            if exclude:
                for tag in html.find_all(exclude):
                    tag.decompose()
                return html
            included = [
                tag
                for tag in html.find_all(include_only)
                if not any(
                    parent.name in include_only for parent in tag.parents if isinstance(parent, Tag)
                )
            ]
            included = [tag.extract() for tag in included]
            html.clear()
            for tag in included:
                html.append(tag)
            return html

        class TagFilter(HTMLParser):
            def __init__(self, include_only: list[str], exclude: list[str]) -> None:
                super().__init__()
                self.include_only = [t.lower() for t in include_only]
                self.exclude = [t.lower() for t in exclude]
                self.output = StringIO()
                self._skip_depth = 0
                self._include_depth = 0 if include_only else 1  # 1 = always include

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                tag_lower = tag.lower()
                if self.exclude and tag_lower in self.exclude:
                    self._skip_depth += 1
                    return
                if self.include_only and tag_lower in self.include_only:
                    self._include_depth += 1
                if self._skip_depth == 0 and self._include_depth > 0:
                    attr_str = "".join(f' {k}="{v}"' if v else f" {k}" for k, v in attrs)
                    self.output.write(f"<{tag}{attr_str}>")

            def handle_endtag(self, tag: str) -> None:
                tag_lower = tag.lower()
                if self.exclude and tag_lower in self.exclude:
                    self._skip_depth = max(0, self._skip_depth - 1)
                    return
                if self._skip_depth == 0 and self._include_depth > 0:
                    self.output.write(f"</{tag}>")
                if self.include_only and tag_lower in self.include_only:
                    self._include_depth = max(0, self._include_depth - 1)

            def handle_data(self, data: str) -> None:
                if self._skip_depth == 0 and self._include_depth > 0:
                    self.output.write(data)

        parser = TagFilter(
            include_only=self.page_config.include_only_tags,
            exclude=self.page_config.exclude_tags,
        )
        parser.feed(html)
        return parser.output.getvalue()

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
        """Post-process extracted Markdown for readability.

        Applies a chain of safe transforms:

        0. Strip leaked template / framework variables.
        1. Collapse 3+ consecutive blank lines into one.
        2. Deduplicate consecutive identical paragraphs.
        3. Reformat ``---``-separated product items into structured bullets.
        4. Compact product-listing blocks (name + price pairs) into bullet lists.
        5. Promote standalone short labels followed by content to headings.
        6. Compact runs of short standalone paragraphs into bullet lists.
        """
        text = _UNICODE_LINE_SEP_RE.sub("\n", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _LITERAL_CRLF_RE.sub("\n", text)
        text = _CMS_ATTR_JUNK_RE.sub("", text)
        text = ContentExtractor._strip_template_variables(text)
        text = ContentExtractor._collapse_blank_lines(text)
        text = ContentExtractor._dedup_paragraphs(text)
        text = ContentExtractor._reformat_separated_items(text)
        text = ContentExtractor._compact_product_listings(text)
        text = ContentExtractor._promote_section_labels(text)
        text = ContentExtractor._compact_short_paragraphs(text)
        return text

    # Patterns matching leaked SPA / OutSystems template variables.
    _TEMPLATE_VAR_RE = re.compile(
        r"^[-*]?\s*"
        r"(?:"
        r"(?:Var_|In_|TrueVar_|FalseVar_)\w+"
        r"|PayLaterOptionList\.\w+"
        r"|(?:Var_|In_)?\w*(?:ErrorCode|Error|MaxMonthOfInstallment"
        r"|PayLaterStatus|IsEligible|IsProcessing|BNPLErrorCode)"
        r"|NumberOfMonths"
        r"|isOutOfStock"
        r")\s*[:.].*$",
        re.IGNORECASE,
    )
    _CONCATENATED_VARS_RE = re.compile(
        r"(?:Var_|In_|True|False)\w+:.*(?:Var_|In_|True|False)\w+:",
        re.IGNORECASE,
    )

    @staticmethod
    def _strip_template_variables(text: str) -> str:
        """Remove lines that look like leaked SPA template variables.

        Targets known patterns from OutSystems and similar frameworks:
        ``Var_*``, ``In_*``, ``PayLaterOptionList.*``, ``isOutOfStock``,
        concatenated variable dumps, etc.
        """
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue
            if ContentExtractor._TEMPLATE_VAR_RE.match(stripped):
                continue
            if ContentExtractor._CONCATENATED_VARS_RE.search(stripped):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def _collapse_blank_lines(text: str) -> str:
        """Replace runs of 3+ blank lines with a single blank line."""
        return re.sub(r"\n{3,}", "\n\n", text)

    # ------------------------------------------------------------------
    # Separated-item reformatter (product cards split by ---)
    # ------------------------------------------------------------------

    # Shared patterns for product field classification
    _MONTHLY_PRICE_RE = re.compile(
        r"^(?:from\s+)?\$[\d,]+(?:\.\d{2})?/mth$",
        re.IGNORECASE,
    )
    _OUTRIGHT_PRICE_RE = re.compile(
        r"^(?:or\s*)?(?:~~)?\$\$?[\d,]+(?:\.\d{2})?(?:~~)?"
        r"(?:\$\$?[\d,]+(?:\.\d{2})?)?$",
        re.IGNORECASE,
    )
    _OFFERS_RE = re.compile(r"^\d+\s+offers?\s+available$", re.IGNORECASE)
    _BADGE_KEYWORDS = re.compile(
        r"^(?:Preorder|Pre-order|New|LNY\s+Offers?|Exclusive\s+Bundle|"
        r"Limited[- ]time\s+only|StarHub\s+[Ee]xclusive|PWP\s+Offers?|"
        r"Wi-Fi\s+Only|eSIM\s+Exclusive|Trending\s+Brands|Best\s+value"
        r"(?:\s+with\s+device)?|Best\s+Deal|Trade[- ]in\s+Bonus|Top\s+Seller)$",
        re.IGNORECASE,
    )
    _UI_ACTION_RE = re.compile(
        r"^(?:Compare|Compare\s+selected\s+products|Add\s+to\s+cart|"
        r"Add\s+to\s+bag|Buy\s+now|Select\s+options|View\s+details|Shop\s+now)$",
        re.IGNORECASE,
    )
    _MORE_LINK_RE = re.compile(rf"^\[{re.escape(_WRAPPER_LINK_LABEL)}\]\((.+)\)$")

    @staticmethod
    def _reformat_separated_items(text: str) -> str:
        """Reformat ``---``-separated product sections into structured bullets.

        Only fires when the text contains at least 3 ``---`` separators
        (indicating ``separate_items`` was active).  Each section is parsed
        for product fields: name, monthly price, outright price, badges,
        and offer count.  Successfully-parsed sections become::

            - **Galaxy S26 Ultra 5G**
              from $76.16/mth · or ~~$2,128.00~~ $1,828.00
              Preorder · 15 offers available

        Sections that don't look like products pass through unchanged.
        """
        # Split on --- lines preserving them as delimiters
        sections: list[str] = []
        current: list[str] = []
        for line in text.split("\n"):
            if _MD_HORIZONTAL_RULE_RE.match(line.strip()):
                sections.append("\n".join(current))
                current = []
            else:
                current.append(line)
        sections.append("\n".join(current))

        # Need at least 3 separators (4 sections) to activate
        if len(sections) < _MIN_SEPARATED_SECTIONS:
            return text

        # Try to reformat each section
        reformatted: list[str] = []
        product_count = 0
        for section in sections:
            parsed = ContentExtractor._parse_product_section(section)
            if parsed is not None:
                product_count += 1
                reformatted.append(parsed)
            else:
                reformatted.append(section)

        # Only use reformatted output if we found enough products
        if product_count < _MIN_PRODUCT_ENTRIES:
            return text

        return _ITEM_SEPARATOR_MD.join(reformatted)

    @staticmethod
    def _parse_product_section(section: str) -> str | None:
        """Try to parse a single ``---``-delimited section as a product entry.

        Returns a formatted bullet string on success, or ``None`` if the
        section does not look like a product listing.
        """
        lines = [ln.strip() for ln in section.strip().split("\n") if ln.strip()]
        if not lines:
            return None

        name = None
        monthly = None
        outright = None
        badges: list[str] = []
        offers = None
        unclassified: list[str] = []

        more_link = None
        for line in lines:
            # Strip leading "- " from list items produced by earlier transforms
            clean = re.sub(r"^[-*]\s+", "", line)
            if ContentExtractor._MONTHLY_PRICE_RE.match(clean):
                monthly = clean
            elif ContentExtractor._OUTRIGHT_PRICE_RE.match(clean):
                outright = clean
            elif ContentExtractor._OFFERS_RE.match(clean):
                offers = clean
            elif ContentExtractor._BADGE_KEYWORDS.match(clean):
                badges.append(clean)
            elif ContentExtractor._UI_ACTION_RE.match(clean):
                continue
            elif clean.lower() == "from":
                # Standalone "from" — will be merged with price later
                continue
            elif ContentExtractor._MORE_LINK_RE.match(clean):
                more_link = clean
            else:
                unclassified.append(clean)

        if not monthly and not outright:
            return None

        # Pick the product name: prefer the last short line (product names
        # are short and sit right before the price; long banner/promo text
        # appears at the top of the block).
        if unclassified:
            short_candidates = [u for u in unclassified if len(u) <= _MAX_PRODUCT_NAME_LEN]
            name = short_candidates[-1] if short_candidates else max(unclassified, key=len)
            unclassified = [u for u in unclassified if u != name]
        else:
            return None

        # Build the formatted output
        result_lines = [f"- **{name}**"]

        # Price line
        price_parts = []
        if monthly:
            price_parts.append(monthly)
        if outright:
            # Normalize outright price display
            price_parts.append(ContentExtractor._format_outright_price(outright))
        if price_parts:
            result_lines.append("  " + " · ".join(price_parts))

        # Badges + offers line
        badge_parts = list(badges)
        if offers:
            badge_parts.append(offers)
        # Add remaining short unclassified lines as badges
        for u in unclassified:
            if len(u) < _MAX_BADGE_LINE_LEN:
                badge_parts.append(u)
        if badge_parts:
            result_lines.append("  " + " · ".join(badge_parts))

        # Append wrapper-link reference (_WRAPPER_LINK_LABEL) if present
        if more_link:
            result_lines.append("  " + more_link)

        return "\n".join(result_lines)

    @staticmethod
    def _format_outright_price(price: str) -> str:
        """Normalize outright price strings for display.

        Converts ``or$2,128.00$1,828.00`` → ``or ~~$2,128.00~~ $1,828.00``
        and ``or$$1,499.00`` → ``or $1,499.00``.
        """
        # Already has strikethrough from _preserve_strikethrough
        if "~~" in price:
            return re.sub(r"^or(?=\S)", "or ", price)

        # Double-dollar from Markdown escaping: or$$1,499.00 → or $1,499.00
        m = re.match(r"^(or\s*)\$\$(\d[\d,]*(?:\.\d{2})?)$", price)
        if m:
            return f"or ${m.group(2)}"

        # Two concatenated prices: or$2,128.00$1,828.00 → or ~~$2,128.00~~ $1,828.00
        m = re.match(
            r"^(or\s*)?\$(\d[\d,]*(?:\.\d{2})?)\$(\d[\d,]*(?:\.\d{2})?)$",
            price,
        )
        if m:
            prefix = "or " if m.group(1) else ""
            return f"{prefix}~~${m.group(2)}~~ ${m.group(3)}"

        return re.sub(r"^or(?=\$)", "or ", price)

    @staticmethod
    def _compact_product_listings(text: str) -> str:
        """Detect repeated name→price sequences and reformat as bullet lists.

        A *product entry* is one or more non-blank, non-price, non-heading
        lines (the name / description) followed by exactly one price line
        matching ``$XX.XX`` (with optional ``from`` prefix).  Short lines
        (< 80 chars) adjacent to a product entry that don't look like a
        product name themselves are kept as indented sub-text (badges like
        "New", "3 offers available", promotional blurbs, etc.).

        The transform only fires when **3 or more** consecutive product
        entries are found, to avoid false positives on article pages that
        mention prices incidentally.
        """
        lines = text.split("\n")
        result: list[str] = []
        i = 0

        while i < len(lines):
            # Try to collect a run of product entries starting here
            entries: list[dict] = []
            j = i
            while j < len(lines):
                entry, j = ContentExtractor._try_parse_product_entry(
                    lines,
                    j,
                    _PRICE_LINE_RE,
                    _MD_HEADING_LINE_RE,
                    _MD_HORIZONTAL_RULE_RE,
                )
                if entry is None:
                    break
                entries.append(entry)

            if len(entries) >= _MIN_PRODUCT_ENTRIES:
                for entry in entries:
                    result.append(f"- **{entry['name']}** — {entry['price']}")
                    for badge in entry["badges"]:
                        result.append(f"  {badge}")
                i = j
            else:
                result.append(lines[i])
                i += 1

        return "\n".join(result)

    @staticmethod
    def _try_parse_product_entry(
        lines: list[str],
        start: int,
        price_re: re.Pattern[str],
        heading_re: re.Pattern[str],
        hr_re: re.Pattern[str],
    ) -> tuple[dict | None, int]:
        """Try to parse a single product entry (badges + name + price) at *start*.

        Returns ``(entry_dict, next_index)`` on success, or
        ``(None, start)`` if the lines at *start* don't form a product entry.
        """
        i = start
        # Skip blank lines between entries
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        if i >= len(lines):
            return None, start

        # Collect all non-blank, non-price, non-heading, non-hr content lines.
        # Blank lines between content lines are allowed (badges and names are
        # often separated by blank lines in the extracted Markdown).
        content_lines: list[str] = []
        j = i
        while j < len(lines):
            line = lines[j].strip()
            if not line:
                # Look ahead past blanks for the next non-blank line
                k = j
                while k < len(lines) and lines[k].strip() == "":
                    k += 1
                if k < len(lines) and price_re.match(lines[k].strip()):
                    # Blanks before a price — stop collecting content
                    break
                if k >= len(lines):
                    break
                nxt = lines[k].strip()
                if heading_re.match(nxt) or hr_re.match(nxt):
                    break
                # Otherwise skip blanks and continue collecting
                j = k
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            # Skip UI action labels and wrapper-link references (_WRAPPER_LINK_LABEL).
            if ContentExtractor._UI_ACTION_RE.match(line):
                j += 1
                continue
            if ContentExtractor._MORE_LINK_RE.match(line):
                j += 1
                continue
            content_lines.append(line)
            j += 1

        if not content_lines:
            return None, start

        # If the last content line is a standalone "from", remove it so it
        # doesn't taint the product name. It will be prepended to the price.
        from_prefix = ""
        if content_lines and content_lines[-1].lower() == "from":
            from_prefix = "from "
            content_lines.pop()
        if not content_lines:
            return None, start

        # Skip blank lines between content and price
        while j < len(lines) and lines[j].strip() == "":
            j += 1

        if j >= len(lines):
            return None, start

        # Expect a price line
        price_line = lines[j].strip()
        if not price_re.match(price_line):
            return None, start
        if from_prefix and not price_line.lower().startswith("from"):
            price_line = from_prefix + price_line
        if re.match(r"^or\s*\$", price_line, re.IGNORECASE):
            price_line = ContentExtractor._format_outright_price(price_line)
        j += 1

        # Collect additional price lines (e.g. outright prices like
        # "or$2,128.00$1,828.00" or "or$$1,499.00") that belong to the
        # same product.  These appear right after the monthly price.
        extra_prices: list[str] = []
        while j < len(lines):
            k = j
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k >= len(lines):
                break
            candidate = lines[k].strip()
            if price_re.match(candidate) and re.match(r"(?:or\s*)", candidate, re.IGNORECASE):
                extra_prices.append(
                    ContentExtractor._format_outright_price(candidate),
                )
                j = k + 1
            else:
                break

        # Split content_lines into badges (before name) and the name itself.
        # The last content line (or group of long lines) is the name;
        # short preceding lines that match known badge patterns are pre-badges.
        pre_badges: list[str] = []
        name_parts: list[str] = list(content_lines)

        # Peel off leading lines that look like badges (known patterns or
        # very short generic text, but NOT product-name-like text containing
        # alphanumeric model identifiers).
        while len(name_parts) > 1:
            candidate = name_parts[0]
            if ContentExtractor._BADGE_KEYWORDS.match(candidate) or (
                candidate.endswith("!") and len(candidate) < 80
            ):
                pre_badges.append(name_parts.pop(0))
            else:
                break

        # Collect post-badges: short lines after price (offers, promo text).
        # Stop if the line looks like it could be the next product name
        # (i.e. it's followed by a price line within a few lines).
        post_badges: list[str] = []
        while j < len(lines):
            line = lines[j].strip()
            if not line:
                j += 1
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            # Known badge keywords are pre-badges for the next product.
            if ContentExtractor._BADGE_KEYWORDS.match(line):
                break
            # Peek ahead: if a price follows this line (skipping blanks),
            # this line is the next product name, not a badge.
            k = j + 1
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k < len(lines):
                nxt = lines[k].strip()
                if price_re.match(nxt):
                    break
                # Handle standalone "from" → price pattern
                if nxt.lower() == "from":
                    m = k + 1
                    while m < len(lines) and lines[m].strip() == "":
                        m += 1
                    if m < len(lines) and price_re.match(lines[m].strip()):
                        break
            if len(line) < _MAX_PRODUCT_NAME_LEN and (
                len(line) < _BADGE_SHORT_LINE_THRESHOLD or line.endswith("!")
            ):
                post_badges.append(line)
                j += 1
            else:
                break

        name = " ".join(name_parts)
        # Combine all price components into a single display string
        full_price = price_line
        if extra_prices:
            full_price = full_price + " · " + " · ".join(extra_prices)
        return {
            "name": name,
            "price": full_price,
            "badges": pre_badges + post_badges,
        }, j

    @staticmethod
    def _dedup_paragraphs(text: str) -> str:
        """Remove consecutive duplicate paragraphs (separated by blank lines)."""
        paragraphs = _PARAGRAPH_SPLIT_2_RE.split(text)
        deduped: list[str] = []
        for para in paragraphs:
            if not deduped or para.strip() != deduped[-1].strip():
                deduped.append(para)
        return "\n\n".join(deduped)

    @staticmethod
    def _compact_short_paragraphs(text: str) -> str:
        """Convert runs of 3+ short single-line paragraphs into bullet lists.

        Sequences of short standalone lines separated by blank lines
        (typical of CSS-layout content losing its visual grouping) are
        collapsed into ``- item`` bullet lists.  Headings, horizontal
        rules, existing list items, and multi-line paragraphs are left
        untouched and act as boundaries for the runs.
        """
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
        max_len = _MAX_SHORT_PARAGRAPH_LEN

        result: list[str] = []
        run: list[str] = []

        def flush_run() -> None:
            if len(run) >= 3:
                for item in run:
                    result.append(f"- {item}")
            else:
                for item in run:
                    result.append(item)
            run.clear()

        for para in paragraphs:
            stripped = para.strip()
            is_single_line = "\n" not in stripped
            is_short = len(stripped) <= max_len
            is_special = (
                _MD_HEADING_LINE_RE.match(stripped)
                or _MD_HORIZONTAL_RULE_RE.match(stripped)
                or _MD_LIST_ITEM_RE.match(stripped)
                or not stripped
            )

            if is_single_line and is_short and not is_special:
                run.append(stripped)
            else:
                flush_run()
                result.append(para)

        flush_run()
        return "\n\n".join(result)

    # ------------------------------------------------------------------
    # Coverage check
    # ------------------------------------------------------------------

    @staticmethod
    def _visible_text_length(html: str) -> int:
        """Approximate the length of human-visible text in HTML."""
        soup = BeautifulSoup(html, _HTML_PARSER)
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        return len(soup.get_text(separator=" ", strip=True))

    # ------------------------------------------------------------------
    # FAQ formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_faq_questions(text: str) -> str:
        """Promote FAQ question lines to ``###`` Markdown headings.

        Single-line paragraphs that end with ``?`` (and are not already
        headings or list items) are converted to level-3 headings so that
        questions stand out visually from their answers.
        """
        max_len = _MAX_FAQ_QUESTION_LEN

        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
        result: list[str] = []
        for para in paragraphs:
            stripped = para.strip()
            is_single_line = "\n" not in stripped
            if (
                is_single_line
                and stripped.endswith("?")
                and len(stripped) <= max_len
                and not _MD_HEADING_LINE_RE.match(stripped)
                and not _MD_LIST_ITEM_RE.match(stripped)
            ):
                result.append(f"### {stripped}")
            else:
                result.append(para)
        return "\n\n".join(result)

    # ------------------------------------------------------------------
    # Supplementary section recovery (FAQ, accordion, Q&A)
    # ------------------------------------------------------------------

    _SUPP_CLASS_KEYWORDS = re.compile(
        r"faq|frequently.asked|accordion|q.and.a|questions?.and.answers?",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_supplementary_sections(html: str) -> list[str]:
        """Detect FAQ / accordion sections that trafilatura would strip.

        Returns a list of Markdown fragments (one per detected section).
        Uses four heuristics, deduplicates by element identity, and
        converts each matched subtree to Markdown via *markdownify*.
        """
        soup = BeautifulSoup(html, _HTML_PARSER)
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
        for el in soup.find_all(attrs={"itemtype": re.compile(r"FAQPage", re.I)}):
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
    def _extract_product_header(html: str) -> dict | None:
        """Extract product metadata from structured data in the HTML.

        Checks two sources in priority order:

        1. **JSON-LD** ``<script type="application/ld+json">`` blocks
           with ``@type: "Product"``.
        2. **Open Graph** ``<meta>`` tags (``og:title``,
           ``product:price:amount``, ``product:brand``).

        Returns a dict with keys ``name``, ``brand``, ``price``,
        ``high_price`` (all optional strings), or ``None`` when the
        page does not appear to be a product detail page.
        """
        result = ContentExtractor._product_from_jsonld(html)
        if result:
            return result
        result = ContentExtractor._product_from_og(html)
        if result:
            return result
        return ContentExtractor._product_from_dom(html)

    @staticmethod
    def _product_from_jsonld(html: str) -> dict | None:
        """Parse JSON-LD blocks for a Product entity."""
        for match in _JSON_LD_SCRIPT_RE.finditer(html):
            try:
                data = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                continue
            product = ContentExtractor._find_product_in_jsonld(data)
            if product:
                return product
        return None

    @staticmethod
    def _find_product_in_jsonld(data: object) -> dict | None:
        """Recursively search for a Product entity in parsed JSON-LD."""
        if isinstance(data, list):
            for item in data:
                result = ContentExtractor._find_product_in_jsonld(item)
                if result:
                    return result
            return None
        if not isinstance(data, dict):
            return None
        ld_type = data.get("@type", "")
        if isinstance(ld_type, list):
            ld_type = " ".join(ld_type)
        if "Product" not in ld_type:
            # Check @graph
            if "@graph" in data:
                return ContentExtractor._find_product_in_jsonld(data["@graph"])
            return None

        name = data.get("name", "")
        brand = ""
        brand_obj = data.get("brand")
        if isinstance(brand_obj, dict):
            brand = brand_obj.get("name", "")
        elif isinstance(brand_obj, str):
            brand = brand_obj

        price = ""
        high_price = ""
        offers = data.get("offers")
        if isinstance(offers, dict):
            price = str(offers.get("price", offers.get("lowPrice", "")))
            high_price = str(offers.get("highPrice", ""))
        elif isinstance(offers, list) and offers:
            first = offers[0] if isinstance(offers[0], dict) else {}
            price = str(first.get("price", first.get("lowPrice", "")))
            high_price = str(first.get("highPrice", ""))

        if not name:
            return None
        return {
            "name": name,
            "brand": brand,
            "price": price,
            "high_price": high_price,
        }

    @staticmethod
    def _product_from_og(html: str) -> dict | None:
        """Detect a product page from Open Graph meta tags.

        Only returns a result when ``product:price:amount`` is present,
        preventing false positives on listing / article pages.
        """

        def _og(prop: str) -> str:
            pat = (
                rf'<meta[^>]+property=["\'](?:og:)?{re.escape(prop)}["\']'
                rf'[^>]+content=["\']([^"\']+)["\']'
            )
            m = re.search(pat, html, re.IGNORECASE)
            if not m:
                pat = (
                    rf'<meta[^>]+content=["\']([^"\']+)["\']'
                    rf'[^>]+property=["\'](?:og:)?{re.escape(prop)}["\']'
                )
                m = re.search(pat, html, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        price = _og("product:price:amount")
        if not price:
            return None
        name = _og("title")
        brand = _og("product:brand")
        return {"name": name, "brand": brand, "price": price, "high_price": ""}

    @staticmethod
    def _product_from_dom(html: str) -> dict | None:
        """Fall back to scanning the rendered DOM for product metadata.

        Looks for a strikethrough price (``<del>``, ``<s>``, ``<strike>``)
        which strongly signals a product detail page with a discounted
        price.  Extracts the product name from the nearest heading and
        the brand from the URL path when possible.

        Returns ``None`` when no strikethrough price is found, avoiding
        false positives on listing and article pages.
        """
        soup = BeautifulSoup(html, "html.parser")
        # Remove non-visible content.
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()

        # Look for a strikethrough element containing a price.
        strike_tag = None
        for tag_name in ("del", "s", "strike"):
            for tag in soup.find_all(tag_name):
                text = tag.get_text(strip=True)
                if _PRICE_DETECT_RE.search(text):
                    strike_tag = tag
                    break
            if strike_tag:
                break

        if not strike_tag:
            return None

        high_price_match = _PRICE_DETECT_RE.search(strike_tag.get_text(strip=True))
        high_price = high_price_match.group(0).lstrip("$") if high_price_match else ""

        # Current/discounted price: next sibling text or parent text after the strike.
        price = ""
        parent = strike_tag.parent
        if parent:
            full_text = parent.get_text(" ", strip=True)
            prices = _PRICE_DETECT_RE.findall(full_text)
            # The last price that differs from high_price is the current price.
            for p in prices:
                if p.lstrip("$") != high_price:
                    price = p.lstrip("$")

        # Product name: walk up DOM to find the nearest heading.
        name = ""
        node = strike_tag
        for _ in range(_MAX_DOM_DEPTH):
            node = node.parent
            if node is None:
                break
            heading = node.find(["h1", "h2", "h3"])
            if heading:
                name = heading.get_text(" ", strip=True)
                break

        # Brand: try to extract from URL in a <link rel="canonical"> or <meta og:url>.
        brand = ""
        canonical = soup.find("link", rel="canonical")
        page_url = str(canonical["href"]) if canonical and canonical.get("href") else ""
        if not page_url:
            og_url = soup.find("meta", attrs={"property": "og:url"})
            page_url = str(og_url["content"]) if og_url and og_url.get("content") else ""
        if page_url:
            parts = urlparse(page_url).path.strip("/").split("/")
            # Heuristic: brand is the second-to-last segment before the product slug.
            if len(parts) >= 2:
                candidate = parts[-2].replace("-", " ").title()
                if candidate.lower() not in _BRAND_EXCLUSION_KEYWORDS:
                    brand = candidate

        if not name and not price and not high_price:
            return None
        return {
            "name": name,
            "brand": brand,
            "price": price,
            "high_price": high_price,
        }

    @staticmethod
    def _format_product_price(product: dict) -> str:
        """Build a human-readable price string from product metadata."""
        price = product.get("price", "")
        high_price = product.get("high_price", "")
        if not price and not high_price:
            return ""
        if high_price and price and high_price != price:
            return f"~~${high_price}~~ ${price}"
        if price:
            return f"${price}"
        return ""

    # ------------------------------------------------------------------
    # Section-label promotion
    # ------------------------------------------------------------------

    @staticmethod
    def _promote_section_labels(text: str) -> str:
        """Promote standalone short labels followed by content to headings.

        Detects short single-line paragraphs (e.g. ``Front camera``,
        ``Battery Life``) that are immediately followed by bullet lists
        or substantial content blocks, and converts them to ``###``
        headings.  This recovers structure lost when CSS-layout pages
        are flattened by content extractors.

        Guards against false positives:

        * Labels matching price patterns, badge keywords, or existing
          headings / list items are skipped.
        * The label must be followed by at least 1 bullet (``- …``) or
          a paragraph of ≥ 80 characters.
        """
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)

        result: list[str] = []
        i = 0
        while i < len(paragraphs):
            stripped = paragraphs[i].strip()
            is_single_line = "\n" not in stripped

            if (
                is_single_line
                and 0 < len(stripped) <= _MAX_SECTION_LABEL_LEN
                and not _MD_HEADING_LINE_RE.match(stripped)
                and not _MD_HORIZONTAL_RULE_RE.match(stripped)
                and not _MD_LIST_ITEM_RE.match(stripped)
                and not ContentExtractor._MONTHLY_PRICE_RE.match(stripped)
                and not ContentExtractor._OUTRIGHT_PRICE_RE.match(stripped)
                and not ContentExtractor._OFFERS_RE.match(stripped)
                and not ContentExtractor._BADGE_KEYWORDS.match(stripped)
                and not stripped.startswith("**")
                and i + 1 < len(paragraphs)
            ):
                # Check if the next paragraph is a bullet list or long block.
                nxt = paragraphs[i + 1].strip()
                next_has_bullets = any(
                    _MD_LIST_ITEM_RE.match(ln.strip()) for ln in nxt.split("\n") if ln.strip()
                )
                next_is_substantial = len(nxt) >= _SUBSTANTIAL_CONTENT_LEN

                if next_has_bullets or next_is_substantial:
                    result.append(f"### {stripped}")
                    i += 1
                    continue

            result.append(paragraphs[i])
            i += 1

        return "\n\n".join(result)
