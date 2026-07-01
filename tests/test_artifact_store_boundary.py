from __future__ import annotations

import ast
from pathlib import Path

import artifact_store

_ARTIFACT_STORE_SRC = Path(__file__).resolve().parents[1] / "src" / "artifact_store"
_FORBIDDEN_IMPORT_PREFIXES = (
    "streamlit",
    "crawl4md_streamlit",
    "crawl4md",
    "crawl4ai",
    "pymupdf",
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


def test_artifact_store_is_a_foundation_with_no_project_dependencies() -> None:
    for path in _ARTIFACT_STORE_SRC.rglob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith(_FORBIDDEN_IMPORT_PREFIXES), (
                f"{path.name} imports {module!r}"
            )


def test_artifact_store_public_api_is_importable() -> None:
    assert "ensure_within_root" in artifact_store.__all__
    assert "list_crawl_result_files" in artifact_store.__all__
    assert "VECTOR_FOLDER_PREFIX" in artifact_store.__all__
    assert "SEARCH_FOLDER_PREFIX" in artifact_store.__all__
