from __future__ import annotations

from crawl4md_streamlit.i18n import (
    CATALOG,
    STRINGS_EN,
    STRINGS_ID,
    get_strings,
)


def test_get_strings_english() -> None:
    assert get_strings("English") is STRINGS_EN


def test_get_strings_indonesian() -> None:
    assert get_strings("Indonesian") is STRINGS_ID


def test_get_strings_unknown_falls_back_to_english() -> None:
    assert get_strings("French") is STRINGS_EN
    assert get_strings("") is STRINGS_EN


def test_catalogs_have_identical_keys() -> None:
    assert STRINGS_EN.keys() == STRINGS_ID.keys()


def test_no_empty_values() -> None:
    for lang, catalog in CATALOG.items():
        for key, value in catalog.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    assert sub_value, f"[{lang}] STATE_LABELS[{sub_key!r}] is empty"
            else:
                assert value, f"[{lang}] key {key!r} is empty"


def test_toast_templates_have_n_placeholder() -> None:
    for key in ("TOAST_SUCCESS", "TOAST_FAILED", "TOAST_DISCOVERED"):
        assert "{n}" in STRINGS_EN[key], f"STRINGS_EN[{key!r}] missing {{n}} placeholder"
        assert "{n}" in STRINGS_ID[key], f"STRINGS_ID[{key!r}] missing {{n}} placeholder"


def test_session_prefix_has_session_id_placeholder() -> None:
    assert "{session_id}" in STRINGS_EN["SESSION_PREFIX"]
    assert "{session_id}" in STRINGS_ID["SESSION_PREFIX"]


def test_discovered_delta_has_n_and_m_placeholders() -> None:
    for catalog, name in ((STRINGS_EN, "EN"), (STRINGS_ID, "ID")):
        val = catalog["METRIC_DISCOVERED_DELTA"]
        assert "{n}" in val, f"STRINGS_{name}[METRIC_DISCOVERED_DELTA] missing {{n}}"
        assert "{m}" in val, f"STRINGS_{name}[METRIC_DISCOVERED_DELTA] missing {{m}}"


def test_state_labels_cover_known_states() -> None:
    known_states = {"idle", "running", "failed", "completed", "cancel_requested", "stopped"}
    for lang, catalog in CATALOG.items():
        assert known_states.issubset(catalog["STATE_LABELS"].keys()), (
            f"[{lang}] STATE_LABELS is missing some known states"
        )


def test_catalog_contains_both_languages() -> None:
    assert "English" in CATALOG
    assert "Indonesian" in CATALOG


def test_files_session_caption_has_path_placeholder() -> None:
    assert "{path}" in STRINGS_EN["FILES_SESSION_CAPTION"]
    assert "{path}" in STRINGS_ID["FILES_SESSION_CAPTION"]
