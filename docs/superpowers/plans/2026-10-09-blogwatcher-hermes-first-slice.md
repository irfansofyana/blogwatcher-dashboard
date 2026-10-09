# Blogwatcher Hermes Companion First Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a testable CLI-backed Blogwatcher inbox and source controls inside both Hermes UI surfaces, plus agent-facing tools.

**Architecture:** A single Python CLI adapter is used by agent plugin handlers and an authenticated FastAPI dashboard router. Separate Desktop and web SDK entrypoints consume a stable JSON response; neither executes CLI or accesses SQLite.

**Tech Stack:** Python 3 standard library, Hermes plugin API/FastAPI, plain ESM for Desktop, plain React via Hermes web SDK, unittest, Node syntax checks.

**Spec:** `docs/superpowers/specs/2026-10-09-blogwatcher-hermes-design.md`

## Global Constraints

- Original `Hyaxia/blogwatcher` only; honor `BLOGWATCHER_DB`, no direct SQLite access or shell execution.
- Mutations only for supported commands: add/remove, scan, read/unread/read-all; no source edit or article delete.
- No separate web server, automatic AI summary, or custom chat client in this slice.
- Test CLI writes with an isolated database, never the user's data.

## Review Focus

- A source name with quotes/semicolons must remain one argv element; adapter test.
- A missing CLI, timeout, or nonzero exit must return an error rather than an empty list; adapter test.
- A malformed/changed article listing must fail closed rather than silently omit entries; parser test.
- A destructive remove/read-all must require explicit UI confirmation; UI review and route test.
- A URL/title containing HTML must render escaped as text, not markup; UI review.

---

### Task 1: CLI adapter and parser

**Files:** `blogwatcher_core.py`, `tests/test_core.py`.
**Interfaces:** `BlogwatcherCLI(binary=None, database=None).blogs()`, `.articles(all_articles=False, blog=None)`, `.add(name,url,feed_url=None,scrape_selector=None,user_agent=None)`, `.remove(name)`, `.scan(blog=None)`, `.read(id)`, `.unread(id)`, `.read_all(blog=None)` return JSON-safe dict/list; `BlogwatcherError` identifies failure.

- [ ] Write failing tests with a temporary executable fake CLI for article/source parsing, stdout cap, safe argv, and errors. Example: `self.assertEqual(cli.articles()[0]['title'], 'Hello')` for an output block with `[42] [new] Hello`.
- [ ] Run `python -m unittest tests.test_core -v`; inspect expected missing-module failure.
- [ ] Implement the smallest adapter using `subprocess.run([binary,*args], shell=False, timeout=...)`, bounded output, strict record parsing and exact command allowlist.
- [ ] Run the targeted tests, then `python -m unittest discover -s tests -v`.
- [ ] Commit only this tested task.

### Task 2: Backend HTTP and agent tools

**Files:** `dashboard/plugin_api.py`, `dashboard/manifest.json`, `plugin.yaml`, `__init__.py`, `tests/test_plugin.py`.
**Interfaces:** FastAPI router mounted at `/api/plugins/hermes-blogwatcher/`; JSON responses `GET /articles`, `GET /blogs`, POST `/blogs`, `/blogs/remove`, `/scan`, `/articles/read`, `/articles/unread`, `/articles/read-all`. Agent tool handlers expose only bounded, read-only article/source listing.

- [ ] Write tests for request validation and handler delegation against the isolated fake CLI; a bad article id must yield a client error without CLI invocation.
- [ ] Run `python -m unittest tests.test_plugin -v` and verify failure due to missing route/handler.
- [ ] Implement FastAPI route handlers, explicit validation and safe error responses; register agent tools with narrow JSON schemas and allowlisted handlers.
- [ ] Run targeted and full tests; validate manifest JSON and plugin loader.
- [ ] Commit only this tested task.

### Task 3: Hermes web and Desktop surfaces

**Files:** `dashboard/dist/index.js`, `desktop/plugin.js`, `dashboard/style.css`, `tests/test_ui_contract.py`.
**Interfaces:** Same backend API as Task 2; page renders inbox, filters, source list/add/remove, scan, read/unread/read-all with confirmation on bulk/destructive operations.

- [ ] Write failing UI contract tests checking expected SDK entrypoints and API routes before writing JS.
- [ ] Run targeted test and observe failure.
- [ ] Build native web tab and Desktop page using each supported SDK; reuse layout and copy, never assume their JS components are interchangeable.
- [ ] Run JS syntax checks and tests; exercise both surfaces in running Hermes, otherwise report that gap explicitly.
- [ ] Commit only this tested task.

### Task 4: Installation and isolated real-CLI verification

**Files:** `README.md`, `tests/test_real_cli.py`.
**Interfaces:** Install via Hermes plugin package directory; document enable switches and required CLI on same host.

- [ ] Write a failing isolated real-CLI test (skip if CLI absent), using `BLOGWATCHER_DB` in a temporary directory and a local RSS fixture.
- [ ] Run and inspect failure, then wire fixture and supported actions.
- [ ] Test the real CLI, whole unittest suite, `node --check` for JS, and Hermes plugin validation. Document only verified behavior and explicitly list remaining integration gaps.
- [ ] Commit the tested task; optionally publish a branch/PR only after review of external effects.
