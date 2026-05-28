from __future__ import annotations

from pathlib import Path

from crawl4md_streamlit import crawl_jobs, generated_files, session_manager, support

_EXPECTED_FACADE_EXPORTS = {
    "CrawlJob": crawl_jobs.CrawlJob,
    "DEFAULT_ACTIVITY_LOG_SIZE": crawl_jobs.DEFAULT_ACTIVITY_LOG_SIZE,
    "DEFAULT_SESSION_LANGUAGE": session_manager.DEFAULT_SESSION_LANGUAGE,
    "DEFAULT_SESSIONS_ROOT": session_manager.DEFAULT_SESSIONS_ROOT,
    "GeneratedFile": generated_files.GeneratedFile,
    "JobSnapshot": crawl_jobs.JobSnapshot,
    "PLAYWRIGHT_MISSING_BROWSER_MESSAGE": crawl_jobs.PLAYWRIGHT_MISSING_BROWSER_MESSAGE,
    "ProgressEstimate": crawl_jobs.ProgressEstimate,
    "ReadyDownload": generated_files.ReadyDownload,
    "SESSION_PREFIX": session_manager.SESSION_PREFIX,
    "SessionRecord": session_manager.SessionRecord,
    "TextPreview": generated_files.TextPreview,
    "active_registry_session_ids": crawl_jobs.active_registry_session_ids,
    "activity_log_path": generated_files.activity_log_path,
    "bootstrap_gate_state": session_manager.bootstrap_gate_state,
    "build_configs": crawl_jobs.build_configs,
    "build_ready_download": generated_files.build_ready_download,
    "cleanup_old_sessions": session_manager.cleanup_old_sessions,
    "cleanup_old_sessions_with_lock": session_manager.cleanup_old_sessions_with_lock,
    "count_crawl_dirs": session_manager.count_crawl_dirs,
    "crawl_output_base": session_manager.crawl_output_base,
    "create_session_record": session_manager.create_session_record,
    "drain_events": crawl_jobs.drain_events,
    "elapsed_time_display": crawl_jobs.elapsed_time_display,
    "ensure_within_root": session_manager.ensure_within_root,
    "estimate_progress": crawl_jobs.estimate_progress,
    "find_latest_crawl_dir": generated_files.find_latest_crawl_dir,
    "find_ready_download_in_session": generated_files.find_ready_download_in_session,
    "format_eta_seconds": crawl_jobs.format_eta_seconds,
    "format_status_row": crawl_jobs.format_status_row,
    "format_status_url_preview": crawl_jobs.format_status_url_preview,
    "generate_crawl_id": session_manager.generate_crawl_id,
    "generate_safe_id": session_manager.generate_safe_id,
    "get_active_job_snapshot": crawl_jobs.get_active_job_snapshot,
    "is_text_previewable": generated_files.is_text_previewable,
    "job_state_from_event": crawl_jobs.job_state_from_event,
    "latest_session_id": session_manager.latest_session_id,
    "normalize_event_urls": crawl_jobs.normalize_event_urls,
    "list_generated_files": generated_files.list_generated_files,
    "normalize_session_records": session_manager.normalize_session_records,
    "prepare_crawl_output_base": session_manager.prepare_crawl_output_base,
    "prepare_session_dir": session_manager.prepare_session_dir,
    "preview_created_timestamp": generated_files.preview_created_timestamp,
    "read_recent_lines": generated_files.read_recent_lines,
    "read_text_preview": generated_files.read_text_preview,
    "request_cancel": crawl_jobs.request_cancel,
    "serialize_session_records": session_manager.serialize_session_records,
    "session_dir": session_manager.session_dir,
    "session_exists": session_manager.session_exists,
    "should_show_portfolio_modal": session_manager.should_show_portfolio_modal,
    "start_crawl_job": crawl_jobs.start_crawl_job,
    "touch_session": session_manager.touch_session,
    "validate_safe_id": session_manager.validate_safe_id,
}


def _assert_same_export(actual: object, expected: object) -> None:
    if isinstance(expected, (str, int, Path)):
        assert actual == expected
        return
    assert actual is expected


def test_support_facade_reexports_split_helper_symbols() -> None:
    assert set(support.__all__) == set(_EXPECTED_FACADE_EXPORTS)
    for name, expected in _EXPECTED_FACADE_EXPORTS.items():
        _assert_same_export(getattr(support, name), expected)
