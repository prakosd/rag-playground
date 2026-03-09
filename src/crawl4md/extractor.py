"""ContentExtractor — converts crawled HTML to clean Markdown text."""

from __future__ import annotations

import json
import re
from collections import Counter
from urllib.parse import urlparse

import mdformat
import trafilatura
from bs4 import BeautifulSoup, Tag
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
        if self.page_config.extract_main_content:
            return self._extract_main_content(result)
        return self._extract_full_html(result)

    def _extract_main_content(self, result: CrawlResult) -> ExtractedPage:
        """Use trafilatura to extract the main body content.

        Falls back to markdownify when trafilatura captures less than
        ``_COVERAGE_THRESHOLD`` of the page's visible text.
        """
        html = result.html
        # Capture supplementary sections (e.g. FAQs) before trafilatura strips them.
        supplements = self._extract_supplementary_sections(html)
        html = self._preserve_strikethrough(html)
        if self.page_config.separate_items:
            html = self._insert_item_separators(html, use_sentinel=True)
        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            favor_recall=True,
        )
        md = self._fix_markdown_tables(extracted or "")
        if self.page_config.separate_items:
            md = md.replace(_ITEM_SENTINEL, "\n\n---\n\n")
        md = self._clean_markdown(md)

        # Fall back to markdownify when trafilatura captured too little.
        visible_len = self._visible_text_length(result.html)
        if visible_len > 0 and len(md.strip()) / visible_len < _COVERAGE_THRESHOLD:
            return self._extract_full_html(result)

        for fragment in supplements:
            formatted = self._format_faq_questions(fragment)
            cleaned = self._clean_markdown(formatted)
            if cleaned.strip():
                md = md.rstrip() + "\n\n---\n\n" + cleaned

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
                header_parts.append(f"Retail price: {price_display}")
            if header_parts:
                md = "\n\n".join(header_parts) + "\n\n" + md

        md = self._validate_markdown(md)

        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
        )

    def _extract_full_html(self, result: CrawlResult) -> ExtractedPage:
        """Use markdownify on the (optionally tag-filtered) HTML."""
        html = self._filter_tags(result.html)
        html = self._preserve_strikethrough(html)
        if self.page_config.separate_items:
            html = self._insert_item_separators(html, use_sentinel=False)
        md = markdownify(html, heading_style="ATX", strip=["img"], table_infer_header=True)
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
                header_parts.append(f"Retail price: {price_display}")
            if header_parts:
                md = "\n\n".join(header_parts) + "\n\n" + md

        md = self._validate_markdown(md)

        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
        )

    # ------------------------------------------------------------------
    # Strikethrough preservation
    # ------------------------------------------------------------------

    @staticmethod
    def _preserve_strikethrough(html: str) -> str:
        """Convert ``<del>``, ``<s>``, and ``<strike>`` tags to ``~~text~~``.

        Trafilatura silently drops these tags, losing the visual
        distinction between original and discounted prices (e.g.
        ``<del>$2,128.00</del>$1,828.00``).  By replacing them with
        Markdown strikethrough *before* extraction, the semantic is
        preserved in the final output.
        """
        return re.sub(
            r"<(del|s|strike)\b[^>]*>(.*?)</\1>",
            r"~~\2~~",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # ------------------------------------------------------------------
    # Item separation (structured product/card grouping)
    # ------------------------------------------------------------------

    def _insert_item_separators(self, html: str, *, use_sentinel: bool) -> str:
        """Insert separators between repeated structural items in the HTML.

        When *use_sentinel* is ``True`` (trafilatura mode), a ``<p>`` with
        a unique text sentinel is inserted because trafilatura strips
        ``<hr>`` elements.  When ``False`` (markdownify mode), a plain
        ``<hr>`` is used.

        If ``page_config.item_selector`` is set, that CSS selector
        identifies items directly.  Otherwise, auto-detection finds the
        largest group of repeated same-tag-and-class siblings.
        """
        soup = BeautifulSoup(html, "html.parser")

        if self.page_config.item_selector:
            items = soup.select(self.page_config.item_selector)
        else:
            items = self._find_repeated_items(soup)
            items = self._include_interstitial_siblings(items)

        if len(items) < 2:
            return html

        if use_sentinel:
            # Append sentinel as last child *inside* each item (except the
            # last) so it becomes part of the item's content subtree.
            # Trafilatura preserves inline text but may strip standalone
            # sibling elements sitting between items.
            for item in items[:-1]:
                sep = soup.new_tag("p")
                sep.string = _ITEM_SENTINEL
                item.append(sep)
        else:
            for item in reversed(items[1:]):
                sep = soup.new_tag("hr")
                item.insert_before(sep)

        return str(soup)

    @staticmethod
    def _find_repeated_items(soup: BeautifulSoup) -> list[Tag]:
        """Auto-detect the dominant group of repeated structural elements.

        Walks the DOM looking for parents whose direct children share the
        same ``(tag_name, frozenset_of_classes)`` signature.  Groups must
        have at least 3 members, each with at least 30 characters of text.
        The group with the highest ``count * avg_text_length`` score wins.

        Elements inside ``<nav>``, ``<header>``, ``<footer>`` are ignored
        to avoid picking up navigation links.
        """
        skip_parents = {"nav", "header", "footer"}
        min_text_len = 20
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
                if len(children) < 3:
                    continue
                # Filter: each child must have meaningful text
                qualified = [
                    c for c in children if len(c.get_text(strip=True)) >= min_text_len
                ]
                if len(qualified) < 3:
                    continue
                key = (id(parent), sig)
                groups[key] = qualified

        if not groups:
            return []

        # Score: count * average text length — favours large groups of content-rich items
        def score(items: list[Tag]) -> float:
            avg_len = sum(len(t.get_text(strip=True)) for t in items) / len(items)
            return len(items) * avg_len

        best = max(groups.values(), key=score)
        return best

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
        matched_indices = [
            i for i, sib in enumerate(siblings) if id(sib) in items_set
        ]
        if not matched_indices:
            return items

        first_idx, last_idx = matched_indices[0], matched_indices[-1]

        # Collect all siblings between first and last, including interstitials
        expanded: list[Tag] = []
        for i in range(first_idx, last_idx + 1):
            sib = siblings[i]
            if id(sib) in items_set:
                expanded.append(sib)
            elif len(sib.get_text(strip=True)) >= 20:
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
        pipe_line = re.compile(r"^\|?.+\|.+\|?\s*$")

        lines = text.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if pipe_line.match(line):
                block: list[str] = []
                while i < len(lines) and pipe_line.match(lines[i]):
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

        separator_re = re.compile(r"^\|?(\s*-{3,}\s*\|)+\s*-{3,}\s*\|?\s*$")
        has_separator = bool(separator_re.match(block[1]))

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

    def _filter_tags(self, html: str) -> str:
        """Remove or keep only specified HTML tags using simple parsing."""
        from html.parser import HTMLParser
        from io import StringIO

        if not self.page_config.include_only_tags and not self.page_config.exclude_tags:
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
                    attr_str = "".join(
                        f' {k}="{v}"' if v else f" {k}" for k, v in attrs
                    )
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
            formatted = mdformat.text(md, extensions=["gfm"])
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
        r"^(?:from\s+)?\$[\d,]+(?:\.\d{2})?/mth$", re.IGNORECASE,
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
        r"(?:\s+with\s+device)?)$",
        re.IGNORECASE,
    )

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
        hr_re = re.compile(r"^---+$")
        # Split on --- lines preserving them as delimiters
        sections: list[str] = []
        current: list[str] = []
        for line in text.split("\n"):
            if hr_re.match(line.strip()):
                sections.append("\n".join(current))
                current = []
            else:
                current.append(line)
        sections.append("\n".join(current))

        # Need at least 3 separators (4 sections) to activate
        if len(sections) < 4:
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
        if product_count < 3:
            return text

        return "\n\n---\n\n".join(reformatted)

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
            elif clean.lower() == "from":
                # Standalone "from" — will be merged with price later
                continue
            else:
                unclassified.append(clean)

        if not monthly and not outright:
            return None

        # Pick the product name: prefer the last short line (product names
        # are short and sit right before the price; long banner/promo text
        # appears at the top of the block).
        if unclassified:
            short_candidates = [u for u in unclassified if len(u) <= 80]
            if short_candidates:
                name = short_candidates[-1]
            else:
                name = max(unclassified, key=len)
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
            if len(u) < 60:
                badge_parts.append(u)
        if badge_parts:
            result_lines.append("  " + " · ".join(badge_parts))

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
            r"^(or\s*)?\$(\d[\d,]*(?:\.\d{2})?)\$(\d[\d,]*(?:\.\d{2})?)$", price,
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
        price_re = re.compile(
            r"^(?:from\s+)?(?:or\s*)?(?:~~)?\$\$?[\d,]+(?:\.\d{2})?(?:~~)?"
            r"(?:/mth)?(?:\$\$?[\d,]+(?:\.\d{2})?)?$"
        )
        heading_re = re.compile(r"^#{1,6}\s")
        hr_re = re.compile(r"^---+$")

        lines = text.split("\n")
        result: list[str] = []
        i = 0

        while i < len(lines):
            # Try to collect a run of product entries starting here
            entries: list[dict] = []
            j = i
            while j < len(lines):
                entry, j = ContentExtractor._try_parse_product_entry(
                    lines, j, price_re, heading_re, hr_re,
                )
                if entry is None:
                    break
                entries.append(entry)

            if len(entries) >= 3:
                # Emit as bullet list
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
            if ContentExtractor._BADGE_KEYWORDS.match(candidate):
                pre_badges.append(name_parts.pop(0))
            elif candidate.endswith("!") and len(candidate) < 80:
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
            if len(line) < 80 and (len(line) < 40 or line.endswith("!")):
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
        paragraphs = re.split(r"\n{2,}", text)
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
        paragraphs = re.split(r"\n\n+", text)
        heading_re = re.compile(r"^#{1,6}\s")
        hr_re = re.compile(r"^---+$")
        list_re = re.compile(r"^[-*+]\s")
        max_len = 120

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
                heading_re.match(stripped)
                or hr_re.match(stripped)
                or list_re.match(stripped)
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
        soup = BeautifulSoup(html, "html.parser")
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
        heading_re = re.compile(r"^#{1,6}\s")
        list_re = re.compile(r"^[-*+]\s")
        max_len = 200

        paragraphs = re.split(r"\n\n+", text)
        result: list[str] = []
        for para in paragraphs:
            stripped = para.strip()
            is_single_line = "\n" not in stripped
            if (
                is_single_line
                and stripped.endswith("?")
                and len(stripped) <= max_len
                and not heading_re.match(stripped)
                and not list_re.match(stripped)
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
        soup = BeautifulSoup(html, "html.parser")
        seen_ids: set[int] = set()
        sections: list[str] = []

        def _add(tag: Tag) -> None:
            tid = id(tag)
            if tid in seen_ids:
                return
            # Skip tiny fragments that are unlikely to be real content.
            if len(tag.get_text(strip=True)) < 30:
                return
            seen_ids.add(tid)
            # Also mark all descendants so later heuristics skip them.
            for desc in tag.find_all(True):
                seen_ids.add(id(desc))
            md = markdownify(str(tag), heading_style="ATX", strip=["img"])
            if md.strip():
                sections.append(md)

        # 1. Schema.org FAQPage structured data
        for el in soup.find_all(attrs={"itemtype": re.compile(r"FAQPage", re.I)}):
            if isinstance(el, Tag):
                _add(el)

        # 2. HTML5 <details>/<summary> groups (≥ 3 siblings)
        for parent in soup.find_all(True):
            details = [c for c in parent.children if isinstance(c, Tag) and c.name == "details"]
            if len(details) >= 3 and id(parent) not in seen_ids:
                _add(parent)

        # 3. CSS class / id keyword matching
        for el in soup.find_all(True):
            if id(el) in seen_ids:
                continue
            classes = " ".join(el.get("class", []))
            el_id = el.get("id", "") or ""
            if ContentExtractor._SUPP_CLASS_KEYWORDS.search(classes) or \
               ContentExtractor._SUPP_CLASS_KEYWORDS.search(el_id):
                _add(el)

        # 4. Heading (h2-h4) whose text mentions FAQ / Frequently Asked
        faq_heading_re = re.compile(r"\bfaq\b|frequently\s+asked", re.I)
        for heading in soup.find_all(re.compile(r"^h[2-4]$")):
            if id(heading) in seen_ids:
                continue
            if faq_heading_re.search(heading.get_text()):
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
        title_match = re.search(
            r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL,
        )
        title_text = title_match.group(1).strip() if title_match else ""

        if title_text and not ContentExtractor._GENERIC_TITLES.match(title_text):
            return title_text

        # 2. og:title meta tag
        og_match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if not og_match:
            og_match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                html,
                re.IGNORECASE,
            )
        if og_match:
            og_text = og_match.group(1).strip()
            if og_text and not ContentExtractor._GENERIC_TITLES.match(og_text):
                return og_text

        # 3. First <h1>
        h1_match = re.search(
            r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL,
        )
        if h1_match:
            # Strip inner HTML tags to get plain text.
            h1_text = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
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
        if not slug or len(slug) < 3 or slug.isdigit():
            return ""
        title = slug.replace("-", " ").replace("_", " ").strip()
        title = title.title()
        # Fix common tech abbreviations.
        title = ContentExtractor._SLUG_UPPER.sub(
            lambda m: m.group(1).upper(), title,
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
        for match in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        ):
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
        price_re = re.compile(r"\$[\d,]+(?:\.\d{2})?")
        strike_tag = None
        for tag_name in ("del", "s", "strike"):
            for tag in soup.find_all(tag_name):
                text = tag.get_text(strip=True)
                if price_re.search(text):
                    strike_tag = tag
                    break
            if strike_tag:
                break

        if not strike_tag:
            return None

        high_price_match = price_re.search(strike_tag.get_text(strip=True))
        high_price = high_price_match.group(0).lstrip("$") if high_price_match else ""

        # Current/discounted price: next sibling text or parent text after the strike.
        price = ""
        parent = strike_tag.parent
        if parent:
            full_text = parent.get_text(" ", strip=True)
            prices = price_re.findall(full_text)
            # The last price that differs from high_price is the current price.
            for p in prices:
                if p.lstrip("$") != high_price:
                    price = p.lstrip("$")

        # Product name: walk up DOM to find the nearest heading.
        name = ""
        node = strike_tag
        for _ in range(15):
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
                if candidate.lower() not in (
                    "devices", "mobile", "store", "personal",
                    "products", "shop", "buy",
                ):
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
        paragraphs = re.split(r"\n\n+", text)
        heading_re = re.compile(r"^#{1,6}\s")
        hr_re = re.compile(r"^---+$")
        list_re = re.compile(r"^[-*+]\s")
        max_label_len = 60

        result: list[str] = []
        i = 0
        while i < len(paragraphs):
            stripped = paragraphs[i].strip()
            is_single_line = "\n" not in stripped

            if (
                is_single_line
                and 0 < len(stripped) <= max_label_len
                and not heading_re.match(stripped)
                and not hr_re.match(stripped)
                and not list_re.match(stripped)
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
                    list_re.match(ln.strip())
                    for ln in nxt.split("\n")
                    if ln.strip()
                )
                next_is_substantial = len(nxt) >= 80

                if next_has_bullets or next_is_substantial:
                    result.append(f"### {stripped}")
                    i += 1
                    continue

            result.append(paragraphs[i])
            i += 1

        return "\n\n".join(result)
