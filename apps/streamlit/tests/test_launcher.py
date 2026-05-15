from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STREAMLIT_CONFIG = _REPO_ROOT / ".streamlit" / "config.toml"
_APP_STREAMLIT_CONFIG = _REPO_ROOT / "apps" / "streamlit" / ".streamlit" / "config.toml"
_STREAMLIT_APP_FILE = _REPO_ROOT / "apps" / "streamlit" / "streamlit_app.py"
_STREAMLIT_SUPPORT_SRC = _REPO_ROOT / "apps" / "streamlit" / "src" / "crawl4md_streamlit"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_app_streamlit_config_exists_and_sets_server_defaults() -> None:
    config_text = _APP_STREAMLIT_CONFIG.read_text(encoding="utf-8")

    assert 'address = "0.0.0.0"' in config_text
    assert "port = 8501" in config_text


def test_root_streamlit_config_does_not_exist() -> None:
    assert not _ROOT_STREAMLIT_CONFIG.exists()


def test_streamlit_support_package_does_not_import_streamlit() -> None:
    for path in _STREAMLIT_SUPPORT_SRC.rglob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith("streamlit"), (
                f"{path.relative_to(_REPO_ROOT)} imports {module!r}"
            )


def test_running_state_no_longer_uses_page_level_spinner() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "crawl-running-dot" not in app_source
    assert 'with st.spinner("Running"):' not in app_source
    assert 'st.spinner("Crawling…")' not in app_source


def test_download_buttons_rely_on_native_left_alignment() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "use_container_width=True" not in app_source
    assert 'div[class*="st-key-download_"] button {' not in app_source


def test_stop_action_uses_confirmation_dialog() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert '@st.dialog("Stop crawl?", width="small")' in app_source
    assert "if st.session_state.stop_confirmation_open:" in app_source
    assert "_stop_confirmation_dialog()" in app_source


def test_stop_form_submit_sets_confirmation_flag() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'elif values["stop_submitted"]:' in app_source
    assert "st.session_state.stop_confirmation_open = True" in app_source


def test_stop_confirmation_dialog_wires_both_actions() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'st.button(strings["DIALOG_BTN_KEEP"], key="stop_cancel_button")' in app_source
    assert "st.button(" in app_source
    assert 'strings["DIALOG_BTN_STOP"],' in app_source
    assert "_stop_job()" in app_source


def test_stop_confirmation_closes_when_job_is_not_alive() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "if st.session_state.stop_confirmation_open and not job_alive:" in app_source
    assert "st.session_state.stop_confirmation_open = False" in app_source


def test_session_bootstrap_uses_component_v2_not_v1() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "from streamlit.components.v2 import component as component_v2" in app_source
    assert "_SESSION_STORAGE_COMPONENT = component_v2(" in app_source
    assert "st.components.v1" not in app_source
    assert "window.localStorage" in app_source


def test_session_id_is_not_generated_before_browser_storage_hydrates() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'st.session_state.setdefault("session_id", "")' in app_source
    assert 'st.session_state.setdefault("session_id", generate_safe_id())' not in app_source


def test_session_selector_uses_native_selectbox_and_create_button() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "st.selectbox(" in app_source
    assert 'strings["SESSION_SELECTOR_LABEL"]' in app_source
    assert 'strings["SESSION_CREATE_BUTTON"]' in app_source
    assert "_create_new_session()" in app_source


def test_session_id_is_not_rendered_as_header_caption() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "st.caption(st.session_state.session_id)" not in app_source


def test_session_header_groups_session_controls_left_and_language_right() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'vertical_alignment="center", width="content"' in app_source
    assert 'horizontal_alignment="right"' in app_source
    assert 'st.columns([2.4, 1.2, 1], vertical_alignment="bottom")' not in app_source


def test_downloads_render_separately_from_live_status_area() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "def _render_downloads() -> None:" in app_source
    assert "def _render_live_area() -> None:" in app_source
    assert "_render_status()\n    _render_activity_log()" in app_source
    assert "_render_live_area()\n_render_downloads()" in app_source


def test_download_buttons_use_validated_generated_file_records() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "render_download_tree(build_download_tree(files))" in app_source
    assert "def render_file_download(" not in app_source
    assert ".iterdir()" not in app_source
    assert "file.download_allowed" in app_source


def test_download_rows_include_preview_button_with_eye_icon() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "FILES_PREVIEW_BUTTON" in app_source
    assert 'label=strings["FILES_PREVIEW_BUTTON"]' in app_source
    assert "icon=_PREVIEW_BUTTON_ICON" not in app_source
    assert "_PREVIEW_BUTTON_WIDTH_PX = 44" in app_source
    assert "width=_PREVIEW_BUTTON_WIDTH_PX" in app_source


def test_download_rows_render_preview_before_download_with_small_gap() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    function_start = app_source.index(
        "def render_generated_file_download(file: GeneratedFile) -> None:"
    )
    function_end = app_source.index("\ndef build_download_tree(", function_start)
    function_source = app_source[function_start:function_end]

    assert 'gap="xxsmall"' in function_source
    assert function_source.index("_render_file_preview_button(file)") < function_source.index(
        "if not file.download_allowed"
    )
    assert function_source.index("_render_file_preview_button(file)") < function_source.index(
        "st.download_button("
    )


def test_file_preview_uses_native_dialog_and_preview_helpers() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "def _open_file_preview_dialog(file: GeneratedFile) -> None:" in app_source
    assert "@st.dialog(" in app_source
    assert 'st.session_state.setdefault("preview_file_relative_path", "")' in app_source
    assert "read_text_preview(file.path" in app_source
    assert "is_text_previewable(file.name)" in app_source
    assert "st.session_state.preview_file_relative_path = file.relative_path" in app_source
    assert 'st.session_state.preview_file_relative_path = ""' in app_source
    assert "_render_open_preview_dialog(files)" in app_source
    assert "_render_file_preview_button(file)" in app_source


def test_file_preview_shows_modified_and_created_timestamps_when_available() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "_format_timestamp_utc" in app_source
    assert "FILES_PREVIEW_MODIFIED_AT" in app_source
    assert "FILES_PREVIEW_CREATED_AT" in app_source
    assert "preview_created_timestamp(current_stat)" in app_source


def test_file_preview_uses_scrollable_native_container() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "_PREVIEW_CODE_CONTAINER_HEIGHT_PX = 560" in app_source
    assert "with st.container(height=_PREVIEW_CODE_CONTAINER_HEIGHT_PX):" in app_source
    assert 'st.code(preview.text, language="text", line_numbers=True)' in app_source


def test_preview_state_clears_before_dialog_open() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "selected_file = file_by_relative_path.get(preview_relative_path)" in app_source
    assert (
        'if selected_file is None:\n        st.session_state.preview_file_relative_path = ""'
        in app_source
    )
    assert (
        'st.session_state.preview_file_relative_path = ""\n    _open_file_preview_dialog(selected_file)'
        in app_source
    )


def test_download_buttons_hidden_while_crawl_is_running() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "_job_is_alive(st.session_state.job)" in app_source
    assert '"FILES_DOWNLOADS_IN_PROGRESS"' in app_source


def test_session_storage_js_includes_language_field() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "SUPPORTED_LANGUAGES" in app_source
    assert '"EN"' in app_source
    assert '"ID"' in app_source
    assert "language," in app_source


def test_session_storage_js_reports_write_failures() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert (
        "const storageWriteFailed = pendingRecords.length > 0 && storedPending === false"
        in app_source
    )
    assert 'setStateValue("storage_write_failed", storageWriteFailed)' in app_source


def test_second_status_row_renders_next_url() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'strings["STATUS_NEXT_URL"]' in app_source
    assert "next_url" in app_source


def test_second_status_row_renders_eta() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "format_eta_seconds" in app_source
    assert "eta_remaining_seconds" in app_source


def test_format_eta_seconds_imported_from_support() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "format_eta_seconds," in app_source


def test_eta_ui_does_not_compute_from_processed_elapsed() -> None:
    """Streamlit must not compute ETA from processed/elapsed — only format provided seconds."""
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    # The UI must NOT contain manual ETA math like dividing elapsed by processed_pages
    assert "processed_pages / elapsed" not in app_source
    assert "elapsed / processed_pages" not in app_source


def test_status_row_urls_are_escaped() -> None:
    """Both status rows must use html.escape() on URLs to prevent attribute breakout."""
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    # current_url and next_url both escape via html.escape()
    assert "html.escape(current_url)" in app_source
    assert "html.escape(next_url)" in app_source


def test_status_row_style_uses_constant() -> None:
    """Repeated CSS inline style must use a named constant, not a duplicate literal."""
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "_STATUS_ROW_STYLE" in app_source
    # The literal should not appear directly in the markdown calls
    assert app_source.count("display:flex;justify-content:space-between") == 1


def test_session_storage_js_uses_gte_for_dedup() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "createdAt >= new Date(existing.created_at)" in app_source


def test_select_session_id_restores_language_from_record() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "st.session_state.language = _normalize_language(record.language)" in app_source


def test_on_language_change_updates_pending_records() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "def _on_language_change(widget_key: str) -> None:" in app_source
    assert "pending_browser_session_records" in app_source


def test_language_selector_wires_on_change_callback() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "on_change=_on_language_change" in app_source


def test_language_selector_uses_session_scoped_widget_key() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "def _language_widget_key() -> str:" in app_source
    assert "language_widget_key = _sync_language_widget_state()" in app_source
    assert "key=language_widget_key" in app_source
    assert "args=(language_widget_key,)" in app_source


def test_new_session_bootstrap_waits_for_browser_storage_roundtrip() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert 'st.session_state.setdefault("pending_bootstrap_session_id", "")' in app_source
    assert 'st.session_state.setdefault("session_storage_write_failed", False)' in app_source
    assert "st.session_state.pending_bootstrap_session_id = record.session_id" in app_source
    assert "bootstrap_state = bootstrap_gate_state(" in app_source
    assert 'st.error(strings["ERROR_SESSION_STORAGE_WRITE"])' in app_source
