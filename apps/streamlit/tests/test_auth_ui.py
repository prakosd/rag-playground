"""Tests for pure helpers in the authentication panel (app_support.auth.auth_ui)."""

from __future__ import annotations

from datetime import datetime, timezone

from app_support.auth.auth_ui import (
    auth_type_label,
    credential_dataframe_rows,
    selected_credential_ids,
)
from app_support.auth.store import CredentialRow
from app_support.i18n.en import STRINGS_EN


def _row(row_id: str, name: str, auth_type: str) -> CredentialRow:
    return CredentialRow(
        id=row_id,
        kind="http",
        name=name,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        auth_type=auth_type,
    )


def test_auth_type_label_bearer() -> None:
    assert auth_type_label("bearer", STRINGS_EN) == STRINGS_EN["AUTH_TYPE_BEARER"]


def test_auth_type_label_basic() -> None:
    assert auth_type_label("basic", STRINGS_EN) == STRINGS_EN["AUTH_TYPE_BASIC"]


def test_auth_type_label_unknown_passes_through() -> None:
    assert auth_type_label("digest", STRINGS_EN) == "digest"


def test_auth_type_label_none_is_empty() -> None:
    assert auth_type_label(None, STRINGS_EN) == ""


def test_credential_dataframe_rows_maps_columns() -> None:
    rows = [_row("a", "Prod", "bearer"), _row("b", "Staging", "basic")]

    data = credential_dataframe_rows(rows, STRINGS_EN)

    assert [entry[STRINGS_EN["AUTH_COL_NAME"]] for entry in data] == ["Prod", "Staging"]
    assert data[0][STRINGS_EN["AUTH_COL_TYPE"]] == STRINGS_EN["AUTH_TYPE_BEARER"]
    assert data[1][STRINGS_EN["AUTH_COL_TYPE"]] == STRINGS_EN["AUTH_TYPE_BASIC"]
    assert data[0][STRINGS_EN["AUTH_COL_CREATED"]]  # a formatted timestamp string


def test_credential_dataframe_rows_handles_missing_created_at() -> None:
    row = CredentialRow(id="a", kind="http", name="X", created_at=None, auth_type="bearer")

    data = credential_dataframe_rows([row], STRINGS_EN)

    assert data[0][STRINGS_EN["AUTH_COL_CREATED"]] == "\u2014"


def test_selected_credential_ids_maps_positions() -> None:
    rows = [_row("a", "A", "bearer"), _row("b", "B", "bearer"), _row("c", "C", "bearer")]

    assert selected_credential_ids([0, 2], rows) == ["a", "c"]


def test_selected_credential_ids_ignores_out_of_range() -> None:
    rows = [_row("a", "A", "bearer")]

    assert selected_credential_ids([0, 5, -1], rows) == ["a"]
    assert selected_credential_ids([], rows) == []
