from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STREAMLIT_CONFIG = _REPO_ROOT / ".streamlit" / "config.toml"
_APP_STREAMLIT_CONFIG = _REPO_ROOT / "apps" / "streamlit" / ".streamlit" / "config.toml"
_STREAMLIT_APP_FILE = _REPO_ROOT / "apps" / "streamlit" / "streamlit_app.py"


def test_app_streamlit_config_exists_and_sets_server_defaults() -> None:
    config_text = _APP_STREAMLIT_CONFIG.read_text(encoding="utf-8")

    assert 'address = "0.0.0.0"' in config_text
    assert "port = 8501" in config_text


def test_root_streamlit_config_does_not_exist() -> None:
    assert not _ROOT_STREAMLIT_CONFIG.exists()


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

    assert 'if st.button("Keep running", key="stop_cancel_button"):' in app_source
    assert "if st.button(" in app_source
    assert '"Stop crawl",' in app_source
    assert "_stop_job()" in app_source


def test_stop_confirmation_closes_when_job_is_not_alive() -> None:
    app_source = _STREAMLIT_APP_FILE.read_text(encoding="utf-8")

    assert "if st.session_state.stop_confirmation_open and not job_alive:" in app_source
    assert "st.session_state.stop_confirmation_open = False" in app_source
