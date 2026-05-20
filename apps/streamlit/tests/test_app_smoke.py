from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from crawl4md_streamlit.support import (
    SessionRecord,
    normalize_session_records,
    serialize_session_records,
)

_STREAMLIT_APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def _storage_component_factory(
    name: str,
    *,
    html: str | None = None,
    css: str | None = None,
    js: str | None = None,
    isolate_styles: bool = True,
    initial_records: list[dict[str, str]] | None = None,
    freeze_records: bool = False,
):
    """Mock component factory. freeze_records=True simulates stale component state where
    'records' stays frozen at the hydration-time value after a new session is created."""
    browser_records: list[dict[str, str]] = list(initial_records or [])
    hydration_snapshot: list[dict[str, str]] = list(browser_records)

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
            records=hydration_snapshot if freeze_records else browser_records,
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


# Risk: long single-line preview content can become unreadable if wrapping or horizontal scrolling regresses. Type: UI-flow smoke.
def test_streamlit_preview_keeps_long_lines_unwrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "preview"
    session_root = tmp_path / "outputs" / "streamlit_sessions" / f"session_{session_id}"
    session_root.mkdir(parents=True)
    preview_name = "long_line.txt"
    long_line = "A" * 400
    (session_root / preview_name).write_text(long_line, encoding="utf-8")
    initial_records = serialize_session_records(
        [
            SessionRecord(
                session_id,
                datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
                "EN",
            )
        ]
    )

    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(_storage_component_factory, initial_records=initial_records),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        app.session_state.preview_file_relative_path = preview_name
        app.run(timeout=10)

    assert not app.exception
    assert any(code.value == long_line and code.wrap_lines is False for code in app.code)


# Risk: stale component 'records' with empty pending overwrites browser_session_records,
# causing session_id to revert to old session when Start is clicked. Type: critical flow regression.
def test_new_session_not_reverted_when_component_records_are_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_session_id = "old_abc"
    initial_records = serialize_session_records(
        [SessionRecord(old_session_id, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    )
    monkeypatch.chdir(tmp_path)
    with patch(
        "streamlit.components.v2.component",
        partial(_storage_component_factory, initial_records=initial_records, freeze_records=True),
    ):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)
        assert not app.exception
        assert app.session_state.session_id == old_session_id

        # Simulate what _create_new_session() sets in state (without clicking the real button,
        # which also triggers st.rerun and a pending-confirmation round that clears pending).
        new_session_id = "new_xyz"
        new_record = SessionRecord(
            new_session_id, datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        )
        existing_records = getattr(app.session_state, "browser_session_records", [])
        app.session_state.browser_session_records = normalize_session_records(
            serialize_session_records([new_record, *existing_records])
        )
        app.session_state.session_id = new_session_id
        app.session_state.preferred_session_id = new_session_id
        app.session_state.pending_browser_session_records = []

        # Next run: component returns stale records=[old_abc], pending=[]. Without the fix
        # browser_session_records is overwritten to [old_abc] and session_id reverts.
        app.run(timeout=10)
        assert not app.exception
        assert app.session_state.session_id == new_session_id, (
            f"session_id reverted to old session: got {app.session_state.session_id!r}"
        )
