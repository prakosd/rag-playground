"""Tests for server-side session validation before populating the session selectbox.

Each session ID is unique across tests (prefixed) to avoid @st.cache_data collisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from crawl4md_streamlit.support import (
    SessionRecord,
    serialize_session_records,
)

_STREAMLIT_APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"
_SESSIONS_DIR = Path("outputs") / "streamlit_sessions"


def _make_component_factory(initial_records: list):
    """Minimal component factory that immediately reports hydrated with given records."""
    records = list(initial_records)

    def factory(name: str, *, html=None, css=None, js=None, isolate_styles=True, **kwargs):
        def render(*, data: dict, **kw) -> SimpleNamespace:
            return SimpleNamespace(
                hydrated=True,
                records=records,
                stored_records=None,
                storage_write_failed=False,
            )

        return render

    return factory


def _create_session_dir(root: Path, session_id: str) -> Path:
    d = root / _SESSIONS_DIR / f"session_{session_id}"
    d.mkdir(parents=True)
    return d


# ── happy path ──────────────────────────────────────────────────────────────────


# Risk: sessions that exist on the server must remain selectable. Type: integration.
def test_valid_sessions_kept_in_browser_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_id = "ssv_valid_kept001"
    _create_session_dir(tmp_path, session_id)
    initial_records = serialize_session_records(
        [SessionRecord(session_id, datetime(2026, 5, 1, tzinfo=timezone.utc))]
    )

    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _make_component_factory(initial_records)):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
    record_ids = {r.session_id for r in app.session_state.browser_session_records}
    assert session_id in record_ids
    assert app.session_state.session_ids_to_purge == []


# ── missing session filtered ────────────────────────────────────────────────────


# Risk: stale localStorage entries for deleted sessions pollute the selectbox. Type: integration.
def test_missing_server_session_removed_from_browser_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    valid_id = "ssv_valid_mix002"
    ghost_id = "ssv_ghost_mix002"
    _create_session_dir(tmp_path, valid_id)
    # ghost directory deliberately not created
    initial_records = serialize_session_records(
        [
            SessionRecord(valid_id, datetime(2026, 5, 1, tzinfo=timezone.utc)),
            SessionRecord(ghost_id, datetime(2026, 5, 2, tzinfo=timezone.utc)),
        ]
    )

    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _make_component_factory(initial_records)):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
    record_ids = {r.session_id for r in app.session_state.browser_session_records}
    assert valid_id in record_ids
    assert ghost_id not in record_ids


# Risk: ghost session IDs must reach the JS component so it can remove them from localStorage.
# Type: integration.
def test_missing_server_session_added_to_purge_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    valid_id = "ssv_valid_purge003"
    ghost_id = "ssv_ghost_purge003"
    _create_session_dir(tmp_path, valid_id)
    initial_records = serialize_session_records(
        [
            SessionRecord(valid_id, datetime(2026, 5, 1, tzinfo=timezone.utc)),
            SessionRecord(ghost_id, datetime(2026, 5, 2, tzinfo=timezone.utc)),
        ]
    )

    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _make_component_factory(initial_records)):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
    assert ghost_id in app.session_state.session_ids_to_purge
    assert valid_id not in app.session_state.session_ids_to_purge


# Risk: if all localStorage sessions are missing (e.g. server was reset), the app must still boot
# cleanly and not crash. Type: robustness smoke.
def test_app_boots_cleanly_when_all_localStorage_sessions_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ghost_id = "ssv_ghost_allgone004"
    # no session directories created
    initial_records = serialize_session_records(
        [SessionRecord(ghost_id, datetime(2026, 5, 1, tzinfo=timezone.utc))]
    )

    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", _make_component_factory(initial_records)):
        app = AppTest.from_file(str(_STREAMLIT_APP_FILE))
        app.run(timeout=10)

    assert not app.exception
    assert ghost_id not in {r.session_id for r in app.session_state.browser_session_records}
    assert ghost_id in app.session_state.session_ids_to_purge
