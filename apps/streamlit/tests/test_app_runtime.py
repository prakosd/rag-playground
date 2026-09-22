from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app_support import app_runtime


# Risk: after a crawl/index job finishes, the file-listing cache token (a shallow
# stat of the session root) does not change when the final folders are written two
# levels deeper, so a stale cache hid the outputs until a manual refresh. The
# terminal-transition clear must drop BOTH the listing and the tree cache. Type: unit.
def test_clear_generated_file_caches_clears_both(monkeypatch: pytest.MonkeyPatch) -> None:
    list_cache = MagicMock()
    tree_cache = MagicMock()
    monkeypatch.setattr(app_runtime, "_cached_list_generated_files", list_cache)
    monkeypatch.setattr(app_runtime, "_cached_download_tree", tree_cache)

    app_runtime._clear_generated_file_caches()

    list_cache.clear.assert_called_once()
    tree_cache.clear.assert_called_once()
