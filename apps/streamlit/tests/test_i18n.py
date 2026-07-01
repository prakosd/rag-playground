from __future__ import annotations

from crawl4md_streamlit.i18n import (
    CATALOG,
    STRINGS_EN,
    STRINGS_ID,
    Strings,
    get_strings,
    localize_message,
)


def test_get_strings_english() -> None:
    assert get_strings("EN") is STRINGS_EN


def test_get_strings_indonesian() -> None:
    assert get_strings("ID") is STRINGS_ID


def test_get_strings_lowercase_codes() -> None:
    assert get_strings("en") is STRINGS_EN
    assert get_strings("id") is STRINGS_ID


def test_get_strings_unknown_falls_back_to_english() -> None:
    assert get_strings("French") is STRINGS_EN
    assert get_strings("") is STRINGS_EN


def test_catalogs_have_identical_keys() -> None:
    assert STRINGS_EN.keys() == STRINGS_ID.keys()


def test_catalog_keys_match_strings_type() -> None:
    expected = set(Strings.__annotations__)
    assert set(STRINGS_EN) == expected
    assert set(STRINGS_ID) == expected


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


def test_session_control_strings_are_present() -> None:
    for key in (
        "SESSION_LOADING",
        "SESSION_SELECTOR_LABEL",
        "SESSION_CREATE_BUTTON",
        "SESSION_CREATE_BUTTON_TOOLTIP",
        "SESSION_LOAD_BUTTON_TOOLTIP",
        "SESSION_EXTEND_BUTTON_TOOLTIP",
        "TOAST_SESSION_CREATED",
        "TOAST_SESSION_LOADED",
        "TOAST_SESSION_EXTENDED",
        "TOAST_SESSION_EXTEND_FAILED",
    ):
        assert STRINGS_EN[key]
        assert STRINGS_ID[key]


def test_toast_session_loaded_has_id_placeholder() -> None:
    assert "{id}" in STRINGS_EN["TOAST_SESSION_LOADED"]
    assert "{id}" in STRINGS_ID["TOAST_SESSION_LOADED"]


def test_discovered_delta_has_n_and_m_placeholders() -> None:
    for catalog, name in ((STRINGS_EN, "EN"), (STRINGS_ID, "ID")):
        val = catalog["METRIC_DISCOVERED_DELTA"]
        assert "{n}" in val, f"STRINGS_{name}[METRIC_DISCOVERED_DELTA] missing {{n}}"
        assert "{m}" in val, f"STRINGS_{name}[METRIC_DISCOVERED_DELTA] missing {{m}}"


def test_localize_message_falls_back_to_default_text_when_code_unknown() -> None:
    message = {"code": "vector.no_chunks", "text": "No chunks were produced.", "params": {}}
    # EN has no override for this code, so the library default text is returned.
    assert localize_message(STRINGS_EN, message) == "No chunks were produced."


def test_localize_message_uses_language_template_with_params() -> None:
    message = {
        "code": "vector.skipped_unsupported_file",
        "text": "Skipped unsupported file: a.pdf",
        "params": {"file": "a.pdf"},
    }
    localized = localize_message(STRINGS_ID, message)
    assert localized != message["text"]
    assert "a.pdf" in localized


def test_localize_message_browser_missing_is_overridden_in_english() -> None:
    message = {"code": "crawl.browser_missing", "text": "Library default.", "params": {}}
    localized = localize_message(STRINGS_EN, message)
    assert "playwright install --with-deps chromium" in localized


def test_localize_message_bad_params_fall_back_to_default_text() -> None:
    # Template expects {file} but params omit it -> fall back to default text.
    message = {"code": "vector.skipped_unsupported_file", "text": "Skipped a.pdf", "params": {}}
    assert localize_message(STRINGS_ID, message) == "Skipped a.pdf"


def test_processed_retry_delta_has_n_placeholder() -> None:
    for catalog, name in ((STRINGS_EN, "EN"), (STRINGS_ID, "ID")):
        val = catalog["METRIC_PROCESSED_DELTA_RETRY"]
        assert "{n}" in val, f"STRINGS_{name}[METRIC_PROCESSED_DELTA_RETRY] missing {{n}}"


def test_state_labels_cover_known_states() -> None:
    known_states = {"idle", "running", "failed", "completed", "cancel_requested", "stopped"}
    for lang, catalog in CATALOG.items():
        assert known_states.issubset(catalog["STATE_LABELS"].keys()), (
            f"[{lang}] STATE_LABELS is missing some known states"
        )


def test_catalog_contains_both_languages() -> None:
    assert "EN" in CATALOG
    assert "ID" in CATALOG


def test_files_session_caption_has_path_placeholder() -> None:
    assert "{path}" in STRINGS_EN["FILES_SESSION_CAPTION"]
    assert "{path}" in STRINGS_ID["FILES_SESSION_CAPTION"]


def test_files_crawl_result_label_defined() -> None:
    assert STRINGS_EN["FILES_CRAWL_RESULT_LABEL"]
    assert STRINGS_ID["FILES_CRAWL_RESULT_LABEL"]


def test_session_expiry_caption_has_days_placeholder() -> None:
    assert "{days}" in STRINGS_EN["SESSION_EXPIRY_CAPTION"]
    assert "{days}" in STRINGS_ID["SESSION_EXPIRY_CAPTION"]


def test_session_expiry_caption_hours_has_hours_placeholder() -> None:
    assert "{hours}" in STRINGS_EN["SESSION_EXPIRY_CAPTION_HOURS"]
    assert "{hours}" in STRINGS_ID["SESSION_EXPIRY_CAPTION_HOURS"]


def test_session_expiry_caption_singular_and_soon_have_no_placeholder() -> None:
    for key in (
        "SESSION_EXPIRY_CAPTION_SINGULAR",
        "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR",
        "SESSION_EXPIRY_CAPTION_SOON",
    ):
        assert "{" not in STRINGS_EN[key], f"STRINGS_EN[{key!r}] should have no placeholder"
        assert "{" not in STRINGS_ID[key], f"STRINGS_ID[{key!r}] should have no placeholder"


def test_files_download_too_large_has_file_placeholder() -> None:
    assert "{file}" in STRINGS_EN["FILES_DOWNLOAD_TOO_LARGE"]
    assert "{file}" in STRINGS_ID["FILES_DOWNLOAD_TOO_LARGE"]


def test_files_downloads_in_progress_exists_in_all_locales() -> None:
    assert "FILES_DOWNLOADS_IN_PROGRESS" in STRINGS_EN
    assert "FILES_DOWNLOADS_IN_PROGRESS" in STRINGS_ID


def test_files_downloads_subtitle_exists_in_all_locales() -> None:
    assert "FILES_DOWNLOADS_SUBTITLE" in STRINGS_EN
    assert "FILES_DOWNLOADS_SUBTITLE" in STRINGS_ID


def test_files_preview_path_and_size_have_placeholders() -> None:
    assert "{path}" in STRINGS_EN["FILES_PREVIEW_PATH"]
    assert "{size_kib}" in STRINGS_EN["FILES_PREVIEW_SIZE"]
    assert "{path}" in STRINGS_ID["FILES_PREVIEW_PATH"]
    assert "{size_kib}" in STRINGS_ID["FILES_PREVIEW_SIZE"]


def test_files_preview_timestamps_have_value_placeholder() -> None:
    keys = ("FILES_PREVIEW_MODIFIED_AT", "FILES_PREVIEW_CREATED_AT")
    for key in keys:
        assert "{value}" in STRINGS_EN[key]
        assert "{value}" in STRINGS_ID[key]


def test_files_preview_truncated_has_limit_placeholder() -> None:
    assert "{limit_kib}" in STRINGS_EN["FILES_PREVIEW_TRUNCATED"]
    assert "{limit_kib}" in STRINGS_ID["FILES_PREVIEW_TRUNCATED"]


def test_ready_result_zip_subtitle_has_count_placeholder() -> None:
    assert "{count}" in STRINGS_EN["READY_RESULT_ZIP_SUBTITLE"]
    assert "{count}" in STRINGS_ID["READY_RESULT_ZIP_SUBTITLE"]


def test_files_preview_messages_keep_file_placeholder() -> None:
    keys = (
        "FILES_PREVIEW_HELP",
        "FILES_PREVIEW_UNSUPPORTED",
        "FILES_PREVIEW_MISSING",
        "FILES_PREVIEW_READ_ERROR",
        "FILES_PREVIEW_EMPTY",
    )
    for key in keys:
        assert "{file}" in STRINGS_EN[key]
        assert "{file}" in STRINGS_ID[key]


def test_eta_keys_exist_in_all_locales() -> None:
    eta_keys = ("ETA_ESTIMATING", "ETA_LESS_THAN_MINUTE", "ETA_MINUTES", "ETA_HOURS_MINUTES")
    for key in eta_keys:
        assert key in STRINGS_EN, f"STRINGS_EN missing {key!r}"
        assert key in STRINGS_ID, f"STRINGS_ID missing {key!r}"


def test_status_row2_keys_exist_in_all_locales() -> None:
    for key in ("STATUS_NEXT_URL", "PROGRESS_RETRYING"):
        assert key in STRINGS_EN, f"STRINGS_EN missing {key!r}"
        assert key in STRINGS_ID, f"STRINGS_ID missing {key!r}"


def test_progress_attempts_has_n_placeholder() -> None:
    assert "{n}" in STRINGS_EN["PROGRESS_ATTEMPTS"]
    assert "{n}" in STRINGS_ID["PROGRESS_ATTEMPTS"]


def test_eta_minutes_has_n_placeholder() -> None:
    assert "{n}" in STRINGS_EN["ETA_MINUTES"]
    assert "{n}" in STRINGS_ID["ETA_MINUTES"]


def test_eta_hours_minutes_has_h_and_m_placeholders() -> None:
    assert "{h}" in STRINGS_EN["ETA_HOURS_MINUTES"]
    assert "{m}" in STRINGS_EN["ETA_HOURS_MINUTES"]
    assert "{h}" in STRINGS_ID["ETA_HOURS_MINUTES"]
    assert "{m}" in STRINGS_ID["ETA_HOURS_MINUTES"]


def test_status_next_url_has_url_html_placeholder() -> None:
    assert "{url_html}" in STRINGS_EN["STATUS_NEXT_URL"]
    assert "{url_html}" in STRINGS_ID["STATUS_NEXT_URL"]


def test_status_active_fetches_has_count_and_max_placeholders() -> None:
    assert "{count}" in STRINGS_EN["STATUS_ACTIVE_FETCHES"]
    assert "{max}" in STRINGS_EN["STATUS_ACTIVE_FETCHES"]
    assert "{count}" in STRINGS_ID["STATUS_ACTIVE_FETCHES"]
    assert "{max}" in STRINGS_ID["STATUS_ACTIVE_FETCHES"]


def test_status_next_fetches_has_count_placeholder() -> None:
    assert "{count}" in STRINGS_EN["STATUS_NEXT_FETCHES"]
    assert "{count}" in STRINGS_ID["STATUS_NEXT_FETCHES"]


def test_status_more_urls_has_count_placeholder() -> None:
    assert "{count}" in STRINGS_EN["STATUS_MORE_URLS"]
    assert "{count}" in STRINGS_ID["STATUS_MORE_URLS"]
