# Code Review — rag-playground

A whole-project review conducted from the perspective of a **Senior Technical Architect** and
a **Senior Cyber-Security Expert**, across three lenses — **security**, **performance /
memory**, and **convention adherence**. Findings are grouped by severity, each with an
evidence location (`file:line`) and a concrete, **non-breaking** suggested fix.

- **Date:** 2026-11-16
- **Scope:** the 6 libraries under [`src/`](../src), the Streamlit app under
  [`apps/streamlit/`](../apps/streamlit), and the FastAPI backend under
  [`apps/backend/`](../apps/backend).
- **Method:** a delegated, evidence-first pass — security via a dedicated security review,
  performance and conventions via targeted subsystem reviews — synthesised and verified here.
- **Companion doc:** the standing [Security posture](SECURITY.md) records the project's
  pre-existing threat model and audit. This review **extends** it to the new backend offload
  layer and adds the performance + convention lenses. Where a finding overlaps, it is
  cross-linked.

> **Guiding constraint.** Every suggested fix is **additive / behaviour-preserving** and keeps
> the existing local, single-process deployment working. None requires a breaking change.

## Severity legend

| Icon | Severity | Meaning |
|------|----------|---------|
| 🔴 | Critical | Directly exploitable with severe impact; fix now. |
| 🟠 | High | Exploitable issue, data leak, or a leak/degradation in a normal deployment. |
| 🟡 | Medium | Hardening gap, or a problem under load / edge conditions. |
| ⚪ | Low | Defence-in-depth nit, minor inefficiency, or style/convention drift. |

---

## Executive summary

The codebase is **well engineered and already applies strong defence-in-depth** (path
containment on every file input, zip-slip guards, injection-defensive prompts on by default,
OS-trust TLS, HTML-escaped render sinks, bounded thread pools, streaming crawl output, lazy
heavy imports, and a clean library↔app boundary). No `eval`/`exec`/`pickle`/`shell=True` exists
anywhere.

The two issues worth prioritising are **both in the new networked backend** and reinforce each
other: the FastAPI backend ships with **no authentication** ([SEC-H2](#sec-h2-backend-has-no-authentication))
and the crawler applies **no SSRF filtering** to seed URLs ([SEC-H1](#sec-h1-crawler-ssrf-on-seed-urls)).
Together, in a networked deployment, they allow an unauthenticated caller to make the server
fetch cloud-metadata / internal endpoints and exfiltrate the result through the index. The
most impactful performance item is **client-disconnect handling on the backend streaming
paths** ([PERF-H1](#perf-h1-backend-stream-leaks-on-client-disconnect)), where an abandoned
stream can leave a worker thread running against an unbounded queue.

### Fixes applied

Non-breaking, test-backed fixes applied in two passes (full suite green; ruff lint + format
clean). The remaining findings are left as recommendations pending go-ahead, since they
involve product decisions or larger refactors.

**Pass 1 — safe bundle** (low-risk correctness + privacy):

| Finding | Change | Test |
|---------|--------|------|
| [CONV-M1](#conv-m1-query-text-logged-in-libraries) | Log a sub-question / probe **index** instead of the query text | `test_failed_sub_question_is_logged_without_query_text`, `test_failed_probe_is_logged_without_query_text` |
| [PERF-H1](#perf-h1-backend-stream-leaks-on-client-disconnect) | Set `cancel_event` on stream teardown so an abandoned job stops | `test_stream_job_signals_cancel_when_stream_is_abandoned` |
| [PERF-H2](#perf-h2-backend-rag-generators-lack-disconnect-cleanup) | Close the generation iterator in a `finally` on disconnect | `test_generate_closes_model_stream_on_client_disconnect` |
| [PERF-L2](#perf-l2-cleanup-cache-key-churn) | Bound the cleanup `@st.cache_resource` with `max_entries=8` | covered by the existing cleanup suite (config-only) |

**Pass 2 — HIGH security mitigations** (all opt-in / default-off, so local behaviour is unchanged):

| Finding | Change | Test |
|---------|--------|------|
| [SEC-H2](#sec-h2-backend-has-no-authentication) | Optional `X-Backend-Token` shared-secret auth, enforced only when `BACKEND_AUTH_TOKEN` is set; `/health` stays open; the frontend attaches it | `test_auth.py` (5) + `test_http_search_sends_auth_header_when_token_set` |
| [SEC-H1](#sec-h1-crawler-ssrf-on-seed-urls) | Opt-in `block_private_networks` guard resolves each fetched/downloaded host and refuses private/loopback/link-local/metadata targets; the backend can force it on | `test_crawler_ssrf.py` (10) + `test_crawl_forces_ssrf_guard_when_backend_requires_it` |
| [SEC-M1](#sec-m1-arbitrary-js_code-via-backend-crawl) | Backend strips `js_code` from an incoming `page_config` unless `ALLOW_PAGE_SCRIPTS` is set | `test_crawl_strips_js_code_by_default`, `test_crawl_keeps_js_code_when_scripts_allowed` |

---

## Summary — Security

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| [SEC-H1](#sec-h1-crawler-ssrf-on-seed-urls) | 🟠 High | src/crawl4md/config.py · crawler.py | 71-78 · 1204 | Crawler does no SSRF filtering on seed URLs → server-side fetch of cloud-metadata / internal services | 9/10 |
| [SEC-H2](#sec-h2-backend-has-no-authentication) | 🟠 High | apps/backend/app_backend/main.py | 11-26 | FastAPI backend exposes every route with zero authentication | 9/10 |
| [SEC-M1](#sec-m1-arbitrary-js_code-via-backend-crawl) | 🟡 Medium | src/crawl4md/config.py · apps/backend/app_backend/crawl_api.py | 176,183-189 · 64 | Unauthenticated arbitrary JS (`js_code`) runs in the headless browser via backend `/crawl` | 8/10 |
| [SEC-M2](#sec-m2-default-shared-signing-secret) | 🟡 Medium | apps/streamlit/src/app_support/settings.py · auth/crypto.py | 36-40 · 30-38 | Committed default `ZIP_SIGNING_SECRET`, dual-purposed for zip HMAC + credential encryption | 7/10 |
| [SEC-L1](#sec-l1-backend-error-detail-and-headers) | ⚪ Low | apps/backend/app_backend/crawl_api.py · index_api.py | 88 · 84 | Worker error frames surface `str(exc)`; backend sets no HTTP security headers | 6/10 |

## Summary — Performance & memory

| # | Severity | File | Lines | Issue |
|---|----------|------|-------|-------|
| [PERF-H1](#perf-h1-backend-stream-leaks-on-client-disconnect) | 🟠 High | apps/backend/app_backend/job_stream.py | 45-58 | On client disconnect the worker keeps running and fills an unbounded queue (no cancel) |
| [PERF-H2](#perf-h2-backend-rag-generators-lack-disconnect-cleanup) | 🟡 Medium | apps/backend/app_backend/rag_api.py | 245-266 · 290-322 | Streaming RAG generators have no `finally` to close the model stream on disconnect |
| [PERF-M1](#perf-m1-vector-indexer-loads-the-whole-corpus-into-ram) | 🟡 Medium | src/vector_indexer/document_loader.py · chunking.py · indexer.py | 34-86 · 30-62 · 205-209 | Whole corpus is loaded + duplicated in RAM instead of streaming per-document |
| [PERF-M2](#perf-m2-log4py-file-handler-cache-is-unbounded) | 🟡 Medium | src/log4py/__init__.py | 117-132 | Per-path routing handlers accumulate without eviction (fd/memory leak) |
| [PERF-M3](#perf-m3-job-registries-retain-finished-snapshots) | 🟡 Medium | apps/streamlit/.../crawl/crawl_jobs.py · vector_index/vector_index_jobs.py | 117 · 102 | Finished job snapshots linger in the registry until the next job starts |
| [PERF-M4](#perf-m4-worker-event-queues-are-unbounded) | 🟡 Medium | apps/streamlit/.../crawl_jobs.py · vector_index_jobs.py | 450 · 241 | Worker event queues are unbounded if the UI stops draining |
| [PERF-L1](#perf-l1-session-cleanup-runs-on-the-request-thread) | ⚪ Low | apps/streamlit/streamlit_app.py · session_manager.py | 169-183 · 455-495 | Startup `rmtree` sweep runs synchronously on the request thread |
| [PERF-L2](#perf-l2-cleanup-cache-key-churn) | ⚪ Low | apps/streamlit/streamlit_app.py | 168 | Cleanup `@st.cache_resource` has no `max_entries` → key churn |
| [PERF-L3](#perf-l3-extra-float-copy-in-local-embeddings) | ⚪ Low | src/vector_indexer/embeddings/local.py | 53-55 | Rebuilds every vector as a nested Python list (extra full copy) |
| [PERF-L4](#perf-l4-mmr-runs-a-second-similarity-search) | ⚪ Low | src/rag_engine/search.py | 197-206 | MMR runs a second similarity search to recover scores |
| [PERF-L5](#perf-l5-zip-signing-rebuilds-the-archive-in-memory) | ⚪ Low | src/artifact_store/archives.py | 186-196 | `sign_zip_bytes` holds the whole archive in memory (bounded by design) |

## Summary — Conventions

| # | Severity | File | Lines | Issue |
|---|----------|------|-------|-------|
| [CONV-M1](#conv-m1-query-text-logged-in-libraries) | 🟡 Medium | src/rag_engine/retrieval.py · followups.py | 234 · 171 | Library logs user sub-question / follow-up **query text** (violates "never log query text") |
| [CONV-L1](#conv-l1-inline-regex-in-the-markdown-pipeline) | ⚪ Low | src/crawl4md/_internal/markdown_pipeline.py | 176,222,271-285 | A few inline regex literals instead of module-level compiled constants |

---

## Security findings

### SEC-H1: Crawler SSRF on seed URLs

**🟠 High.** The only validation on a seed URL is the `http(s)://` scheme prefix
([config.py:71-78](../src/crawl4md/config.py)); nothing blocks loopback, RFC-1918, or
link-local targets. Seeds are fetched directly ([crawler.py:1204](../src/crawl4md/crawler.py)),
and `url_allowed` ([url_filter.py](../src/crawl4md/_internal/url_filter.py)) only gates the
*discovered* frontier. A crawl of `http://169.254.169.254/latest/meta-data/…` (EC2 IMDSv1) or
`http://169.254.170.2/v2/credentials/…` (ECS task-role creds) is fetched server-side and
written into the session Markdown, then viewable in the UI (in-process mode) or
indexable + retrievable via `/index` → `/rag/search` (backend mode) — a full
SSRF-to-exfiltration chain, triggerable by **any ordinary app user**, not only via the backend.

- **Cross-ref:** [SECURITY.md · M-1](SECURITY.md#m-1-crawler-ssrf--no-private-ip-block). This
  review **raises the practical severity**: M-1 scoped SSRF to shared/hosted deployments, but
  the backend offload now makes the server fetch on behalf of the frontend by default.
- **Fix (non-breaking):** add an opt-out-able guard that resolves each seed/redirect host and
  rejects loopback/private/link-local/ULA/metadata ranges and non-http(s) schemes
  (`ipaddress.ip_address(...).is_private/.is_loopback/.is_link_local` + an explicit
  `169.254.169.254` / `169.254.170.2` block). Default it to "block" for networked deployments;
  pair with IMDSv2 and network egress controls on the infra side.
- **Fix risk:** Medium — needs DNS resolution + redirect re-validation and could block
  legitimate intranet crawls, so it must be a setting (keep current behaviour the default for
  local use, enable "hosted mode" for networked deployments).
- **Status:** ✅ Applied as the opt-in `CrawlerConfig.block_private_networks` guard
  ([ssrf.py](../src/crawl4md/_internal/ssrf.py)), checked before every HTML fetch and document
  download; app toggle `CRAWL_BLOCK_PRIVATE_NETWORKS`, backend force-flag `BLOCK_PRIVATE_NETWORKS`.
  Residual: redirect-target re-validation is not covered — keep network egress controls on
  hosted infra.

### SEC-H2: Backend has no authentication

**🟠 High.** `create_app` ([main.py:11-26](../apps/backend/app_backend/main.py)) wires routers
with no auth dependency, no middleware, and no CORS; every route is a bare `@router.post`
([crawl_api.py:47](../apps/backend/app_backend/crawl_api.py),
[index_api.py:43](../apps/backend/app_backend/index_api.py),
[rag_api.py:178,192,214,247](../apps/backend/app_backend/rag_api.py)). Anyone who can reach the
backend can drive the SSRF above, run arbitrary crawl/index jobs, read/write under the shared
artifacts volume (bounded by containment), and spend the operator's LLM budget via
`/rag/generate` and `/rag/conversational` (which resolve models with server-side credentials).
The app relies entirely on the operator adding auth at the ALB — a fail-open posture.

- **Fix (non-breaking):** add an **optional** shared-secret dependency (compare an
  `X-Backend-Token` header with `hmac.compare_digest` against an env secret) via
  `FastAPI(dependencies=[...])`; enforce **only when the secret env var is set**, so local /
  in-process setups are unaffected. Have
  [backend_client.py](../apps/streamlit/src/app_support/backend_client.py) attach the same
  header when configured. Document that the secret is required for any networked deployment.
- **Fix risk:** Low — additive, gated on an env var, default-off preserves current behaviour.
- **Status:** ✅ Applied ([auth.py](../apps/backend/app_backend/auth.py)) — `BACKEND_AUTH_TOKEN`
  + `X-Backend-Token`, default-off; `/health` stays open; the frontend attaches the header.

### SEC-M1: Arbitrary js_code via backend crawl

**🟡 Medium.** `PageConfig.js_code` accepts arbitrary JS
([config.py:176,183-189](../src/crawl4md/config.py)) that is executed in the Playwright page
([crawler.py:2575-2576](../src/crawl4md/crawler.py)). The backend `/crawl` endpoint validates
an unrestricted `page_config` dict from the request body
([crawl_api.py:64](../apps/backend/app_backend/crawl_api.py)), so on the HTTP path `js_code` is
fully attacker-controlled (it is **not** exposed in the Streamlit form — a backend-only
primitive that compounds [SEC-H2](#sec-h2-backend-has-no-authentication)). Injected JS runs in
the server's headless Chromium, giving a foothold to issue browser-side requests to internal
hosts (amplifying [SEC-H1](#sec-h1-crawler-ssrf-on-seed-urls)).

- **Fix (non-breaking):** largely contained once [SEC-H2](#sec-h2-backend-has-no-authentication)
  auth exists; additionally add a backend setting to reject/ignore `js_code` (and other
  script-injection `page_config` keys) on the HTTP path by default, enabling it only for
  trusted deployments. Keep accepting it for the in-process library caller.
- **Fix risk:** Low — backend-path-only, default-deny of an unused-by-the-UI field.
- **Status:** ✅ Applied — the backend strips `js_code` from an incoming `page_config` unless
  `ALLOW_PAGE_SCRIPTS` is set ([crawl_api.py](../apps/backend/app_backend/crawl_api.py)).

### SEC-M2: Default shared signing secret

**🟡 Medium.** `ZIP_SIGNING_SECRET` ships a committed dev default
([.env.defaults](../.env.defaults), [settings.py:36-40](../apps/streamlit/src/app_support/settings.py))
and is dual-purposed: zip export HMAC **and** deriving the per-session Fernet key for stored
crawl credentials ([auth/crypto.py:30-38](../apps/streamlit/src/app_support/auth/crypto.py)).
If a deployment doesn't override it (only a startup **warning** nudges this), exported zips
become forgeable and stored credentials become decryptable by anyone holding the on-disk
ciphertext + session id.

- **Cross-ref:** already tracked as [SECURITY.md · H-1](SECURITY.md#h-1-shared-default-signing--encryption-secret)
  (mitigated with a warning). Session ids use a CSPRNG, zip-slip containment still holds, and
  `secret_headers`/`proxies` are excluded from serialization — hence Medium, not High.
- **Fix (non-breaking):** keep the dev default for local use but **refuse to start** (or disable
  credential storage + trusted zip import) when a networked indicator is set
  (`backend_mode == "http"`, `storage_backend == "s3"`) **and** the secret still equals the
  shipped default. Optionally split the two roles into separate secrets.
- **Fix risk:** Low — a conditional startup check; no effect on correctly-configured deployments.

### SEC-L1: Backend error detail and headers

**⚪ Low.** Backend worker error frames surface `str(exc)` (message only, no traceback) to the
client ([crawl_api.py:88](../apps/backend/app_backend/crawl_api.py),
[index_api.py:84](../apps/backend/app_backend/index_api.py)), and the backend sets no HTTP
security headers. Both are low and typically handled at the ALB.

- **Fix (non-breaking):** map worker exceptions to a stable `LibraryMessage` code (as the rest
  of the stack does) rather than raw `str(exc)`; add security headers at the proxy.
- **Fix risk:** Low.

---

## Performance & memory findings

### PERF-H1: Backend stream leaks on client disconnect

**🟠 High.** In [job_stream.py:45-58](../apps/backend/app_backend/job_stream.py) the `events`
queue is created with no `maxsize`, and the `frames()` `finally` removes the cancel-registry
entry but **does not set `cancel_event`**. On client disconnect the daemon worker keeps running
the full crawl/index and keeps `events.put(...)`-ing frames nobody drains — the queue grows for
the whole job duration with no consumer.

- **Fix (non-breaking):** in the `finally`, also call `cancel_event.set()` so the worker stops
  cooperatively when the stream is abandoned. (Keep the queue unbounded so the worker never
  blocks at `put()` and can reach its cancel check; a naive `maxsize` could wedge the worker.)
- **Fix risk:** Low — on normal completion the worker has already finished, so setting the event
  is a no-op; on disconnect it is the correct behaviour. Covered by a focused unit test.
- **Status:** ✅ Applied in this pass.

### PERF-H2: Backend RAG generators lack disconnect cleanup

**🟡 Medium.** The `/rag/generate` and `/rag/conversational` `frames()` generators
([rag_api.py:245-266, 290-322](../apps/backend/app_backend/rag_api.py)) have no `finally`; on
client disconnect the underlying `stream_prompt` / `conversational_answer_stream` iterator is
only closed when the generator is GC'd. Under CPython refcounting this is usually prompt, so the
practical impact is small, but explicit cleanup is deterministic.

- **Fix (non-breaking):** wrap the `for piece in generation:` loop in `try/finally` that calls
  `generation.close()` on `GeneratorExit`.
- **Fix risk:** Low — closing an exhausted generator is a no-op.
- **Status:** ✅ Applied in this pass.

### PERF-M1: Vector indexer loads the whole corpus into RAM

**🟡 Medium.** `load_documents` reads every file/zip member fully into a `list[Document]`
([document_loader.py:34-86](../src/vector_indexer/document_loader.py)), `chunk_documents` builds
a complete `list[Chunk]` ([chunking.py:30-62](../src/vector_indexer/chunking.py)), and
`_embed_and_store` materialises `list(_batched(chunks, 32))`
([indexer.py:205-209](../src/vector_indexer/indexer.py)). The full text is resident 2-3×
simultaneously — a RAM spike proportional to total corpus size.

- **Fix (non-breaking):** stream per-document (load → chunk → embed → store one document at a
  time) and iterate `_batched(...)` lazily. The id counter is already global, so per-document
  batching is safe.
- **Fix risk:** Medium — a real refactor of the indexing loop; worth a dedicated change + tests,
  not a drive-by edit.

### PERF-M2: log4py file-handler cache is unbounded

**🟡 Medium.** `_RoutingFileHandler` caches one `RotatingFileHandler` per distinct routed path
and never evicts except on `close()` ([__init__.py:117-132](../src/log4py/__init__.py)). If the
router returns many distinct paths over a long-lived process (e.g. one file per session/day),
open file handles and handler objects grow without bound.

- **Fix (non-breaking):** bound the cache (LRU with a small max, closing evicted handlers).
- **Fix risk:** Low — contained to the routing handler; an evicted-then-reused path simply
  reopens in append mode.

### PERF-M3: Job registries retain finished snapshots

**🟡 Medium.** Pruning of stale (dead-thread) entries happens only inside `_register_and_start_job`
([crawl_jobs.py:118](../apps/streamlit/src/app_support/crawl/crawl_jobs.py),
[vector_index_jobs.py:102](../apps/streamlit/src/app_support/vector_index/vector_index_jobs.py)),
so a completed job's snapshot (holding its queue + `latest_event`) stays resident until someone
starts a **new** job — non-trivial RAM held per terminated job on a long-lived process.

- **Fix (non-breaking):** also prune in the read paths (`get_active_*_snapshot` already detects
  dead threads — drop the entry there), or prune on a timer.
- **Fix risk:** Low.

### PERF-M4: Worker event queues are unbounded

**🟡 Medium.** The crawl/index worker queues are `queue.Queue()` with no `maxsize`
([crawl_jobs.py:450](../apps/streamlit/src/app_support/crawl/crawl_jobs.py),
[vector_index_jobs.py:241](../apps/streamlit/src/app_support/vector_index/vector_index_jobs.py)).
The single consumer is `drain_events` on Streamlit reruns; if the tab closes mid-job the queue
grows for the whole job. The `latest_event` snapshot pattern is good, but the queue still
accumulates every emit.

- **Fix (non-breaking):** give the queue a `maxsize` and coalesce/drop on full, **or** rely on
  the `latest_event` snapshot and periodically clear the backlog in the worker. (Mind the same
  block-at-`put()` caveat as [PERF-H1](#perf-h1-backend-stream-leaks-on-client-disconnect).)
- **Fix risk:** Medium — needs care to avoid wedging the worker; design alongside PERF-M3.

### PERF-L1: Session cleanup runs on the request thread

**⚪ Low.** `cleanup_old_sessions` iterates the sessions root and `rmtree`s whole trees
synchronously ([streamlit_app.py:169-183](../apps/streamlit/streamlit_app.py) →
[session_manager.py:455-495](../apps/streamlit/src/app_support/session_manager.py)); for large/old
trees this can stall the first rerun. **Fix:** offload the sweep to a daemon thread or cap work
per invocation. **Fix risk:** Low-Medium (timing change).

### PERF-L2: Cleanup cache key churn

**⚪ Low.** `_run_startup_cleanup(active_session_ids: tuple)`
([streamlit_app.py:168](../apps/streamlit/streamlit_app.py)) is `@st.cache_resource` keyed per
distinct tuple with no `max_entries`, so keys accumulate as sessions churn (values are `None`).
**Fix:** add `max_entries` or key on a coarser token. **Fix risk:** Low. **Status:** ✅ Applied
in this pass (`max_entries=8`).

### PERF-L3: Extra float copy in local embeddings

**⚪ Low.** `embed_documents` rebuilds every vector as a nested Python list
([local.py:53-55](../src/vector_indexer/embeddings/local.py)), a second full copy of all
vectors per batch. **Fix:** keep numpy arrays / convert lazily. **Fix risk:** Low.

### PERF-L4: MMR runs a second similarity search

**⚪ Low.** `_mmr_hits` calls `max_marginal_relevance_search` then an extra
`similarity_search_with_score(fetch_k)` just to recover distances
([search.py:197-206](../src/rag_engine/search.py)) — roughly doubles cost per MMR query.
Acceptable given the backend API limitation; note only. **Fix risk:** Low (don't change unless
the backend exposes candidate scores).

### PERF-L5: Zip signing rebuilds the archive in memory

**⚪ Low.** `sign_zip_bytes` reads each member and rewrites a new zip into a `BytesIO`
([archives.py:186-196](../src/artifact_store/archives.py)) — inherently in-memory because the
API takes/returns `bytes`. Acceptable for the signed-export use case; note only.

---

## Convention findings

### CONV-M1: Query text logged in libraries

**🟡 Medium.** Two library log calls include user-derived **query text**, which the logging
convention forbids ("never log … prompt/query text"):
[retrieval.py:234](../src/rag_engine/retrieval.py) logs the failing sub-question with `%r`, and
[followups.py:171](../src/rag_engine/followups.py) logs the follow-up probe text with `%r`.

- **Fix (non-breaking):** log a stable position/length instead of the text, e.g.
  `_logger.warning("Retrieval failed for sub-question #%d: %s", idx, exc)` (keep deferred
  `%`-args). Behaviour-preserving — only the log line content changes.
- **Fix risk:** None — logging-only change; recommended for the privacy convention.
- **Status:** ✅ Applied in this pass.

### CONV-L1: Inline regex in the markdown pipeline

**⚪ Low.** A few `re.sub`/`re.match` calls in
[markdown_pipeline.py](../src/crawl4md/_internal/markdown_pipeline.py) (lines 176, 222, 271-285)
and [product_metadata.py:138-141](../src/crawl4md/_internal/product_metadata.py) pass raw
patterns inline rather than module-level compiled constants. Python's internal `re` cache
mitigates this; the surrounding module otherwise follows the convention well (22+ compiled
constants). **Fix:** hoist the repeated patterns to `_UPPER_SNAKE_CASE` compiled constants;
leave genuinely trivial one-offs. **Fix risk:** Low (cosmetic).

---

## Confirmed good practices

The review confirmed a strong baseline, worth preserving:

**Security**
- **Path containment** (`ensure_within_root`, [paths.py:10-22](../src/artifact_store/paths.py))
  on every backend input — `crawl_api`, `index_api` (both `output_base` and each `input_paths`
  entry), and `rag_api._resolve_run_dir`. No traversal gap found.
- **Zip-slip** defended (`is_safe_member_name` + `ensure_within_root`), **HMAC** with
  constant-time compare, and a 50 MiB/member decompression-bomb cap on untrusted members.
- **Prompt-injection prevention on by default** (`ConversationalConfig.injection_prevention`),
  threaded through the conversational pipeline, plus always-on data-fencing of retrieved
  knowledge and conversation history.
- **TLS** via the OS trust store (`truststore`); **no** `verify=False`/`CERT_NONE` anywhere.
- **XSS surface escaped** — all ~42 `unsafe_allow_html` sites route values through
  `html.escape`; untrusted crawl/LLM content renders via `st.write`/`st.code`/`st.markdown`
  **without** `unsafe_allow_html`; the 3D-graph export escapes `<` to prevent `</script>`
  breakout.
- **No dangerous sinks** — no `eval`/`exec`/`os.system`/`shell=True`/`pickle`/`yaml.load`; the
  only `subprocess` call is a fixed-arg `playwright install chromium`.
- **Secrets** kept out of logs and serialization (`secret_headers`/`proxies` are
  `exclude=True, repr=False`).

**Performance**
- **Bounded resource caches** (`max_entries=8` on the chat-model and vector-searcher
  `@st.cache_resource`) and `cache_token=(mtime,size)` invalidation for file reads.
- **Bounded, `with`-managed thread pools** (`max_workers=min(6, len(questions))`), a shared
  warmed searcher reused across workers, **O(n)** chunk dedup via identity hashing, and
  **windowed** conversation history.
- **Streaming crawl output** (size-capped files + JSONL sidecar read back by byte offset),
  **cached** cross-encoder (`@lru_cache(maxsize=1)`) with lazy torch import, and daemonized
  workers that always emit a terminal event / `SENTINEL`.

**Conventions**
- **Clean library↔app boundary** — zero `import streamlit` under `src/`.
- **Lazy heavy imports** in `vector_indexer`/`rag_engine` (sentence-transformers, chromadb kept
  inside functions).
- **Structured `LibraryMessage`** carried end-to-end; the app localises by `code` and never
  substring-matches library text.
- **Logging hygiene** otherwise clean (deferred `%`-args; prompt sizes logged as char counts,
  not content) — except [CONV-M1](#conv-m1-query-text-logged-in-libraries).

---

## Recommended remediation order

1. **[CONV-M1](#conv-m1-query-text-logged-in-libraries)** — stop logging query text (privacy;
   zero-risk, logging-only).
2. **[PERF-H1](#perf-h1-backend-stream-leaks-on-client-disconnect)** /
   **[PERF-H2](#perf-h2-backend-rag-generators-lack-disconnect-cleanup)** — cancel + close the
   stream on client disconnect (small, safe, test-backed).
3. **[SEC-H2](#sec-h2-backend-has-no-authentication)** — optional backend auth token
   (default-off; required for networked deployments).
4. **[SEC-H1](#sec-h1-crawler-ssrf-on-seed-urls)** / **[SEC-M1](#sec-m1-arbitrary-js_code-via-backend-crawl)**
   — opt-in "hosted mode" SSRF guard + backend `js_code` deny (behind a setting).
5. **[PERF-M2](#perf-m2-log4py-file-handler-cache-is-unbounded)**,
   **[PERF-M3](#perf-m3-job-registries-retain-finished-snapshots)**,
   **[PERF-M4](#perf-m4-worker-event-queues-are-unbounded)** — bound the caches/registries/queues.
6. **[PERF-M1](#perf-m1-vector-indexer-loads-the-whole-corpus-into-ram)** — per-document
   streaming in the indexer (dedicated change).
7. **[SEC-M2](#sec-m2-default-shared-signing-secret)** + the ⚪ Low items — hardening and
   micro-optimisations as capacity allows.

## References

- [Security posture](SECURITY.md) · [Cloud deployment](CLOUD_DEPLOYMENT.md) ·
  [AWS deployment](AWS_DEPLOYMENT.md) · [Architecture](ARCHITECTURE.md)
- Conventions: [copilot-instructions.md](../.github/copilot-instructions.md) and
  [.github/instructions/](../.github/instructions)
