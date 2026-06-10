# artifact_store

Shared, UI-agnostic foundation for managing persisted project artifacts. It is the
lowest layer in the repository: the `crawl4md` core library, the `vector_indexer`
library, and the Streamlit app all build on it. It depends on the Python standard
library only — no crawler, no UI, no third-party packages.

## Why it exists

Crawl outputs, uploaded files, and vector indexes all need the same primitives:
consistent timestamped folder names, safe path handling, and safe archive reading.
`artifact_store` keeps that logic in one place so every producer and consumer stays
consistent and no module re-implements (or diverges on) naming or path safety.

## Modules

| Module | Responsibility |
|---|---|
| `naming.py` | Single source of truth for the UTC timestamp slug, the `crawl_` / `vector_` folder prefixes, and generic sequence helpers (`format_sequence_id`, `folder_name`, `parse_folder_sequence`, `sequence_sort_key`). `crawl4md.naming` re-exports these. |
| `paths.py` | `ensure_within_root(root, path)` — the directory-traversal guard used before any file read or write. |
| `archives.py` | Zip-slip-safe extraction of `.md` / `.txt` members only (`iter_text_members`, `extract_text_members`, `is_safe_member_name`). |
| `crawl_results.py` | `list_crawl_result_files(session_root)` — discover a crawl's success content, preferring the final sorted output and falling back to `round_N/` snapshots for stopped crawls. |

## Examples

```python
from artifact_store import (
    format_utc_timestamp_slug,
    VECTOR_FOLDER_PREFIX,
    folder_name,
    ensure_within_root,
    iter_text_members,
    list_crawl_result_files,
)

run_dir = folder_name(VECTOR_FOLDER_PREFIX, "01_navigate")  # "vector_01_navigate"
slug = format_utc_timestamp_slug()                          # "2026-06-01_12-09-15"

# Reject paths that escape a root before reading/writing
safe = ensure_within_root("outputs/session_x", "outputs/session_x/final/a.md")

# Read only the .md/.txt members of an uploaded zip, skipping unsafe names
for name, data in iter_text_members("uploaded.zip"):
    ...

# List indexable crawl outputs for a session
files = list_crawl_result_files("outputs/streamlit_sessions/session_x")
```

## Boundary

A test asserts `artifact_store` imports nothing from `streamlit`, `crawl4md_streamlit`,
`crawl4md`, `crawl4ai`, or `pymupdf`. Keep it that way: this package must remain a
dependency-free foundation that any future library or UI can reuse.
