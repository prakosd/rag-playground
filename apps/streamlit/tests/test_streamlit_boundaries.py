from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STREAMLIT_CONFIG = _REPO_ROOT / ".streamlit" / "config.toml"
_APP_STREAMLIT_CONFIG = _REPO_ROOT / "apps" / "streamlit" / ".streamlit" / "config.toml"
_APP_PAGES_SRC = _REPO_ROOT / "apps" / "streamlit" / "app_pages"
_STREAMLIT_SUPPORT_SRC = _REPO_ROOT / "apps" / "streamlit" / "src" / "app_support"
_PURE_HELPER_MODULES = frozenset(
    {
        "controls.py",
        "crawl_jobs.py",
        "crawl_runtime.py",
        "form_defaults.py",
        "generated_files.py",
        "progress_chart.py",
        "pages.py",
        "session_manager.py",
        "support.py",
    }
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _streamlit_toast_call_lines(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    streamlit_names = {"st", "streamlit"}
    toast_names: set[str] = set()
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "streamlit":
                    streamlit_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "streamlit":
            for alias in node.names:
                if alias.name == "toast":
                    toast_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            is_streamlit_toast_attr = (
                isinstance(func, ast.Attribute)
                and func.attr == "toast"
                and isinstance(func.value, ast.Name)
                and func.value.id in streamlit_names
            )
            is_imported_toast_name = isinstance(func, ast.Name) and func.id in toast_names
            if is_streamlit_toast_attr or is_imported_toast_name:
                lines.append(node.lineno)
    return lines


def test_app_streamlit_config_exists_and_sets_server_defaults() -> None:
    config_text = _APP_STREAMLIT_CONFIG.read_text(encoding="utf-8")

    assert 'address = "0.0.0.0"' in config_text
    assert "port = 8501" in config_text


def test_root_streamlit_config_does_not_exist() -> None:
    assert not _ROOT_STREAMLIT_CONFIG.exists()


def test_pure_helper_modules_do_not_import_streamlit() -> None:
    for path in _STREAMLIT_SUPPORT_SRC.rglob("*.py"):
        if path.name not in _PURE_HELPER_MODULES:
            continue
        for module in _imported_modules(path):
            assert not module.startswith("streamlit"), (
                f"{path.relative_to(_REPO_ROOT)} imports {module!r}"
            )


def test_app_pages_do_not_emit_streamlit_toasts_directly() -> None:
    violations = [
        f"{path.relative_to(_REPO_ROOT)}:{line}"
        for path in sorted(_APP_PAGES_SRC.rglob("*.py"))
        for line in _streamlit_toast_call_lines(path)
    ]

    assert violations == [], (
        "App-wide toasts belong in streamlit_app.py; page modules should request "
        f"shell-owned toasts instead. Direct toast calls found: {violations}"
    )
