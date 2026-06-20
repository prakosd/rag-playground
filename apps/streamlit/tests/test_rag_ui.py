from __future__ import annotations

from rag_engine import RetrievedChunk
from vector_indexer import IndexManifest

from crawl4md_streamlit.i18n import STRINGS_EN
from crawl4md_streamlit.rag_ui import (
    format_score_percent,
    index_metadata_caption,
    sort_results_by_score,
)


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(text="t", source="s", score=score, metadata={})


def test_format_score_percent_clamps_to_0_100() -> None:
    assert format_score_percent(0.0) == 0
    assert format_score_percent(1.0) == 100
    assert format_score_percent(0.5) == 50
    assert format_score_percent(0.873) == 87
    assert format_score_percent(-0.2) == 0
    assert format_score_percent(1.4) == 100


def test_sort_results_by_score_orders_highest_first() -> None:
    ordered = sort_results_by_score([_chunk(0.2), _chunk(0.9), _chunk(0.5)])

    assert [chunk.score for chunk in ordered] == [0.9, 0.5, 0.2]


def test_index_metadata_caption_includes_useful_manifest_fields() -> None:
    manifest = IndexManifest(
        embedding_model_requested="amazon.titan-embed-text-v2:0",
        embedding_model_used="amazon.titan-embed-text-v2:0",
        embedding_dimension=512,
        collection_name="crawl4md_documents",
        chunk_size=600,
        chunk_overlap=100,
        language="english",
        success=True,
        indexed_file_count=3,
        indexed_chunk_count=42,
        skipped_file_count=0,
    )

    caption = index_metadata_caption(STRINGS_EN, manifest)

    assert "amazon.titan-embed-text-v2:0" in caption
    assert "english" in caption
    assert "100" in caption
    assert "crawl4md_documents" in caption
