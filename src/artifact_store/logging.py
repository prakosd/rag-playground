"""Shared logging setup for the rag-playground libraries and apps.

Part of the pure foundation: standard library only. Every library obtains its
logger through :func:`get_logger` and emits records freely; the *application*
(or a notebook) decides the threshold, format, and destinations with a single
:func:`configure_logging` call. Libraries never attach their own output
handlers, so importing a library is silent until an app opts in.

Log lines read ``<datetime> <LEVEL> <logger name> <message>``, for example::

    2026-07-05 11:13:01 INFO crawl4md.crawler Starting crawl of 1 URL (limit 100)

Levels follow the standard threshold model (``DEBUG`` < ``INFO`` < ``WARNING`` <
``ERROR``): configuring at ``WARNING`` shows ``WARNING`` and ``ERROR`` only. The
user-facing ``WARN`` alias is accepted for ``WARNING``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

__all__ = ["DATE_FORMAT", "LOG_FORMAT", "configure_logging", "get_logger"]

# Emitted line layout: datetime, level, logger name, then the message.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Top-level loggers this project owns. configure_logging sets the level and
# attaches handlers here so every child (e.g. ``crawl4md.crawler``) inherits
# them, while third-party logging (chromadb, urllib3, playwright) is left alone.
_PROJECT_LOGGER_NAMES = (
    "artifact_store",
    "crawl4md",
    "vector_indexer",
    "rag_engine",
    "crawl4md_streamlit",
)

# Rotating-file defaults keep the on-disk log bounded without operator tuning.
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 3

# Tags handlers this module installs so a repeated configure_logging call
# (notebooks, tests, or a re-init) replaces them instead of stacking duplicates.
_MANAGED_HANDLER_ATTR = "_rag_playground_managed"


def get_logger(name: str) -> logging.Logger:
    """Return a library logger that stays silent until an app configures logging.

    A :class:`logging.NullHandler` is attached once to the caller's top-level
    project logger, so libraries can log freely without producing output — or
    "No handlers could be found" noise — before any application calls
    :func:`configure_logging`.
    """
    logger = logging.getLogger(name)
    root_logger = logging.getLogger(name.split(".", 1)[0])
    if not any(isinstance(handler, logging.NullHandler) for handler in root_logger.handlers):
        root_logger.addHandler(logging.NullHandler())
    return logger


def _resolve_level(level: int | str) -> int:
    """Return the numeric logging level for an int or (case-insensitive) name."""
    if isinstance(level, bool):  # bool is an int subclass; reject it explicitly.
        raise ValueError(f"Unknown log level: {level!r}")
    if isinstance(level, int):
        return level
    normalized = str(level).strip().upper()
    resolved = logging.getLevelName(normalized)
    if not isinstance(resolved, int):
        raise ValueError(f"Unknown log level: {level!r}")
    return resolved


def configure_logging(
    *,
    level: int | str = "INFO",
    stream: bool = True,
    log_file: Path | str | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure the project loggers to emit at *level* to stderr and/or a file.

    Call once from the application (or a notebook). Safe to call repeatedly: any
    handlers a previous call installed are detached (and file handlers closed)
    first, so a Streamlit rerun never stacks duplicate handlers. Only the
    project's top-level loggers are touched; the root logger and third-party
    loggers are left untouched.

    Args:
        level: Threshold level as a name (``"DEBUG"``/``"INFO"``/``"WARNING"`` or
            ``"WARN"``/``"ERROR"``) or numeric value. Records below it are dropped.
        stream: When True, emit to ``stderr``.
        log_file: When given, also emit to this rotating file (parents created).
        max_bytes: Rotate the file once it reaches this size.
        backup_count: Number of rotated files to retain.
    """
    resolved_level = _resolve_level(level)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    _detach_managed_handlers()

    handlers: list[logging.Handler] = []
    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)
    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    for handler in handlers:
        setattr(handler, _MANAGED_HANDLER_ATTR, True)

    # Attach the same handler instances to every project logger. A record fires
    # only its nearest ancestor's handlers (propagation stops below), so a single
    # shared RotatingFileHandler avoids concurrent-rotation races on one file.
    for logger_name in _PROJECT_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        logger.setLevel(resolved_level)
        for handler in handlers:
            logger.addHandler(handler)
        logger.propagate = False


def _detach_managed_handlers() -> None:
    """Remove and close handlers installed by a previous configure_logging call."""
    detached: set[logging.Handler] = set()
    for logger_name in _PROJECT_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        for handler in [h for h in logger.handlers if getattr(h, _MANAGED_HANDLER_ATTR, False)]:
            logger.removeHandler(handler)
            detached.add(handler)
    for handler in detached:
        # Close file handlers to release the file; never close the stderr stream.
        if isinstance(handler, RotatingFileHandler):
            handler.close()
