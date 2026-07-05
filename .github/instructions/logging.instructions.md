---
description: "Use when adding or reviewing logging (log4py) in any library or the Streamlit app. Covers logger creation, level choice, message style, and what must never be logged."
applyTo: "src/**, apps/streamlit/**"
---

# Logging (log4py)

All logging goes through the standalone `log4py` package (pure stdlib, the lowest
layer — everything may depend on it). Libraries only *emit* records; the app
decides output. Follow the Python logging HOWTO conventions.

## How to log

- One module-level logger per file, named after the module:
  ```python
  from log4py import get_logger

  _logger = get_logger(__name__)
  ```
  For an app entry script whose `__name__` is `__main__`, pass an explicit name
  under a configured package (e.g. `get_logger("crawl4md_streamlit.app")`).
- Use **`%`-style deferred** formatting — never f-strings or `%`/`.format()`
  pre-formatting: `_logger.info("Indexed %d chunks from %s", n, source)`.
- In an `except` block that handles (does not re-raise) an error, use
  `_logger.exception("...")` to capture the traceback.
- Never call `logging.basicConfig`, add output handlers, or set levels inside a
  library. Configuration is the app's job (`log4py.configure_logging`). `get_logger`
  already attaches a `NullHandler`, so unconfigured use is silent.

## Level guidance

| Level | Use for |
|---|---|
| `DEBUG` | Detailed diagnostics of interest only when troubleshooting: per-item decisions, per-page/-file/-chunk detail, retries, skips, filter matches. |
| `INFO` | Confirmation that a lifecycle step ran, with counts: start/finish of a crawl round, index stage, retrieval, model run. One line per operation, not per item. |
| `WARNING` | Something unexpected but recoverable: fallbacks (proxy/API, echo model), skipped/unreadable files, WAF/blocked pages, cancellations, degraded modes. The operation still completes. |
| `ERROR` | A caught failure that stopped a function (use `_logger.exception` in the handler). Do not also log-and-raise the same error; pick one. |

Keep it low-noise: milestones at INFO, detail at DEBUG. A default `INFO` run should
read as a clean narrative of what happened, not a firehose.

## Never log

Secrets or credentials (proxy auth, API keys, tokens), PII, full prompt text,
user query content, or full document/chunk bodies. Log identifiers, counts,
sizes, model names, and URLs (proxy URLs are logged only as the neutral method
label `proxy`/`api`, never with embedded credentials).

## Structured messages vs logs

`artifact_store.LibraryMessage` (codes for UI localization) and logs are separate
concerns: a `LibraryMessage` is a user-facing warning/error a UI renders; a log is
a developer-facing trace. It is fine to both record a `LibraryMessage` on a result
and log a WARNING/ERROR for the same event — do not substitute one for the other.
