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


def _history_hook_script(fire_label: str, folder: str) -> None:
    # Render a one-folder tree with an after_history_hook so a test can assert the hook
    # fires right after a history folder (and only for history folders).
    import streamlit as st

    from app_support import downloads_ui as ui

    for key, value in {
        "session_id": "s1",
        "language": "EN",
        "job": None,
        "job_state": "idle",
        "vector_index_job": None,
        "vector_index_state": "idle",
    }.items():
        st.session_state.setdefault(key, value)
    ui.render_download_tree(
        {folder: {}},
        allow_run_folder_collapse=False,
        after_history_hook=lambda: st.markdown(fire_label),
    )


def test_render_download_tree_fires_after_history_hook() -> None:
    # The build tree drops its Token-usage panel via this hook right after the
    # conversational_rag_history folder, so the hook must fire for a history folder.
    app = AppTest.from_function(
        _history_hook_script,
        kwargs={"fire_label": "HOOK_FIRED", "folder": "conversational_rag_history"},
    )
    app.run(timeout=10)
    assert not app.exception
    assert any("HOOK_FIRED" in block.value for block in app.markdown)


def test_render_download_tree_hook_skips_non_history_folder() -> None:
    app = AppTest.from_function(
        _history_hook_script,
        kwargs={"fire_label": "HOOK_FIRED", "folder": "vector_01_slate"},
    )
    app.run(timeout=10)
    assert not app.exception
    assert not any("HOOK_FIRED" in block.value for block in app.markdown)


def test_on_export_dismiss_clears_painted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Dismissing the export modal must reset every export key, including the two-phase
    # "painted" flag, so the next export starts fresh (and re-paints its shell).
    fake_st = MagicMock()
    fake_st.session_state = _State(
        {
            "export_folder_relative_path": "crawl_01_garden",
            "export_zip_payload": {"relative_path": "crawl_01_garden", "bytes": b"z"},
            "export_autoclicked": True,
            "export_dialog_painted_for": "crawl_01_garden",
        }
    )
    monkeypatch.setattr(downloads_ui, "st", fake_st)

    downloads_ui._on_export_dismiss()

    assert fake_st.session_state["export_folder_relative_path"] == ""
    assert "export_zip_payload" not in fake_st.session_state
    assert "export_autoclicked" not in fake_st.session_state
    assert "export_dialog_painted_for" not in fake_st.session_state


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


def _render_rename_dialog_view(rename_path: str) -> None:
    # Self-contained render for AppTest with the rename dialog primed to open.
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
        "rename_folder_relative_path": rename_path,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    ui._render_downloads()


def _render_delete_dialog_view(delete_path: str) -> None:
    # Self-contained render for AppTest with the delete-folder dialog primed to open.
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
        "delete_folder_relative_path": delete_path,
        "export_folder_relative_path": "",
        "rename_folder_relative_path": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    ui._render_downloads()


def _render_multi_state_view(delete_path: str, export_path: str) -> None:
    # Prime BOTH the delete and export dialog states to verify only one modal renders.
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
        "delete_folder_relative_path": delete_path,
        "export_folder_relative_path": export_path,
        "rename_folder_relative_path": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    ui._render_downloads()


def test_only_one_files_dialog_renders_when_multiple_states_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Defensive: a just-dismissed dialog must not linger beside a newly opened one, so the
    # body renders only the first modal whose state is set (delete is checked before export).
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_multi_state_view,
        kwargs={"delete_path": "crawl_01_garden", "export_path": "crawl_01_garden"},
    )
    app.run(timeout=10)

    assert not app.exception
    # Delete wins (checked first); its confirm button renders.
    assert any(getattr(b, "key", "") == "delete_folder_confirm_button" for b in app.button)
    # The export dialog must not render alongside it (no download button, no preparing shell).
    assert not any(getattr(b, "key", "").startswith("export_download_") for b in app.button)
    assert "export_dialog_painted_for" not in app.session_state


def test_delete_blocked_close_button_avoids_red_delete_key_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Regression: the red-delete CSS matches any "st-key-delete_folder_*" key, so the
    # blocked-index notice's primary Close button must use a key without that prefix
    # (otherwise its text renders dark-red-on-red and is unreadable).
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "vector_01_slate").mkdir(parents=True)
    monkeypatch.setattr(
        downloads_ui,
        "_builds_blocking_index_delete",
        lambda *_: [SimpleNamespace(name="rag_build_01_garden", slug="a_b_c_d_e")],
    )

    app = AppTest.from_function(
        _render_delete_dialog_view, kwargs={"delete_path": "vector_01_slate"}
    )
    app.run(timeout=10)

    assert not app.exception
    assert any("Can't delete this index" in block.value for block in app.subheader)
    close_buttons = [button for button in app.button if button.label == "Close"]
    assert close_buttons
    assert all(not button.key.startswith("delete_folder_") for button in close_buttons)


def test_folder_rename_button_shown_before_delete_for_run_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    final_dir = (
        tmp_path
        / "outputs"
        / "streamlit_sessions"
        / "session_s1"
        / "crawl_01_garden"
        / "2026-07-01_09-00-00"
        / "final"
    )
    final_dir.mkdir(parents=True)
    (final_dir / "sorted_success_content_001.md").write_text("# hi", encoding="utf-8")

    app = AppTest.from_function(_render_rename_dialog_view, kwargs={"rename_path": ""})
    app.run(timeout=10)

    assert not app.exception
    keys = [button.key for button in app.button if button.key]
    rename_keys = [key for key in keys if key.startswith("rename_folder_s1_crawl_01_garden")]
    delete_keys = [key for key in keys if key.startswith("delete_folder_s1_crawl_01_garden")]
    assert rename_keys and delete_keys
    # Rename sits to the left of Delete in the action row.
    assert keys.index(rename_keys[0]) < keys.index(delete_keys[0])


def test_rename_dialog_renders_prefilled_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "crawl_01_garden"}
    )
    app.run(timeout=10)

    assert not app.exception
    # The dialog prefills the editable label (the part after the locked crawl_01_ prefix).
    assert any(widget.value == "garden" for widget in app.text_input)
    # The locked prefix shows inline before the field (no explanatory caption anymore).
    assert any("crawl_01_" in md.value for md in app.markdown)
    assert not any("part stays" in md.value for md in app.markdown)
    # Confirm button is labelled "Confirm"; Cancel + Confirm are the form's submit buttons.
    confirm = next(b for b in app.button if b.key == "rename_folder_confirm_button")
    assert confirm.label == "Confirm"
    assert any(b.key == "rename_folder_cancel_button" for b in app.button)


def test_rename_dialog_blocks_referenced_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "vector_01_slate").mkdir(parents=True)
    # Stub the shared block check (its real logic is covered by the _builds_blocking_* tests)
    # so the tree needs no build folder — which would pull in the CCv2 launch component.
    monkeypatch.setattr(
        downloads_ui,
        "_builds_blocking_index_delete",
        lambda *_: [SimpleNamespace(name="rag_build_01_garden", slug="a_b_c_d_e")],
    )

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "vector_01_slate"}
    )
    app.run(timeout=10)

    assert not app.exception
    # A build references the index, so the blocked notice shows and no rename input renders.
    assert any("Can't rename this index" in block.value for block in app.subheader)
    assert not app.text_input


def test_rename_dialog_confirm_renames_in_one_click(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "crawl_01_garden"}
    )
    app.run(timeout=10)
    assert not app.exception
    # Edit the label and submit the form once — the render-context handler applies it in
    # one pass (and closes the modal), no two-click dance.
    text_input = next(w for w in app.text_input if w.value == "garden")
    text_input.set_value("beach")
    next(b for b in app.button if b.key == "rename_folder_confirm_button").click()
    app.run(timeout=10)

    assert not app.exception
    assert (session / "crawl_01_beach").is_dir()
    assert not (session / "crawl_01_garden").exists()
    assert app.session_state["rename_folder_relative_path"] == ""  # dialog closed


def test_rename_dialog_confirm_is_first_submit_so_enter_targets_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "crawl_01_garden"}
    )
    app.run(timeout=10)
    assert not app.exception
    # Streamlit's Enter-to-submit fires the FIRST form-submit button in element-tree order,
    # so Confirm must precede Cancel in the tree — otherwise Enter would dismiss via Cancel
    # without renaming (the reported bug).
    rename_keys = [
        b.key
        for b in app.button
        if b.key in {"rename_folder_confirm_button", "rename_folder_cancel_button"}
    ]
    assert rename_keys == ["rename_folder_confirm_button", "rename_folder_cancel_button"]
    # The action row is visually reversed so Cancel still reads left and Confirm right.
    assert any("flex-direction:row-reverse" in md.value for md in app.markdown)


def test_rename_dialog_cancel_closes_without_renaming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "crawl_01_garden"}
    )
    app.run(timeout=10)
    text_input = next(w for w in app.text_input if w.value == "garden")
    text_input.set_value("beach")
    next(b for b in app.button if b.key == "rename_folder_cancel_button").click()
    app.run(timeout=10)

    assert not app.exception
    # Cancel clears the dialog state and leaves the folder untouched.
    assert (session / "crawl_01_garden").is_dir()
    assert not (session / "crawl_01_beach").exists()
    assert app.session_state["rename_folder_relative_path"] == ""


def test_rename_dialog_invalid_label_keeps_dialog_open_with_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    (session / "crawl_01_garden" / "2026-07-01_09-00-00").mkdir(parents=True)

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "crawl_01_garden"}
    )
    app.run(timeout=10)
    text_input = next(w for w in app.text_input if w.value == "garden")
    text_input.set_value("with space")  # now invalid (underscore-only)
    next(b for b in app.button if b.key == "rename_folder_confirm_button").click()
    app.run(timeout=10)

    assert not app.exception
    # The folder is untouched, the dialog stays open, and an inline error shows.
    assert (session / "crawl_01_garden").is_dir()
    assert app.session_state["rename_folder_relative_path"] == "crawl_01_garden"
    assert any("letters, numbers, underscores, and dashes" in err.value for err in app.error)


def test_rename_dialog_renames_build_and_syncs_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app_support.conversational_rag.conversational_rag_build_ui as build_ui
    from app_support.conversational_rag.build_manager import load_build

    # Stub the CCv2 Launch component (its registration leaks across AppTest contexts) so
    # rendering the tree with a build folder stays isolated.
    monkeypatch.setattr(build_ui, "render_launch_button", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)
    session = tmp_path / "outputs" / "streamlit_sessions" / "session_s1"
    run_dir = session / "rag_build_01_garden" / "2026-10-28_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "build.json").write_text(
        _build_snapshot("rag_build_01_garden", "vector_01_slate").to_json(), encoding="utf-8"
    )

    app = AppTest.from_function(
        _render_rename_dialog_view, kwargs={"rename_path": "rag_build_01_garden"}
    )
    app.run(timeout=10)
    assert not app.exception
    # A build folder prefills its label after the locked rag_build_01_ prefix.
    text_input = next(w for w in app.text_input if w.value == "garden")
    text_input.set_value("charter")
    next(b for b in app.button if b.key == "rename_folder_confirm_button").click()
    app.run(timeout=10)

    assert not app.exception
    assert (session / "rag_build_01_charter").is_dir()
    assert not (session / "rag_build_01_garden").exists()
    # build.json's name is kept in sync by rename_build.
    snapshot = load_build(session / "rag_build_01_charter")
    assert snapshot is not None
    assert snapshot.name == "rag_build_01_charter"
