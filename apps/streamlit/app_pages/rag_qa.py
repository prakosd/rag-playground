"""Step 4 content area for single-turn RAG Q&A."""

from __future__ import annotations

from app_pages._placeholder import render_placeholder_page

_PAGE_ID = "rag_qa"


def render_page() -> None:
    """Render the RAG Q&A page content area."""
    render_placeholder_page(_PAGE_ID)
