"""Tests for the standalone log4py logging toolkit."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from log4py import _detach_managed_handlers, _resolve_level, configure_logging, get_logger

_TEST_LOGGERS = ("crawl4md", "vector_indexer", "rag_engine")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Snapshot and restore the loggers tests touch (plus root) for isolation."""
    names = ("", *_TEST_LOGGERS)
    saved = {
        name: (
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in names
    }
    try:
        yield
    finally:
        _detach_managed_handlers()
        for name, (handlers, level, propagate) in saved.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.setLevel(level)
            logger.propagate = propagate


def test_get_logger_returns_named_logger() -> None:
    assert get_logger("crawl4md.crawler").name == "crawl4md.crawler"


def test_get_logger_attaches_one_null_handler_to_top_logger() -> None:
    get_logger("crawl4md.crawler")
    get_logger("crawl4md.writer")
    root = logging.getLogger("crawl4md")
    null_handlers = [h for h in root.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1


def test_resolve_level_accepts_names_alias_and_ints() -> None:
    assert _resolve_level("DEBUG") == logging.DEBUG
    assert _resolve_level("warn") == logging.WARNING  # user-facing WARN alias
    assert _resolve_level("WARNING") == logging.WARNING
    assert _resolve_level(logging.ERROR) == logging.ERROR


def test_resolve_level_rejects_unknown_and_bool() -> None:
    with pytest.raises(ValueError):
        _resolve_level("LOUD")
    with pytest.raises(ValueError):
        _resolve_level(True)


def test_configure_logging_sets_threshold_on_named_loggers() -> None:
    configure_logging(level="WARNING", logger_names=_TEST_LOGGERS, stream=False)
    for name in _TEST_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.level == logging.WARNING
        assert logger.propagate is False


def test_configure_logging_stream_attaches_single_stream_handler() -> None:
    configure_logging(level="INFO", logger_names=_TEST_LOGGERS, stream=True)
    handlers = logging.getLogger("crawl4md").handlers
    stream_handlers = [
        h
        for h in handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler)
    ]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].formatter is not None


def test_configure_logging_writes_formatted_line_to_file(tmp_path) -> None:
    log_file = tmp_path / "logs" / "app.log"
    configure_logging(level="INFO", logger_names=_TEST_LOGGERS, stream=False, log_file=log_file)

    get_logger("crawl4md.crawler").info("hello world")

    assert log_file.exists()
    line = log_file.read_text(encoding="utf-8").strip()
    # datetime, level, logger name, message — e.g. "2026-... INFO crawl4md.crawler hello world"
    assert " INFO crawl4md.crawler hello world" in line
    assert line[:4].isdigit()  # starts with a year


def test_configure_logging_threshold_drops_lower_levels(tmp_path) -> None:
    log_file = tmp_path / "app.log"
    configure_logging(level="INFO", logger_names=_TEST_LOGGERS, stream=False, log_file=log_file)

    logger = get_logger("vector_indexer.indexer")
    logger.debug("suppressed debug")
    logger.info("kept info")

    contents = log_file.read_text(encoding="utf-8")
    assert "kept info" in contents
    assert "suppressed debug" not in contents


def test_configure_logging_is_idempotent(tmp_path) -> None:
    log_file = tmp_path / "app.log"
    configure_logging(level="INFO", logger_names=_TEST_LOGGERS, stream=True, log_file=log_file)
    configure_logging(level="INFO", logger_names=_TEST_LOGGERS, stream=True, log_file=log_file)

    handlers = logging.getLogger("crawl4md").handlers
    managed = [h for h in handlers if getattr(h, "_log4py_managed", False)]
    # One stream + one file handler, not stacked across the two calls.
    assert len(managed) == 2


def test_configure_logging_without_names_targets_root(tmp_path) -> None:
    log_file = tmp_path / "app.log"
    configure_logging(level="INFO", logger_names=(), stream=False, log_file=log_file)

    root = logging.getLogger()
    managed = [h for h in root.handlers if getattr(h, "_log4py_managed", False)]
    assert len(managed) == 1


def test_configure_logging_routes_records_to_per_context_files(tmp_path) -> None:
    current = {"name": "a"}

    def router() -> Path:
        return tmp_path / current["name"] / "app.log"

    configure_logging(
        level="INFO", logger_names=_TEST_LOGGERS, stream=False, log_file_router=router
    )
    logger = get_logger("crawl4md.crawler")
    logger.info("first message")
    current["name"] = "b"
    logger.info("second message")

    a_log = (tmp_path / "a" / "app.log").read_text(encoding="utf-8")
    b_log = (tmp_path / "b" / "app.log").read_text(encoding="utf-8")
    assert "first message" in a_log
    assert "second message" not in a_log
    assert "second message" in b_log


def test_configure_logging_router_returning_none_skips_the_file(tmp_path) -> None:
    def router() -> Path | None:
        return None

    configure_logging(
        level="INFO", logger_names=_TEST_LOGGERS, stream=False, log_file_router=router
    )
    get_logger("crawl4md.crawler").info("dropped from file")

    assert not list(tmp_path.rglob("*.log"))
