from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STREAMLIT_CONFIG = _REPO_ROOT / ".streamlit" / "config.toml"
_APP_STREAMLIT_CONFIG = _REPO_ROOT / "apps" / "streamlit" / ".streamlit" / "config.toml"
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
