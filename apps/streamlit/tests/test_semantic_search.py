"""Tests for the semantic search page's pure replay/summary helpers."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path

from pytest import MonkeyPatch

from crawl4md_streamlit.i18n import STRINGS_EN
from crawl4md_streamlit.search_history import SearchRecord

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.semantic_search")


def _record(**overrides: object) -> SearchRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-01T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-01_09-00-00",
        "embedding_model": "titan",
        "query": "rain today",
        "search_type": "mmr",
        "top_k": 7,
        "fetch_k": 25,
        "mmr_lambda": 0.4,
        "score_threshold": 0.3,
        "source_filter": ("a.md", "b.md"),
        "result_count": 4,
        "top_score": 0.9,
    }
    values.update(overrides)
    return SearchRecord(**values)  # type: ignore[arg-type]


def test_config_from_record_round_trips_search_parameters(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    config = page._config_from_record(asdict(_record()))

    assert config.top_k == 7
    assert config.fetch_k == 25
    assert config.search_type == "mmr"
    assert config.lambda_mult == 0.4
    assert config.score_threshold == 0.3
    assert config.source_filter == ("a.md", "b.md")


def test_options_summary_similarity_omits_mmr_parts(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    summary = page._options_summary(
        STRINGS_EN,
        _record(search_type="similarity", top_k=5, score_threshold=0.2, source_filter=()),
    )

    assert STRINGS_EN["SEARCH_MODE_SIMILARITY"] in summary
    assert "top 5" in summary
    assert "min 20%" in summary
    assert "diversity" not in summary


def test_options_summary_includes_mmr_and_sources(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    summary = page._options_summary(
        STRINGS_EN, _record(search_type="mmr", fetch_k=30, mmr_lambda=0.35)
    )

    assert "diversity 0.35" in summary
    assert "pool 30" in summary
    assert "2 file(s)" in summary


def test_local_time_label_falls_back_on_bad_value(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    assert page._local_time_label("not-a-timestamp") == "not-a-timestamp"
    # A valid UTC timestamp renders a non-empty localized label.
    assert page._local_time_label("2026-07-01T10:00:00+00:00")


def test_replay_prefills_query_and_reruns_without_warnings(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))

    def render(session_dir: str) -> None:
        from pathlib import Path as _Path
        from types import SimpleNamespace
        from unittest.mock import patch

        import app_pages.semantic_search as page
        from vector_indexer import IndexManifest

        from crawl4md_streamlit.index_catalog import IndexRef
        from crawl4md_streamlit.rag_ui import RagPageContext

        root = _Path(session_dir)
        manifest = IndexManifest(
            embedding_model_requested="titan",
            embedding_model_used="titan",
            embedding_dimension=512,
            collection_name="c",
            chunk_size=600,
            chunk_overlap=100,
            language="english",
            success=True,
            indexed_file_count=1,
            indexed_chunk_count=3,
            skipped_file_count=0,
            indexed_sources=("a.md",),
        )
        ref = IndexRef(
            run_dir=root / "idx",
            vector_folder="vector_01_x",
            run_name="2026-07-01_09-00-00",
            manifest=manifest,
        )
        context = RagPageContext(
            default_language="EN",
            list_indexes=lambda: [ref],
            render_downloads=lambda: None,
            session_root=lambda: root,
        )
        empty = SimpleNamespace(chunks=[], warnings=[], errors=[])
        with patch.object(page, "retrieve", return_value=empty):
            page.render_page(context)

    app = AppTest.from_function(render, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)
    assert not app.exception

    app.session_state["semantic_search_replay"] = asdict(
        _record(query="rerun me", source_filter=("a.md",))
    )
    app.run(timeout=10)

    assert not app.exception
    # The magnifier replay re-fills the query widget across the rerun and re-runs
    # the search (retrieve is mocked); the setdefault pattern keeps the keyed
    # widgets from tripping Streamlit's default-value-plus-Session-State warning.
    assert app.session_state["semantic_search_query"] == "rerun me"
