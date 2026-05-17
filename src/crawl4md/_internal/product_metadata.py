"""Product metadata extraction helpers for ContentExtractor."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

__all__ = ["ProductMetadataExtractor"]

_HTML_PARSER = "html.parser"
_JSON_LD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_PRICE_DETECT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
_OG_META_RE_TEMPLATE = (
    r'<meta[^>]+property=["\'](?:og:)?{prop}["\'][^>]+content=["\']([^"\']+)["\']'
)
_OG_META_REVERSE_RE_TEMPLATE = (
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\'](?:og:)?{prop}["\']'
)
_BRAND_EXCLUSION_KEYWORDS = frozenset(
    {"devices", "mobile", "store", "personal", "products", "shop", "buy"}
)
_NON_VISIBLE_TAGS = ("script", "style", "noscript")
_STRIKE_TAGS = ("del", "s", "strike")
_HEADING_TAGS = ("h1", "h2", "h3")
_MAX_DOM_DEPTH = 15
_PRODUCT_TYPE = "Product"
_GRAPH_KEY = "@graph"
_TYPE_KEY = "@type"
_NAME_KEY = "name"
_BRAND_KEY = "brand"
_OFFERS_KEY = "offers"
_PRICE_KEY = "price"
_LOW_PRICE_KEY = "lowPrice"
_HIGH_PRICE_KEY = "highPrice"
_PRODUCT_PRICE_META = "product:price:amount"
_PRODUCT_BRAND_META = "product:brand"
_TITLE_META = "title"

_ProductMetadata = dict[str, str]


class ProductMetadataExtractor:
    """Extract product detail metadata from structured data, Open Graph, or DOM hints."""

    @staticmethod
    def extract(html: str, *, soup: BeautifulSoup | None = None) -> _ProductMetadata | None:
        result = ProductMetadataExtractor.from_jsonld(html)
        if result:
            return result
        result = ProductMetadataExtractor.from_open_graph(html)
        if result:
            return result
        return ProductMetadataExtractor.from_dom(html, soup=soup)

    @staticmethod
    def from_jsonld(html: str) -> _ProductMetadata | None:
        for match in _JSON_LD_SCRIPT_RE.finditer(html):
            try:
                data = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                continue
            product = ProductMetadataExtractor.find_in_jsonld(data)
            if product:
                return product
        return None

    @staticmethod
    def find_in_jsonld(data: object) -> _ProductMetadata | None:
        if isinstance(data, list):
            for item in data:
                result = ProductMetadataExtractor.find_in_jsonld(item)
                if result:
                    return result
            return None
        if not isinstance(data, dict):
            return None
        ld_type = data.get(_TYPE_KEY, "")
        if isinstance(ld_type, list):
            ld_type = " ".join(ld_type)
        if _PRODUCT_TYPE not in ld_type:
            if _GRAPH_KEY in data:
                return ProductMetadataExtractor.find_in_jsonld(data[_GRAPH_KEY])
            return None

        name = data.get(_NAME_KEY, "")
        brand = ProductMetadataExtractor._brand_from_jsonld(data.get(_BRAND_KEY))
        price, high_price = ProductMetadataExtractor._prices_from_jsonld(data.get(_OFFERS_KEY))

        if not name:
            return None
        return {
            _NAME_KEY: str(name),
            _BRAND_KEY: brand,
            _PRICE_KEY: price,
            "high_price": high_price,
        }

    @staticmethod
    def _brand_from_jsonld(brand_obj: object) -> str:
        if isinstance(brand_obj, dict):
            return str(brand_obj.get(_NAME_KEY, ""))
        if isinstance(brand_obj, str):
            return brand_obj
        return ""

    @staticmethod
    def _prices_from_jsonld(offers: object) -> tuple[str, str]:
        if isinstance(offers, dict):
            price = str(offers.get(_PRICE_KEY, offers.get(_LOW_PRICE_KEY, "")))
            high_price = str(offers.get(_HIGH_PRICE_KEY, ""))
            return price, high_price
        if isinstance(offers, list) and offers:
            first_offer = offers[0] if isinstance(offers[0], dict) else {}
            price = str(first_offer.get(_PRICE_KEY, first_offer.get(_LOW_PRICE_KEY, "")))
            high_price = str(first_offer.get(_HIGH_PRICE_KEY, ""))
            return price, high_price
        return "", ""

    @staticmethod
    def from_open_graph(html: str) -> _ProductMetadata | None:
        price = ProductMetadataExtractor._open_graph_value(html, _PRODUCT_PRICE_META)
        if not price:
            return None
        name = ProductMetadataExtractor._open_graph_value(html, _TITLE_META)
        brand = ProductMetadataExtractor._open_graph_value(html, _PRODUCT_BRAND_META)
        return {_NAME_KEY: name, _BRAND_KEY: brand, _PRICE_KEY: price, "high_price": ""}

    @staticmethod
    def _open_graph_value(html: str, prop: str) -> str:
        escaped_prop = re.escape(prop)
        pattern = _OG_META_RE_TEMPLATE.format(prop=escaped_prop)
        match = re.search(pattern, html, re.IGNORECASE)
        if not match:
            pattern = _OG_META_REVERSE_RE_TEMPLATE.format(prop=escaped_prop)
            match = re.search(pattern, html, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def from_dom(html: str, *, soup: BeautifulSoup | None = None) -> _ProductMetadata | None:
        if soup is None:
            soup = BeautifulSoup(html, _HTML_PARSER)
            for tag in soup.find_all(_NON_VISIBLE_TAGS):
                tag.decompose()

        strike_tag = ProductMetadataExtractor._find_strike_price_tag(soup)
        if not strike_tag:
            return None

        high_price = ProductMetadataExtractor._high_price_from_strike(strike_tag)
        price = ProductMetadataExtractor._current_price_from_strike(strike_tag, high_price)
        name = ProductMetadataExtractor._name_near_strike(strike_tag)
        brand = ProductMetadataExtractor._brand_from_page_url(soup)

        if not name and not price and not high_price:
            return None
        return {
            _NAME_KEY: name,
            _BRAND_KEY: brand,
            _PRICE_KEY: price,
            "high_price": high_price,
        }

    @staticmethod
    def _find_strike_price_tag(soup: BeautifulSoup) -> Tag | None:
        price_tags: list[Tag] = []
        for tag_name in _STRIKE_TAGS:
            for tag in soup.find_all(tag_name):
                if ProductMetadataExtractor._has_non_visible_ancestor(tag):
                    continue
                text = tag.get_text(strip=True)
                if _PRICE_DETECT_RE.search(text):
                    price_tags.append(tag)
        if len(price_tags) != 1:
            return None
        return price_tags[0]

    @staticmethod
    def _has_non_visible_ancestor(tag: Tag) -> bool:
        return any(
            isinstance(parent, Tag) and parent.name in _NON_VISIBLE_TAGS for parent in tag.parents
        )

    @staticmethod
    def _high_price_from_strike(strike_tag: Tag) -> str:
        high_price_match = _PRICE_DETECT_RE.search(strike_tag.get_text(strip=True))
        return high_price_match.group(0).lstrip("$") if high_price_match else ""

    @staticmethod
    def _current_price_from_strike(strike_tag: Tag, high_price: str) -> str:
        parent = strike_tag.parent
        if not isinstance(parent, Tag):
            return ""
        price = ""
        full_text = parent.get_text(" ", strip=True)
        prices = _PRICE_DETECT_RE.findall(full_text)
        for price_text in prices:
            if price_text.lstrip("$") != high_price:
                price = price_text.lstrip("$")
        return price

    @staticmethod
    def _name_near_strike(strike_tag: Tag) -> str:
        node: Tag = strike_tag
        for _depth in range(_MAX_DOM_DEPTH):
            parent = node.parent
            if not isinstance(parent, Tag):
                break
            heading = parent.find(list(_HEADING_TAGS))
            if heading:
                return heading.get_text(" ", strip=True)
            node = parent
        return ""

    @staticmethod
    def _brand_from_page_url(soup: BeautifulSoup) -> str:
        canonical = soup.find("link", rel="canonical")
        page_url = str(canonical["href"]) if canonical and canonical.get("href") else ""
        if not page_url:
            og_url = soup.find("meta", attrs={"property": "og:url"})
            page_url = str(og_url["content"]) if og_url and og_url.get("content") else ""
        if not page_url:
            return ""
        parts = urlparse(page_url).path.strip("/").split("/")
        if len(parts) < 2:
            return ""
        candidate = parts[-2].replace("-", " ").title()
        if candidate.lower() in _BRAND_EXCLUSION_KEYWORDS:
            return ""
        return candidate

    @staticmethod
    def format_price(product: _ProductMetadata) -> str:
        price = product.get(_PRICE_KEY, "")
        high_price = product.get("high_price", "")
        if not price and not high_price:
            return ""
        if high_price and price and high_price != price:
            return f"~~${high_price}~~ ${price}"
        if price:
            return f"${price}"
        return ""
