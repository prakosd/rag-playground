from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STREAMLIT_CONFIG = _REPO_ROOT / ".streamlit" / "config.toml"
_APP_STREAMLIT_CONFIG = _REPO_ROOT / "apps" / "streamlit" / ".streamlit" / "config.toml"


def test_app_streamlit_config_exists_and_sets_server_defaults() -> None:
    config_text = _APP_STREAMLIT_CONFIG.read_text(encoding="utf-8")

    assert 'address = "0.0.0.0"' in config_text
    assert "port = 8501" in config_text


def test_root_streamlit_config_does_not_exist() -> None:
    assert not _ROOT_STREAMLIT_CONFIG.exists()
