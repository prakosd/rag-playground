"""Page metadata for the crawl4md Streamlit workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_PAGE_ID_CRAWL = "crawl"
_PAGE_ID_VECTOR_INDEX = "vector_index"
_PAGE_ID_SEMANTIC_SEARCH = "semantic_search"
_PAGE_ID_RAG_QA = "rag_qa"
_PAGE_ID_CONVERSATIONAL_RAG = "conversational_rag"

DEFAULT_PAGE_ID = _PAGE_ID_CRAWL


@dataclass(frozen=True)
class AppPageSpec:
    """Navigation and translation keys for one Streamlit page."""

    page_id: str
    nav_label_key: str
    title_key: str
    subtitle_key: str
    icon: str
    url_path: str
    module_name: str
    placeholder_key: str | None = None


APP_PAGE_SPECS: tuple[AppPageSpec, ...] = (
    AppPageSpec(
        page_id=_PAGE_ID_CRAWL,
        nav_label_key="NAV_CRAWL",
        title_key="PAGE_TITLE",
        subtitle_key="PAGE_SUBTITLE",
        icon=":material/travel_explore:",
        url_path="crawl",
        module_name="app_pages.crawl4md",
    ),
    AppPageSpec(
        page_id=_PAGE_ID_VECTOR_INDEX,
        nav_label_key="NAV_VECTOR_INDEX",
        title_key="PAGE_VECTOR_INDEX_TITLE",
        subtitle_key="PAGE_VECTOR_INDEX_SUBTITLE",
        icon=":material/database:",
        url_path="vector-index",
        module_name="app_pages.vector_index",
        placeholder_key="PLACEHOLDER_VECTOR_INDEX",
    ),
    AppPageSpec(
        page_id=_PAGE_ID_SEMANTIC_SEARCH,
        nav_label_key="NAV_SEMANTIC_SEARCH",
        title_key="PAGE_SEMANTIC_SEARCH_TITLE",
        subtitle_key="PAGE_SEMANTIC_SEARCH_SUBTITLE",
        icon=":material/search:",
        url_path="semantic-search",
        module_name="app_pages.semantic_search",
        placeholder_key="PLACEHOLDER_SEMANTIC_SEARCH",
    ),
    AppPageSpec(
        page_id=_PAGE_ID_RAG_QA,
        nav_label_key="NAV_RAG_QA",
        title_key="PAGE_RAG_QA_TITLE",
        subtitle_key="PAGE_RAG_QA_SUBTITLE",
        icon=":material/question_answer:",
        url_path="rag-qa",
        module_name="app_pages.rag_qa",
        placeholder_key="PLACEHOLDER_RAG_QA",
    ),
    AppPageSpec(
        page_id=_PAGE_ID_CONVERSATIONAL_RAG,
        nav_label_key="NAV_CONVERSATIONAL_RAG",
        title_key="PAGE_CONVERSATIONAL_RAG_TITLE",
        subtitle_key="PAGE_CONVERSATIONAL_RAG_SUBTITLE",
        icon=":material/forum:",
        url_path="conversational-rag",
        module_name="app_pages.conversational_rag",
        placeholder_key="PLACEHOLDER_CONVERSATIONAL_RAG",
    ),
)


def page_spec_by_id(page_id: str) -> AppPageSpec:
    """Return the page spec matching *page_id*, falling back to the crawl page."""
    for page_spec in APP_PAGE_SPECS:
        if page_spec.page_id == page_id:
            return page_spec
    return default_page_spec()


def page_spec_by_nav_label(nav_label: str, strings: Mapping[str, object]) -> AppPageSpec:
    """Return the page spec matching a translated navigation label."""
    for page_spec in APP_PAGE_SPECS:
        if str(strings[page_spec.nav_label_key]) == nav_label:
            return page_spec
    return default_page_spec()


def default_page_spec() -> AppPageSpec:
    """Return the default crawl page spec."""
    return APP_PAGE_SPECS[0]
