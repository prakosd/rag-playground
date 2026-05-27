"""Markdown cleanup helpers for ContentExtractor."""

from __future__ import annotations

import re

from crawl4md._internal.html_preprocess import _WRAPPER_LINK_TEXT

__all__ = ["MarkdownPipeline"]

_ITEM_SEPARATOR_MD = "\n\n---\n\n"
_MAX_PRODUCT_NAME_LEN = 80
_MAX_BADGE_LINE_LEN = 60
_BADGE_SHORT_LINE_THRESHOLD = 40
_MIN_PRODUCT_ENTRIES = 3
_MIN_SEPARATED_SECTIONS = 4
_MAX_FAQ_QUESTION_LEN = 200
_MAX_SHORT_PARAGRAPH_LEN = 120
_SUBSTANTIAL_CONTENT_LEN = 80
_MAX_SECTION_LABEL_LEN = 60

_MD_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_MD_HORIZONTAL_RULE_RE = re.compile(r"^---+$")
_MD_LIST_ITEM_RE = re.compile(r"^[-*+]\s")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\n+")
_PARAGRAPH_SPLIT_2_RE = re.compile(r"\n{2,}")
_UNICODE_LINE_SEP_RE = re.compile("[\u2028\u2029]")
_CMS_ATTR_JUNK_RE = re.compile(
    r"(?:\\r\\n|\r\n|\r|\n)*"
    r'["\'}\]\)]*\}\}["\'>]*'
    r'(?:\s+[a-z][a-z\-]*="[^"]*")*'
    r"\s*>",
)
_LITERAL_CRLF_RE = re.compile(r"\\r\\n")
_PIPE_LINE_RE = re.compile(r"^\|?.+\|.+\|?\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?(\s*-{3,}\s*\|)+\s*-{3,}\s*\|?\s*$")
_PRICE_LINE_RE = re.compile(
    r"^(?:from\s+)?(?:or\s*)?(?:~~)?\$\$?[\d,]+(?:\.\d{2})?(?:~~)?"
    r"(?:/mth)?(?:\$\$?[\d,]+(?:\.\d{2})?)?$"
)
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
_MORE_LINK_RE = re.compile(rf"^\[{re.escape(_WRAPPER_LINK_TEXT)}\]\((.+)\)$")

_ProductEntry = dict[str, str | list[str]]


class MarkdownPipeline:
    @staticmethod
    def fix_markdown_tables(text: str) -> str:
        lines = text.split("\n")
        result: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if _PIPE_LINE_RE.match(line):
                block: list[str] = []
                while index < len(lines) and _PIPE_LINE_RE.match(lines[index]):
                    block.append(lines[index])
                    index += 1
                result.extend(MarkdownPipeline.normalize_table_block(block))
            else:
                result.append(line)
                index += 1
        return "\n".join(result)

    @staticmethod
    def normalize_table_block(block: list[str]) -> list[str]:
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
            cells = [cell.strip() for cell in expanded.split("|")]
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

        output: list[str] = []
        for cells in parsed:
            output.append("| " + " | ".join(cells) + " |")
        separator_row = "| " + " | ".join("---" for _ in range(max_cols)) + " |"
        output.insert(1, separator_row)
        return output

    @staticmethod
    def clean(text: str) -> str:
        text = _UNICODE_LINE_SEP_RE.sub("\n", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _LITERAL_CRLF_RE.sub("\n", text)
        text = _CMS_ATTR_JUNK_RE.sub("", text)
        text = MarkdownPipeline.strip_template_variables(text)
        text = MarkdownPipeline.collapse_blank_lines(text)
        text = MarkdownPipeline.dedup_paragraphs(text)
        text = MarkdownPipeline.reformat_separated_items(text)
        text = MarkdownPipeline.compact_product_listings(text)
        text = MarkdownPipeline.promote_section_labels(text)
        text = MarkdownPipeline.compact_short_paragraphs(text)
        return text

    @staticmethod
    def strip_template_variables(text: str) -> str:
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue
            if _TEMPLATE_VAR_RE.match(stripped):
                continue
            if _CONCATENATED_VARS_RE.search(stripped):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def collapse_blank_lines(text: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def reformat_separated_items(text: str) -> str:
        sections: list[str] = []
        current: list[str] = []
        for line in text.split("\n"):
            if _MD_HORIZONTAL_RULE_RE.match(line.strip()):
                sections.append("\n".join(current))
                current = []
            else:
                current.append(line)
        sections.append("\n".join(current))

        if len(sections) < _MIN_SEPARATED_SECTIONS:
            return text

        reformatted: list[str] = []
        product_count = 0
        for section in sections:
            parsed = MarkdownPipeline.parse_product_section(section)
            if parsed is not None:
                product_count += 1
                reformatted.append(parsed)
            else:
                reformatted.append(section)

        if product_count < _MIN_PRODUCT_ENTRIES:
            return text
        return _ITEM_SEPARATOR_MD.join(reformatted)

    @staticmethod
    def parse_product_section(section: str) -> str | None:
        lines = [line.strip() for line in section.strip().split("\n") if line.strip()]
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
            clean = re.sub(r"^[-*]\s+", "", line)
            if _MONTHLY_PRICE_RE.match(clean):
                monthly = clean
            elif _OUTRIGHT_PRICE_RE.match(clean):
                outright = clean
            elif _OFFERS_RE.match(clean):
                offers = clean
            elif _BADGE_KEYWORDS.match(clean):
                badges.append(clean)
            elif _UI_ACTION_RE.match(clean) or clean.lower() == "from":
                continue
            elif _MORE_LINK_RE.match(clean):
                more_link = clean
            else:
                unclassified.append(clean)

        if not monthly and not outright:
            return None
        if unclassified:
            short_candidates = [line for line in unclassified if len(line) <= _MAX_PRODUCT_NAME_LEN]
            name = short_candidates[-1] if short_candidates else max(unclassified, key=len)
            unclassified = [line for line in unclassified if line != name]
        else:
            return None

        result_lines = [f"- **{name}**"]
        price_parts = []
        if monthly:
            price_parts.append(monthly)
        if outright:
            price_parts.append(MarkdownPipeline.format_outright_price(outright))
        if price_parts:
            result_lines.append("  " + " · ".join(price_parts))

        badge_parts = list(badges)
        if offers:
            badge_parts.append(offers)
        for line in unclassified:
            if len(line) < _MAX_BADGE_LINE_LEN:
                badge_parts.append(line)
        if badge_parts:
            result_lines.append("  " + " · ".join(badge_parts))
        if more_link:
            result_lines.append("  " + more_link)
        return "\n".join(result_lines)

    @staticmethod
    def format_outright_price(price: str) -> str:
        if "~~" in price:
            return re.sub(r"^or(?=\S)", "or ", price)

        match = re.match(r"^(or\s*)\$\$(\d[\d,]*(?:\.\d{2})?)$", price)
        if match:
            return f"or ${match.group(2)}"

        match = re.match(
            r"^(or\s*)?\$(\d[\d,]*(?:\.\d{2})?)\$(\d[\d,]*(?:\.\d{2})?)$",
            price,
        )
        if match:
            prefix = "or " if match.group(1) else ""
            return f"{prefix}~~${match.group(2)}~~ ${match.group(3)}"

        return re.sub(r"^or(?=\$)", "or ", price)

    @staticmethod
    def compact_product_listings(text: str) -> str:
        lines = text.split("\n")
        result: list[str] = []
        index = 0

        while index < len(lines):
            entries: list[_ProductEntry] = []
            next_index = index
            while next_index < len(lines):
                entry, next_index = MarkdownPipeline.try_parse_product_entry(lines, next_index)
                if entry is None:
                    break
                entries.append(entry)

            if len(entries) >= _MIN_PRODUCT_ENTRIES:
                for entry in entries:
                    result.append(f"- **{entry['name']}** — {entry['price']}")
                    badges = entry["badges"]
                    if isinstance(badges, list):
                        for badge in badges:
                            result.append(f"  {badge}")
                index = next_index
            else:
                result.append(lines[index])
                index += 1

        return "\n".join(result)

    @staticmethod
    def try_parse_product_entry(
        lines: list[str],
        start: int,
        price_re: re.Pattern[str] = _PRICE_LINE_RE,
        heading_re: re.Pattern[str] = _MD_HEADING_LINE_RE,
        hr_re: re.Pattern[str] = _MD_HORIZONTAL_RULE_RE,
    ) -> tuple[_ProductEntry | None, int]:
        index = start
        while index < len(lines) and lines[index].strip() == "":
            index += 1
        if index >= len(lines):
            return None, start

        content_lines: list[str] = []
        next_index = index
        while next_index < len(lines):
            line = lines[next_index].strip()
            if not line:
                lookahead_index = next_index
                while lookahead_index < len(lines) and lines[lookahead_index].strip() == "":
                    lookahead_index += 1
                if lookahead_index < len(lines) and price_re.match(lines[lookahead_index].strip()):
                    break
                if lookahead_index >= len(lines):
                    break
                next_line = lines[lookahead_index].strip()
                if heading_re.match(next_line) or hr_re.match(next_line):
                    break
                next_index = lookahead_index
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            if _UI_ACTION_RE.match(line) or _MORE_LINK_RE.match(line):
                next_index += 1
                continue
            content_lines.append(line)
            next_index += 1

        if not content_lines:
            return None, start

        from_prefix = ""
        if content_lines and content_lines[-1].lower() == "from":
            from_prefix = "from "
            content_lines.pop()
        if not content_lines:
            return None, start

        while next_index < len(lines) and lines[next_index].strip() == "":
            next_index += 1
        if next_index >= len(lines):
            return None, start

        price_line = lines[next_index].strip()
        if not price_re.match(price_line):
            return None, start
        if from_prefix and not price_line.lower().startswith("from"):
            price_line = from_prefix + price_line
        if re.match(r"^or\s*\$", price_line, re.IGNORECASE):
            price_line = MarkdownPipeline.format_outright_price(price_line)
        next_index += 1

        extra_prices: list[str] = []
        while next_index < len(lines):
            lookahead_index = next_index
            while lookahead_index < len(lines) and lines[lookahead_index].strip() == "":
                lookahead_index += 1
            if lookahead_index >= len(lines):
                break
            candidate = lines[lookahead_index].strip()
            if price_re.match(candidate) and re.match(
                r"(?:or\s*)",
                candidate,
                re.IGNORECASE,
            ):
                extra_prices.append(MarkdownPipeline.format_outright_price(candidate))
                next_index = lookahead_index + 1
            else:
                break

        pre_badges: list[str] = []
        name_parts: list[str] = list(content_lines)
        while len(name_parts) > 1:
            candidate = name_parts[0]
            if _BADGE_KEYWORDS.match(candidate) or (
                candidate.endswith("!") and len(candidate) < 80
            ):
                pre_badges.append(name_parts.pop(0))
            else:
                break

        post_badges: list[str] = []
        while next_index < len(lines):
            line = lines[next_index].strip()
            if not line:
                next_index += 1
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            if _BADGE_KEYWORDS.match(line):
                break
            lookahead_index = next_index + 1
            while lookahead_index < len(lines) and lines[lookahead_index].strip() == "":
                lookahead_index += 1
            if lookahead_index < len(lines):
                next_line = lines[lookahead_index].strip()
                if price_re.match(next_line):
                    break
                if next_line.lower() == "from":
                    from_index = lookahead_index + 1
                    while from_index < len(lines) and lines[from_index].strip() == "":
                        from_index += 1
                    if from_index < len(lines) and price_re.match(lines[from_index].strip()):
                        break
            if len(line) < _MAX_PRODUCT_NAME_LEN and (
                len(line) < _BADGE_SHORT_LINE_THRESHOLD or line.endswith("!")
            ):
                post_badges.append(line)
                next_index += 1
            else:
                break

        name = " ".join(name_parts)
        full_price = price_line
        if extra_prices:
            full_price = full_price + " · " + " · ".join(extra_prices)
        return {
            "name": name,
            "price": full_price,
            "badges": pre_badges + post_badges,
        }, next_index

    @staticmethod
    def dedup_paragraphs(text: str) -> str:
        paragraphs = _PARAGRAPH_SPLIT_2_RE.split(text)
        deduped: list[str] = []
        for paragraph in paragraphs:
            if not deduped or paragraph.strip() != deduped[-1].strip():
                deduped.append(paragraph)
        return "\n\n".join(deduped)

    @staticmethod
    def compact_short_paragraphs(text: str) -> str:
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
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

        for paragraph in paragraphs:
            stripped = paragraph.strip()
            is_single_line = "\n" not in stripped
            is_short = len(stripped) <= _MAX_SHORT_PARAGRAPH_LEN
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
                result.append(paragraph)

        flush_run()
        return "\n\n".join(result)

    @staticmethod
    def format_faq_questions(text: str) -> str:
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
        result: list[str] = []
        for paragraph in paragraphs:
            stripped = paragraph.strip()
            is_single_line = "\n" not in stripped
            if (
                is_single_line
                and stripped.endswith("?")
                and len(stripped) <= _MAX_FAQ_QUESTION_LEN
                and not _MD_HEADING_LINE_RE.match(stripped)
                and not _MD_LIST_ITEM_RE.match(stripped)
            ):
                result.append(f"### {stripped}")
            else:
                result.append(paragraph)
        return "\n\n".join(result)

    @staticmethod
    def promote_section_labels(text: str) -> str:
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
        result: list[str] = []
        index = 0
        while index < len(paragraphs):
            stripped = paragraphs[index].strip()
            is_single_line = "\n" not in stripped

            if (
                is_single_line
                and 0 < len(stripped) <= _MAX_SECTION_LABEL_LEN
                and not _MD_HEADING_LINE_RE.match(stripped)
                and not _MD_HORIZONTAL_RULE_RE.match(stripped)
                and not _MD_LIST_ITEM_RE.match(stripped)
                and not _MONTHLY_PRICE_RE.match(stripped)
                and not _OUTRIGHT_PRICE_RE.match(stripped)
                and not _OFFERS_RE.match(stripped)
                and not _BADGE_KEYWORDS.match(stripped)
                and not stripped.startswith("**")
                and index + 1 < len(paragraphs)
            ):
                next_paragraph = paragraphs[index + 1].strip()
                next_has_bullets = any(
                    _MD_LIST_ITEM_RE.match(line.strip())
                    for line in next_paragraph.split("\n")
                    if line.strip()
                )
                next_is_substantial = len(next_paragraph) >= _SUBSTANTIAL_CONTENT_LEN

                if next_has_bullets or next_is_substantial:
                    result.append(f"### {stripped}")
                    index += 1
                    continue

            result.append(paragraphs[index])
            index += 1

        return "\n\n".join(result)
