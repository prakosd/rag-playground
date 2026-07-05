---
description: "Use when editing the log4py package in src/log4py/ or its tests. Covers the pure-stdlib zero-dependency boundary, get_logger/configure_logging contract, idempotent handler management, and per-context file routing."
applyTo: "src/log4py/**, tests/test_log4py*.py"
---

# log4py

The lowest layer of rag-playground: a tiny logging toolkit that every other
package (`artifact_store`, `crawl4md`, `vector_indexer`, `rag_engine`) and the
Streamlit app may import. It exists so libraries only *emit* records while the
application decides threshold, format, and destinations in one place.

## Constraints

- **Zero dependencies, pure stdlib.** `log4py` must not import any project package
  or any third-party library — standard library only. It is the base layer;
  nothing may make it depend upward. A boundary test enforces this.
- **Libraries stay silent by default.** `get_logger(name)` returns a standard
  `logging.Logger` and attaches a single `NullHandler` to the record's top-level
  package logger, so importing a library produces no output until an app calls
  `configure_logging`. Never call `logging.basicConfig`, add output handlers, or
  set levels from a library.
- **Single format.** `LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"`
  and `DATE_FORMAT = "%Y-%m-%d %H:%M:%S"` are the one source of truth. Do not add
  per-call format overrides.
- **Threshold model.** `configure_logging(level=...)` sets one minimum level
  (`DEBUG < INFO < WARNING < ERROR`; `"WARN"` is accepted as an alias via stdlib
  `getLevelName`). Records below it are dropped.
- **Idempotent (Streamlit reruns).** `configure_logging` must be safe to call
  repeatedly. It first detaches (and closes file handlers of) any handler a prior
  call installed — tracked by the `_log4py_managed` marker attribute and the
  `_configured_logger_names` set — then attaches fresh handlers, so a rerun
  replaces rather than stacks handlers. Any new handler type that owns OS
  resources must be closed in `_detach_managed_handlers`.
- **Target selection.** A non-empty `logger_names` isolates the named top-level
  loggers from third-party noise and stops propagation below them; an empty
  selection configures the **root** logger (captures everything). Keep this
  branch intact.
- **Per-context file routing.** `log_file_router` (a `Callable[[], Path | None]`)
  takes precedence over the fixed `log_file`. Its `_RoutingFileHandler` picks a
  destination **per record**: it calls the router, skips the file when it returns
  `None`, and otherwise appends via a per-path cached `RotatingFileHandler`
  (parents created, rotation applied). Router exceptions must be swallowed so a
  logging call never raises into caller code; `close()` must close every cached
  child handler. Callers set the routing context (e.g. a `contextvars.ContextVar`)
  and, because worker threads do not inherit contextvars, must set it inside each
  thread.

## Tests

- Live in `tests/test_log4py.py` and `tests/test_log4py_boundary.py` (run by
  `python -m pytest tests/ -q`, linted by `ruff check src/ tests/`).
- Restore logging state between tests (detach managed handlers, reset
  `propagate`) so `caplog` and other suites are unaffected.
- Cover: `get_logger` attaches exactly one `NullHandler`; `configure_logging`
  sets level + handlers; idempotency (no duplicate handlers after repeated
  calls); routing to per-path files and `None`-skip; the zero-dependency boundary.
- Use `tmp_path` for any file assertions — never write outside the fixture.
