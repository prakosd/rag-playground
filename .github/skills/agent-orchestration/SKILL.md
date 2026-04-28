---
name: agent-orchestration
description: "Plan and execute multi-step work by delegating to specialized subagents. Use when: writing a plan, breaking down a non-trivial task, coordinating exploration + implementation + verification, deciding what to delegate vs do inline, working with smaller models (Claude Sonnet 4.6 / Haiku) that benefit from narrow subtasks."
---

# Agent Orchestration

## Core Idea

**Agent orchestration** is the practice of decomposing a task into smaller, well-scoped subtasks and assigning each to a specialized agent (subagent) that runs in isolation, then combining their outputs into a coherent result.

The orchestrator (the main agent) does three things:

1. **Decompose** — split the task into independent or sequential subtasks small enough that a smaller model can execute each one reliably.
2. **Delegate** — hand each subtask to the agent best suited for it (read-only exploration, test execution, code review, etc.). Each subagent has its own context window, so noise from one subtask does not pollute the others.
3. **Integrate** — collect each subagent's single final report and combine them into the user-facing result or the next step of the plan.

This matters because smaller models (Claude Sonnet 4.6, Haiku) execute narrow, well-defined tasks far more reliably than broad, ambiguous ones. Orchestration trades a bit of coordination overhead for much higher per-step success rates.

## Patterns

| Pattern | When to use | Example in crawl4md |
|---|---|---|
| **Sequential pipeline** | Each step depends on the previous one | `Explore` (find files) → implement → `test-runner` (verify) |
| **Parallel fan-out** | Independent reads/searches | Two `Explore` calls in parallel: one for `extractor.py`, one for `crawler.py` |
| **Supervisor / worker** | Main agent plans + integrates; workers execute narrow tasks | Orchestrator writes the plan; `test-runner` runs tests; `code-reviewer` reviews diff |
| **Critique loop** | Generate then review/refine | Implement change → `code-reviewer` critiques → apply fixes |

## Available Subagents in This Project

- **`Explore`** — read-only codebase Q&A and file discovery. Use instead of chaining many `grep_search` / `read_file` calls. Specify thoroughness: quick / medium / thorough.
- **`test-runner`** — runs pytest + ruff and returns a structured report. Use to verify any code change.
- **`code-reviewer`** — reviews a diff or file set against the project's "clean, lightweight, not bloated" bar. Use before declaring a task complete.

## When to Delegate vs Do Inline

**Delegate to a subagent when:**

- The subtask would consume many tool calls (>~5 searches/reads) — keeps the main context clean.
- The subtask benefits from a fresh perspective (e.g., review).
- The subtask has a narrow, well-defined deliverable (e.g., "list every place `_FALLBACK_WAIT_UNTIL` is referenced").
- Multiple independent searches can run in parallel.

**Do inline when:**

- A single read or search is enough.
- The work is interactive editing of one file you already understand.
- The result is trivial.

## Writing Plans That Use Orchestration

Every non-trivial plan in this project must:

1. Be **understandable by Claude Sonnet 4.6** — clear, simple, short steps; no jargon; no implicit context. Each step should be executable on its own.
2. **Explicitly call out which steps delegate to a subagent** and which agent. Example: *"Step 3: delegate to `Explore` (medium) to map all callers of `FileWriter.flush()`."*
3. **Combine subagent outputs deliberately** — name the integration step. Example: *"Step 5: merge findings from steps 2 and 3 to identify the regex to update."*
4. **End with verification** — final step is almost always `test-runner`.

## Anti-Patterns

- **Mega-step plans** ("Step 1: implement the feature"). Break it down.
- **Delegating trivial work** (one `grep_search` does not need an `Explore` call).
- **Parallel calls with hidden dependencies** — only parallelize truly independent subtasks.
- **Letting a subagent's intermediate reasoning leak into the user-facing result** — only the integrated outcome matters to the user.
