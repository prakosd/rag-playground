from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING
from crawl4md import messages
from crawl4md._internal.crawler_progress import emit_crawl_warning


def test_blocked_backoff_carries_wait_seconds() -> None:
    message = messages.blocked_backoff(12.4)
    assert message.code == messages.CODE_BLOCKED_BACKOFF
    assert message.severity == SEVERITY_WARNING
    assert message.params["wait_seconds"] == 12.4
    assert "12" in str(message)


def test_ocr_unavailable_is_a_warning() -> None:
    message = messages.ocr_unavailable()
    assert message.code == messages.CODE_OCR_UNAVAILABLE
    assert message.severity == SEVERITY_WARNING


def test_classify_crawl_error_detects_missing_browser() -> None:
    detail = "BrowserType.launch: Executable doesn't exist at /ms-playwright/chromium"
    message = messages.classify_crawl_error(detail)
    assert message.code == messages.CODE_BROWSER_MISSING
    assert message.severity == SEVERITY_ERROR


def test_classify_crawl_error_detects_missing_engine() -> None:
    message = messages.classify_crawl_error("No module named 'crawl4ai'")
    assert message.code == messages.CODE_ENGINE_MISSING
    assert "rag-playground[crawl]" in str(message)


def test_classify_crawl_error_detects_ssl() -> None:
    message = messages.classify_crawl_error("SSLError: certificate_verify_failed")
    assert message.code == messages.CODE_SSL_CERTIFICATE


def test_classify_crawl_error_falls_back_to_generic() -> None:
    message = messages.classify_crawl_error("connection reset by peer")
    assert message.code == messages.CODE_CRAWL_FAILED
    assert "connection reset by peer" in str(message)


def test_emit_crawl_warning_builds_structured_event() -> None:
    captured: list[dict[str, object]] = []
    event = emit_crawl_warning(captured.append, messages.ocr_unavailable())

    assert event["event"] == "crawl_warning"
    assert event["code"] == messages.CODE_OCR_UNAVAILABLE
    assert event["severity"] == "warning"
    assert captured == [event]


def test_emit_crawl_warning_without_callback_is_noop() -> None:
    event = emit_crawl_warning(None, messages.blocked_backoff(1.0))
    assert event["code"] == messages.CODE_BLOCKED_BACKOFF
