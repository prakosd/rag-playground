from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
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
_FIXED_CREATED_AT = datetime(2026, 5, 13, 10, 0, 0, tzinfo=timezone.utc)


def _storage_component_factory(
    *,
    initial_records: list[dict[str, str]] | None = None,
    delay_pending_store: bool = False,
    fail_pending_store: bool = False,
    pending_actions: list[str] | None = None,
):
    browser_records = list(initial_records or [])
    delayed_once = False
    queued_pending_actions = list(pending_actions or [])

    def component_factory(
        name: str,
        *,
        html: str | None = None,
        css: str | None = None,
        js: str | None = None,
        isolate_styles: bool = True,
    ):
        def render(*, data: dict[str, object], **kwargs: object) -> SimpleNamespace:
            nonlocal browser_records, delayed_once
            pending_records = data.get("pendingRecords", [])
            if not isinstance(pending_records, list):
                pending_records = []

            if pending_records:
                if queued_pending_actions:
                    action = queued_pending_actions.pop(0)
                elif fail_pending_store:
                    action = "fail"
                elif delay_pending_store and not delayed_once:
                    action = "delay"
                else:
                    action = "store"

                if action == "fail":
                    return SimpleNamespace(
                        hydrated=True,
                        records=browser_records,
                        stored_records=None,
                        storage_write_failed=True,
                    )
                if action == "delay":
                    delayed_once = True
                    return SimpleNamespace(
                        hydrated=True,
                        records=browser_records,
                        stored_records=None,
                        storage_write_failed=False,
                    )
                if fail_pending_store:
                    raise AssertionError(
                        "fail_pending_store should not be combined with pending_actions"
                    )
                browser_records = serialize_session_records(
                    normalize_session_records([*browser_records, *pending_records])
                )
                return SimpleNamespace(
                    hydrated=True,
                    records=browser_records,
                    stored_records=browser_records,
                    storage_write_failed=False,
                )

            return SimpleNamespace(
                hydrated=True,
                records=browser_records,
                stored_records=None,
                storage_write_failed=False,
            )

        return render

    return component_factory


@contextmanager
def _patched_app_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    component_factory,
    created_record: SessionRecord | None = None,
) -> Iterator[AppTest]:
    monkeypatch.chdir(tmp_path)
    with patch("streamlit.components.v2.component", component_factory):
        if created_record is None:
            yield AppTest.from_file(str(_STREAMLIT_APP_FILE))
            return
        with patch(
            "crawl4md_streamlit.support.create_session_record",
            return_value=created_record,
        ):
            yield AppTest.from_file(str(_STREAMLIT_APP_FILE))


def test_real_app_language_selection_persists_for_active_session_across_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    initial_records = serialize_session_records(
        [
            SessionRecord("active", _FIXED_CREATED_AT, "ID"),
            SessionRecord("other", _FIXED_CREATED_AT.replace(minute=1), "ID"),
        ]
    )
    with _patched_app_test(
        monkeypatch,
        tmp_path,
        component_factory=_storage_component_factory(initial_records=initial_records),
    ) as app:
        app.run(timeout=10)

        assert app.selectbox[0].value == "other"
        assert app.button_group[0].value == "ID"

        app.button_group[0].set_value("EN")
        app.run(timeout=10)

        assert app.selectbox[0].value == "other"
        assert app.button_group[0].value == "EN"

        app.selectbox[0].set_value("active")
        app.run(timeout=10)

        assert app.selectbox[0].value == "active"
        assert app.button_group[0].value == "ID"


def test_real_app_new_session_defaults_to_en_after_storage_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with _patched_app_test(
        monkeypatch,
        tmp_path,
        component_factory=_storage_component_factory(delay_pending_store=True),
        created_record=SessionRecord("bootstrap", _FIXED_CREATED_AT, "EN"),
    ) as app:
        app.run(timeout=10)

        assert app.info[0].value == "Loading browser sessions..."
        assert len(app.selectbox) == 0

        app.run(timeout=10)

        assert app.selectbox[0].value == "bootstrap"
        assert app.button_group[0].value == "EN"
        assert not (tmp_path / "outputs" / "streamlit_sessions").exists()


def test_real_app_shows_error_when_bootstrap_storage_write_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with _patched_app_test(
        monkeypatch,
        tmp_path,
        component_factory=_storage_component_factory(fail_pending_store=True),
        created_record=SessionRecord("bootstrap", _FIXED_CREATED_AT, "EN"),
    ) as app:
        app.run(timeout=10)

        assert app.error[0].value == (
            "Browser storage is unavailable. Enable local storage in this browser and refresh "
            "the page."
        )
        assert len(app.selectbox) == 0
        assert not (tmp_path / "outputs" / "streamlit_sessions").exists()


def test_real_app_retries_language_write_after_same_session_store_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    initial_records = serialize_session_records(
        [
            SessionRecord("active", _FIXED_CREATED_AT, "ID"),
            SessionRecord("other", _FIXED_CREATED_AT.replace(minute=1), "ID"),
        ]
    )
    with _patched_app_test(
        monkeypatch,
        tmp_path,
        component_factory=_storage_component_factory(
            initial_records=initial_records,
            pending_actions=["store", "fail", "store"],
        ),
    ) as app:
        app.run(timeout=10)

        assert app.selectbox[0].value == "other"
        assert app.button_group[0].value == "ID"

        app.button_group[0].set_value("EN")
        app.run(timeout=10)

        assert app.button_group[0].value == "EN"

        app.button_group[0].set_value("ID")
        app.run(timeout=10)

        assert app.button_group[0].value == "ID"

        app.selectbox[0].set_value("active")
        app.run(timeout=10)

        assert app.selectbox[0].value == "active"
        assert app.button_group[0].value == "ID"

        app.selectbox[0].set_value("other")
        app.run(timeout=10)

        assert app.selectbox[0].value == "other"
        assert app.button_group[0].value == "ID"


def test_real_app_switching_session_clears_stale_view_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    initial_records = serialize_session_records(
        [
            SessionRecord("active", _FIXED_CREATED_AT, "EN"),
            SessionRecord("other", _FIXED_CREATED_AT.replace(minute=1), "EN"),
        ]
    )
    with _patched_app_test(
        monkeypatch,
        tmp_path,
        component_factory=_storage_component_factory(initial_records=initial_records),
    ) as app:
        app.run(timeout=10)

        assert app.selectbox[0].value == "other"

        app.session_state["events"] = [{"event": "completed", "processed_pages": 3}]
        app.session_state["latest_event"] = {"event": "completed", "processed_pages": 3}
        app.session_state["active_output_dir"] = (
            "outputs/streamlit_sessions/session_other/crawl_abc"
        )
        app.session_state["activity_log_latest_line"] = "Saved page"
        app.session_state["last_elapsed"] = "0:00:10"
        app.session_state["job_state"] = "failed"
        app.session_state["started_at"] = _FIXED_CREATED_AT
        app.session_state["prev_successful_pages"] = 7
        app.session_state["prev_failed_pages"] = 2
        app.session_state["prev_discovered_pages"] = 11

        app.selectbox[0].set_value("active")
        app.run(timeout=10)

        assert app.selectbox[0].value == "active"
        assert app.session_state["events"] == []
        assert app.session_state["latest_event"] == {}
        assert app.session_state["active_output_dir"] == ""
        assert app.session_state["activity_log_latest_line"] is None
        assert app.session_state["last_elapsed"] == ""
        assert app.session_state["job_state"] == "idle"
        assert app.session_state["started_at"] is None
        assert app.session_state["prev_successful_pages"] == 0
        assert app.session_state["prev_failed_pages"] == 0
        assert app.session_state["prev_discovered_pages"] == 0
