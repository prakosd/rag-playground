from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from crawl4md_streamlit.support import normalize_session_records, serialize_session_records

_STREAMLIT_APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def _storage_component_factory(
    name: str,
    *,
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
    isolate_styles: bool = True,
):
    browser_records: list[dict[str, str]] = []

    def render(*, data: dict[str, object], **kwargs: object) -> SimpleNamespace:
        nonlocal browser_records
        pending_records = data.get("pendingRecords", [])
        if not isinstance(pending_records, list):
            pending_records = []

        stored_records = None
        if pending_records:
            browser_records = serialize_session_records(
                normalize_session_records([*browser_records, *pending_records])
            )
            stored_records = browser_records

        return SimpleNamespace(
            hydrated=True,
            records=browser_records,
            stored_records=stored_records,
            storage_write_failed=False,
        )

    return render


# Risk: the app can fail during import/bootstrap even when unit helpers pass. Type: smoke.
def test_streamlit_app_starts_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _storage_component_factory):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
