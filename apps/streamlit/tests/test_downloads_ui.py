from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from app_support import downloads_ui
from app_support.conversational_rag.build_manager import BuildSnapshot, create_build


class _State(dict):
    """A session_state stand-in supporting both attribute and item access."""

    __getattr__ = dict.get  # type: ignore[assignment]
    __setattr__ = dict.__setitem__  # type: ignore[assignment]


# Risk: importing a history zip must replace in place, flag the success toast, and
# bust the file-listing caches so the panel repopulates. Type: unit.
def test_import_uploaded_history_zip_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = MagicMock()
    fake_st.session_state = _State()
    list_cache = MagicMock()
    tree_cache = MagicMock()
    monkeypatch.setattr(downloads_ui, "st", fake_st)
    monkeypatch.setattr(
        downloads_ui, "get_settings", lambda: SimpleNamespace(zip_signing_secret="k")
    )
    monkeypatch.setattr(downloads_ui, "_session_root", lambda: Path("/session"))
    monkeypatch.setattr(
        downloads_ui, "import_history_zip", lambda root, data, secret: "search_history"
    )
    monkeypatch.setattr(downloads_ui, "_cached_list_generated_files", list_cache)
    monkeypatch.setattr(downloads_ui, "_cached_download_tree", tree_cache)

    downloads_ui._import_uploaded_history_zip(b"zip")

    assert fake_st.session_state["upload_done_folder"] == "search_history"
    assert fake_st.session_state["upload_dialog_open"] is False
    list_cache.clear.assert_called_once()
    tree_cache.clear.assert_called_once()
    fake_st.rerun.assert_called_once()


# Risk: a rejected history import (bad signature / foreign folder) must not flag a
# success toast, but must still close the dialog. Type: unit.
def test_import_uploaded_history_zip_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = MagicMock()
    fake_st.session_state = _State()
    monkeypatch.setattr(downloads_ui, "st", fake_st)
    monkeypatch.setattr(
        downloads_ui, "get_settings", lambda: SimpleNamespace(zip_signing_secret="k")
    )
    monkeypatch.setattr(downloads_ui, "_session_root", lambda: Path("/session"))
    monkeypatch.setattr(downloads_ui, "import_history_zip", lambda root, data, secret: None)

    downloads_ui._import_uploaded_history_zip(b"zip")

    assert "upload_done_folder" not in fake_st.session_state
    assert fake_st.session_state["upload_dialog_open"] is False
    fake_st.rerun.assert_called_once()


# Risk: the preview modal shows file timestamps; a bad epoch must not crash the
# dialog. Verify the UTC formatter returns a stable string. Type: unit.
def test_format_preview_timestamp_utc_formats_epoch() -> None:
    assert downloads_ui._format_preview_timestamp_utc(0) == "1970-01-01 00:00:00 UTC"


# Risk: a missing timestamp must render as "no value" rather than raising.
# Type: unit.
def test_format_preview_timestamp_utc_none_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(None) is None


# Risk: an out-of-range timestamp (e.g. corrupt stat) must be swallowed, not
# crash the preview dialog. Type: unit.
def test_format_preview_timestamp_utc_out_of_range_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(1e300) is None


# Risk: a crafted filename (e.g. from an imported zip member) must not inject markup
# into the preview caption; every value is HTML-escaped. Type: unit.
def test_preview_caption_html_escapes_values() -> None:
    caption = downloads_ui._preview_caption_html(
        "Path: <img src=x onerror=alert(1)>", "Size: 1.0 KiB", None, None
    )
    assert "<img" not in caption
    assert "&lt;img src=x onerror=alert(1)&gt;" in caption


# Risk: after a browser reset clears the session, the session folder does not yet
# exist and holds no files; the panel must still show so Import is reachable.
# Type: unit.
def test_should_show_files_panel_idle_shows_even_without_files() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=False) is True
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=True) is True


# Risk: an empty panel must not flash mid-write; while a job runs, show the panel
# only once it holds files. Type: unit.
def test_should_show_files_panel_hides_empty_panel_during_active_job() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=False) is False
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=True) is True


def _render_downloads_view() -> None:
    # Self-contained render for AppTest.from_function (isolated namespace).
    import streamlit as st

    from app_support import downloads_ui as ui

    defaults = {
        "session_id": "s1",
        "job": None,
        "job_state": "idle",
        "vector_index_job": None,
        "vector_index_state": "idle",
        "language": "EN",
        "active_output_dir": "",
        "preview_file_relative_path": "",
        "delete_folder_relative_path": "",
        "export_folder_relative_path": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    ui._render_downloads()


# Risk: the Output Files panel render (tree, subheader, dataframe, sample panel) is
# untested; only its pure helpers are. Type: unit (AppTest).
def test_downloads_panel_renders_output_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    final_dir = (
        tmp_path
        / "outputs"
        / "streamlit_sessions"
        / "session_s1"
        / "crawl_01_x"
        / "2026-07-01_09-00-00"
        / "final"
    )
    final_dir.mkdir(parents=True)
    (final_dir / "sorted_success_content_001.md").write_text("# hi", encoding="utf-8")

    app = AppTest.from_function(_render_downloads_view)
    app.run(timeout=10)

    assert not app.exception


def _build_snapshot(name: str, vector_folder: str) -> BuildSnapshot:
    return BuildSnapshot(
        schema_version=1,
        created_at_utc="2026-10-30T00:00:00+00:00",
        name=name,
        slug="a_b_c_d_e",
        language="EN",
        answer_model="m",
        top_k=5,
        tone="Neutral",
        reranker="off",
        aux_model_id="echo",
        decomposition_limit=1,
        followup_show_count=0,
        followup_drop=0.3,
        followup_keep=0.6,
        followup_probe_k=3,
        answerability_chunks=2,
        state_summary_start_turn=4,
        state_summary_max_words=150,
        answer_recent_turns=5,
        plan_recent_turns=2,
        index_vector_folder=vector_folder,
        index_run_name="2026-10-28_10-00-00",
        embedding_model="titan",
        prompts={},
    )


# Risk: deleting a vector index that a Step 5 build still references must be blocked.
# Type: unit.
def test_builds_blocking_index_delete_lists_referencing_builds(tmp_path: Path) -> None:
    create_build(tmp_path, _build_snapshot("rag_build_01_garden", "vector_01_slate"))
    blocking = downloads_ui._builds_blocking_index_delete(tmp_path, "vector_01_slate")
    assert [snapshot.name for snapshot in blocking] == ["rag_build_01_garden"]


def test_builds_blocking_index_delete_empty_when_unreferenced(tmp_path: Path) -> None:
    create_build(tmp_path, _build_snapshot("rag_build_01_garden", "vector_02_other"))
    assert downloads_ui._builds_blocking_index_delete(tmp_path, "vector_01_slate") == []


def test_builds_blocking_index_delete_ignores_non_vector_targets(tmp_path: Path) -> None:
    create_build(tmp_path, _build_snapshot("rag_build_01_garden", "vector_01_slate"))
    # Crawl runs, builds, and nested paths are never guarded.
    assert downloads_ui._builds_blocking_index_delete(tmp_path, "crawl_01_run") == []
    assert downloads_ui._builds_blocking_index_delete(tmp_path, "rag_build_01_garden") == []
    assert downloads_ui._builds_blocking_index_delete(tmp_path, "vector_01_slate/2026-10-28") == []


# Risk: exporting a build must re-bundle its shared index so the zip stays portable.
# Type: unit.
def test_build_index_export_dirs_maps_shared_index(tmp_path: Path) -> None:
    from vector_indexer.manifest import write_manifest

    run = tmp_path / "vector_01_slate" / "2026-10-28_10-00-00"
    (run / "chroma").mkdir(parents=True)
    write_manifest(
        run,
        {
            "success": True,
            "indexed_chunk_count": 5,
            "embedding_model_used": "titan",
            "collection_name": "c",
        },
    )
    create_build(tmp_path, _build_snapshot("rag_build_01_garden", "vector_01_slate"))

    dirs = downloads_ui._build_index_export_dirs(tmp_path, "rag_build_01_garden")

    assert len(dirs) == 1
    [(prefix, source)] = dirs.items()
    assert source == run
    assert prefix.startswith("rag_build_01_garden/")
    assert prefix.endswith("vector_01_slate/2026-10-28_10-00-00")


def test_build_index_export_dirs_empty_for_non_build(tmp_path: Path) -> None:
    assert downloads_ui._build_index_export_dirs(tmp_path, "crawl_01_x") == {}
    assert downloads_ui._build_index_export_dirs(tmp_path, "vector_01_slate") == {}


def test_build_index_export_dirs_empty_for_old_self_contained_build(tmp_path: Path) -> None:
    # Old build with the index copied inside it (no shared session index) — already in
    # the zip, so there is nothing extra to re-bundle.
    from vector_indexer.manifest import write_manifest

    run_dir = tmp_path / "rag_build_01_garden" / "2026-10-28_10-00-00"
    copied = run_dir / "vector_01_slate" / "2026-10-28_10-00-00"
    (copied / "chroma").mkdir(parents=True)
    write_manifest(
        copied,
        {
            "success": True,
            "indexed_chunk_count": 5,
            "embedding_model_used": "titan",
            "collection_name": "c",
        },
    )
    (run_dir / "build.json").write_text(
        _build_snapshot("rag_build_01_garden", "vector_01_slate").to_json(), encoding="utf-8"
    )

    assert downloads_ui._build_index_export_dirs(tmp_path, "rag_build_01_garden") == {}
