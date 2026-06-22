from __future__ import annotations

from rag_engine import RetrievedChunk
from vector_indexer import IndexManifest

from crawl4md_streamlit.i18n import STRINGS_EN
from crawl4md_streamlit.rag_ui import (
    format_score_percent,
    index_metadata_rows,
    result_detail_caption,
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


def test_result_detail_caption_includes_chunk_id_size_and_language() -> None:
    chunk = RetrievedChunk(
        text="hello world",
        source="doc.md",
        score=0.5,
        metadata={"chunk_index": "3", "language": "english"},
    )

    caption = result_detail_caption(STRINGS_EN, chunk)

    assert "doc.md#3" in caption
    assert "11 chars" in caption  # len("hello world") == 11
    assert "english" in caption


def test_index_metadata_rows_include_key_manifest_fields() -> None:
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
        created_at="2026-06-22T10:30:00+00:00",
    )

    rows = dict(index_metadata_rows(STRINGS_EN, manifest))

    assert rows[STRINGS_EN["SEARCH_META_MODEL"]] == "amazon.titan-embed-text-v2:0"
    assert rows[STRINGS_EN["SEARCH_META_LANGUAGE"]] == "english"
    assert rows[STRINGS_EN["SEARCH_META_OVERLAP"]] == "100"
    assert rows[STRINGS_EN["SEARCH_META_COLLECTION"]] == "crawl4md_documents"
    assert "2026-06-22 10:30 UTC" in rows[STRINGS_EN["SEARCH_META_CREATED"]]
