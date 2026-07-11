from __future__ import annotations

import ast
from pathlib import Path

import log4py

_LOG4PY_SRC = Path(__file__).resolve().parents[1] / "src" / "log4py"
# log4py is the lowest layer: it must not import any project package, so nothing
# can ever depend on it *and* have it depend back (no import cycles).
_FORBIDDEN_IMPORT_PREFIXES = (
    "artifact_store",
    "crawl4md",
    "app_support",
    "vector_indexer",
    "rag_engine",
    "streamlit",
    "pydantic",
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


def test_log4py_is_a_zero_dependency_foundation() -> None:
    for path in _LOG4PY_SRC.rglob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith(_FORBIDDEN_IMPORT_PREFIXES), (
                f"{path.name} imports {module!r}"
            )


def test_log4py_public_api_is_importable() -> None:
    assert "get_logger" in log4py.__all__
    assert "configure_logging" in log4py.__all__
