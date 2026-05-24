"""Compatibility exports for Streamlit app support helpers."""

from __future__ import annotations

from crawl4md_streamlit import crawl_jobs as _crawl_jobs
from crawl4md_streamlit import generated_files as _generated_files
from crawl4md_streamlit import session_manager as _session_manager

DEFAULT_ACTIVITY_LOG_SIZE = _crawl_jobs.DEFAULT_ACTIVITY_LOG_SIZE
PLAYWRIGHT_MISSING_BROWSER_MESSAGE = _crawl_jobs.PLAYWRIGHT_MISSING_BROWSER_MESSAGE
CrawlJob = _crawl_jobs.CrawlJob
JobSnapshot = _crawl_jobs.JobSnapshot
ProgressEstimate = _crawl_jobs.ProgressEstimate
active_registry_session_ids = _crawl_jobs.active_registry_session_ids
build_configs = _crawl_jobs.build_configs
drain_events = _crawl_jobs.drain_events
elapsed_time_display = _crawl_jobs.elapsed_time_display
estimate_progress = _crawl_jobs.estimate_progress
format_eta_seconds = _crawl_jobs.format_eta_seconds
format_status_row = _crawl_jobs.format_status_row
format_status_url_preview = _crawl_jobs.format_status_url_preview
get_active_job_snapshot = _crawl_jobs.get_active_job_snapshot
job_state_from_event = _crawl_jobs.job_state_from_event
normalize_event_urls = _crawl_jobs.normalize_event_urls
request_cancel = _crawl_jobs.request_cancel
start_crawl_job = _crawl_jobs.start_crawl_job

GeneratedFile = _generated_files.GeneratedFile
ReadyDownload = _generated_files.ReadyDownload
TextPreview = _generated_files.TextPreview
activity_log_path = _generated_files.activity_log_path
build_ready_download = _generated_files.build_ready_download
find_latest_crawl_dir = _generated_files.find_latest_crawl_dir
find_ready_download_in_session = _generated_files.find_ready_download_in_session
is_text_previewable = _generated_files.is_text_previewable
list_generated_files = _generated_files.list_generated_files
preview_created_timestamp = _generated_files.preview_created_timestamp
read_recent_lines = _generated_files.read_recent_lines
read_text_preview = _generated_files.read_text_preview

DEFAULT_SESSIONS_ROOT = _session_manager.DEFAULT_SESSIONS_ROOT
DEFAULT_SESSION_LANGUAGE = _session_manager.DEFAULT_SESSION_LANGUAGE
SESSION_PREFIX = _session_manager.SESSION_PREFIX
SessionRecord = _session_manager.SessionRecord
bootstrap_gate_state = _session_manager.bootstrap_gate_state
cleanup_old_sessions = _session_manager.cleanup_old_sessions
cleanup_old_sessions_with_lock = _session_manager.cleanup_old_sessions_with_lock
count_crawl_dirs = _session_manager.count_crawl_dirs
crawl_output_base = _session_manager.crawl_output_base
create_session_record = _session_manager.create_session_record
ensure_within_root = _session_manager.ensure_within_root
generate_crawl_id = _session_manager.generate_crawl_id
generate_safe_id = _session_manager.generate_safe_id
latest_session_id = _session_manager.latest_session_id
normalize_session_records = _session_manager.normalize_session_records
prepare_crawl_output_base = _session_manager.prepare_crawl_output_base
prepare_session_dir = _session_manager.prepare_session_dir
serialize_session_records = _session_manager.serialize_session_records
session_dir = _session_manager.session_dir
session_exists = _session_manager.session_exists
session_time_remaining = _session_manager.session_time_remaining
touch_session = _session_manager.touch_session
validate_safe_id = _session_manager.validate_safe_id

__all__ = [
    "CrawlJob",
    "DEFAULT_ACTIVITY_LOG_SIZE",
    "DEFAULT_SESSION_LANGUAGE",
    "DEFAULT_SESSIONS_ROOT",
    "GeneratedFile",
    "JobSnapshot",
    "PLAYWRIGHT_MISSING_BROWSER_MESSAGE",
    "ProgressEstimate",
    "ReadyDownload",
    "SESSION_PREFIX",
    "SessionRecord",
    "TextPreview",
    "active_registry_session_ids",
    "activity_log_path",
    "bootstrap_gate_state",
    "build_configs",
    "build_ready_download",
    "cleanup_old_sessions",
    "cleanup_old_sessions_with_lock",
    "count_crawl_dirs",
    "crawl_output_base",
    "create_session_record",
    "drain_events",
    "elapsed_time_display",
    "ensure_within_root",
    "estimate_progress",
    "find_latest_crawl_dir",
    "find_ready_download_in_session",
    "format_eta_seconds",
    "format_status_row",
    "format_status_url_preview",
    "generate_crawl_id",
    "generate_safe_id",
    "get_active_job_snapshot",
    "is_text_previewable",
    "job_state_from_event",
    "latest_session_id",
    "list_generated_files",
    "normalize_event_urls",
    "normalize_session_records",
    "prepare_crawl_output_base",
    "prepare_session_dir",
    "preview_created_timestamp",
    "read_recent_lines",
    "read_text_preview",
    "request_cancel",
    "serialize_session_records",
    "session_dir",
    "session_exists",
    "start_crawl_job",
    "touch_session",
    "validate_safe_id",
]
