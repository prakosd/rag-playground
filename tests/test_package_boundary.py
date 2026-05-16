from __future__ import annotations

import ast
import os
import pkgutil
import subprocess
import sys
from pathlib import Path

import crawl4md

_CORE_SRC = Path(__file__).resolve().parents[1] / "src" / "crawl4md"
_STREAMLIT_CONTROL_MODULE = "streamlit_controls"
_STREAMLIT_SUPPORT_MODULE = "streamlit_support"
_FORBIDDEN_CORE_IMPORT_PREFIXES = ("streamlit", "crawl4md_streamlit")
_FORBIDDEN_CORE_SOURCE_STRINGS = (
    "apps/streamlit",
    "crawl4md_streamlit",
    "streamlit_sessions",
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


def test_public_api_excludes_streamlit_helpers() -> None:
    public_exports = set(crawl4md.__all__)

    assert _STREAMLIT_CONTROL_MODULE not in public_exports
    assert _STREAMLIT_SUPPORT_MODULE not in public_exports


def test_core_package_excludes_streamlit_helper_modules() -> None:
    module_names = {module.name for module in pkgutil.iter_modules(crawl4md.__path__)}

    assert _STREAMLIT_CONTROL_MODULE not in module_names
    assert _STREAMLIT_SUPPORT_MODULE not in module_names


def test_package_import_does_not_eagerly_load_crawl_or_pdf_engines() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(_CORE_SRC.parent), env.get("PYTHONPATH", "")) if part
    )
    code = (
        "import sys; import crawl4md; "
        "loaded = [m for m in ('crawl4ai', 'pymupdf', 'pymupdf4llm') if m in sys.modules]; "
        "raise SystemExit(loaded or 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_core_sources_do_not_import_streamlit_app_modules() -> None:
    for path in _CORE_SRC.rglob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith(_FORBIDDEN_CORE_IMPORT_PREFIXES), (
                f"{path.relative_to(_CORE_SRC.parent)} imports {module!r}"
            )


def test_core_sources_do_not_reference_streamlit_app_paths() -> None:
    for path in _CORE_SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower().replace("\\", "/")
        for forbidden in _FORBIDDEN_CORE_SOURCE_STRINGS:
            assert forbidden not in source, (
                f"{path.relative_to(_CORE_SRC.parent)} references {forbidden!r}"
            )
