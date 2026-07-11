from __future__ import annotations

from pathlib import Path

from artifact_store.crawl_results import CrawlResultFile
from vector_indexer import DEFAULT_LOCAL_MODEL
from vector_indexer.embeddings import TITAN_MODEL

from app_support.i18n import get_strings
from app_support.vector_index.vector_form_ui import (
    crawl_result_options,
    embedding_model_info_for,
    embedding_model_label,
    has_index_inputs,
    resolve_embedding_model_choices,
)


def _crawl_result(crawl_label: str, relative_path: str, path: str) -> CrawlResultFile:
    return CrawlResultFile(
        path=Path(path),
        relative_path=relative_path,
        crawl_label=crawl_label,
        size_bytes=1,
    )


def test_resolve_embedding_model_choices_orders_configured_first() -> None:
    ordered, index = resolve_embedding_model_choices(
        [DEFAULT_LOCAL_MODEL, TITAN_MODEL],
        [TITAN_MODEL, DEFAULT_LOCAL_MODEL],
        DEFAULT_LOCAL_MODEL,
    )
    assert ordered == [DEFAULT_LOCAL_MODEL, TITAN_MODEL]
    assert index == 0


def test_resolve_embedding_model_choices_appends_unlisted_allowed_models() -> None:
    # MiniLM is configured first; Titan is appended so a supported model isn't hidden.
    ordered, index = resolve_embedding_model_choices(
        [DEFAULT_LOCAL_MODEL],
        [TITAN_MODEL, DEFAULT_LOCAL_MODEL],
        DEFAULT_LOCAL_MODEL,
    )
    assert ordered == [DEFAULT_LOCAL_MODEL, TITAN_MODEL]
    assert index == 0


def test_resolve_embedding_model_choices_drops_unknown_configured_ids() -> None:
    ordered, index = resolve_embedding_model_choices(
        ["made-up-model", TITAN_MODEL],
        [TITAN_MODEL, DEFAULT_LOCAL_MODEL],
        TITAN_MODEL,
    )
    assert ordered == [TITAN_MODEL, DEFAULT_LOCAL_MODEL]
    assert index == 0


def test_resolve_embedding_model_choices_falls_back_to_first_when_default_unsupported() -> None:
    ordered, index = resolve_embedding_model_choices(
        [TITAN_MODEL, DEFAULT_LOCAL_MODEL],
        [TITAN_MODEL, DEFAULT_LOCAL_MODEL],
        "unknown-default",
    )
    assert ordered == [TITAN_MODEL, DEFAULT_LOCAL_MODEL]
    assert index == 0


def test_crawl_result_options_maps_label_to_path() -> None:
    files = [_crawl_result("crawl_01_a", "crawl_01_a/final/notes.md", "/abs/notes.md")]

    options = crawl_result_options(files)

    label = next(iter(options))
    assert "crawl_01_a" in label
    assert "notes.md" in label
    assert list(options.values()) == [str(Path("/abs/notes.md"))]


def test_crawl_result_options_disambiguates_duplicate_labels() -> None:
    files = [
        _crawl_result("c", "c/final/x.md", "/a/x.md"),
        _crawl_result("c", "c/final/x.md", "/b/x.md"),
    ]

    options = crawl_result_options(files)

    assert len(options) == 2
    assert set(options.values()) == {str(Path("/a/x.md")), str(Path("/b/x.md"))}


def test_has_index_inputs() -> None:
    assert has_index_inputs(["/a"], 0)
    assert has_index_inputs([], 2)
    assert not has_index_inputs([], 0)


def test_embedding_model_info_for_returns_catalog_metadata() -> None:
    info = embedding_model_info_for(DEFAULT_LOCAL_MODEL)

    assert info.kind == "local"
    assert info.one_time_download is True
    assert info.supported_dimensions == (info.default_dimension,)


def test_embedding_model_info_for_unknown_model_uses_open_range() -> None:
    info = embedding_model_info_for("made-up/model")

    assert info.kind == "unknown"
    assert info.supported_dimensions is None
    assert info.min_dimension == 1
    assert info.max_dimension is None


def test_embedding_model_label_tags_local_and_cloud() -> None:
    strings = get_strings("en")

    local_label = embedding_model_label(DEFAULT_LOCAL_MODEL, strings)
    cloud_label = embedding_model_label(TITAN_MODEL, strings)

    assert DEFAULT_LOCAL_MODEL in local_label
    assert strings["VEC_MODEL_TAG_LOCAL"] in local_label
    assert strings["VEC_MODEL_TAG_CLOUD"] in cloud_label


def test_embedding_model_label_returns_plain_id_for_unknown_model() -> None:
    strings = get_strings("en")

    assert embedding_model_label("made-up/model", strings) == "made-up/model"
