# Reliable Article Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Article detail panels with explicitly requested, trustworthy summaries on both Hermes surfaces.
**Architecture:** Shared VPS-side article lookup, bounded safe extraction, host-managed model invocation and profile-scoped result cache. Thin native Desktop/web panels; no changes to Hermes core or Blogwatcher storage.
**Tech Stack:** Python/FastAPI, Hermes plugin ctx.llm, HTTPS client with pinned destination/TLS verification, article extraction library, Hermes React plugin SDKs, Python unittest and Node behavioral tests.
**Spec:** docs/superpowers/specs/2026-10-09-article-summary-design.md

## Global Constraints
- HTTP(S) only; reject private, loopback, link-local, multicast, reserved and unspecified IPv4/IPv6, including mapped addresses.
- At most 3 redirects; 20-second fetch wall-clock deadline; maximum decoded response 2 MiB; maximum model input 30000 characters.
- Model timeout 60 seconds; maximum output 800 tokens; no tools or automatic paid retries.
- Successful-result cache 7 days, maximum 50 MiB; at most 2 concurrent generations per profile.
- No Hermes core patches, renderer credentials, direct provider clients or Blogwatcher SQLite writes.
- No live install/restart or merge without user approval.

## Review Focus
- DNS rebinding: validate and connect to the same resolved IP, preserving TLS hostname checks.
- Cross-profile data: article identity, model configuration, cache and work ownership must follow the request profile.
- Late results: switching article/connection must not paint the previous summary into a new selection.
- Unknown generation outcome: disconnect/timeout must not silently retry a paid call.
- Partial publisher content: extracted/truncated coverage must be explicit; no completeness guarantee.

### Task 1 — Prove the host-owned LLM bridge
**Files:** tests/test_summary_bridge.py, summary_bridge.py, __init__.py, dashboard/plugin_api.py.
**Contract:** `summarize_text(text, source_url)` returns model text, model/provider and usage using plugin-scoped `ctx.llm`, or a typed capability-unavailable error. No credentials or arbitrary provider overrides.
- [ ] Write a failing integration test loading the real plugin through a temporary HERMES_HOME, with plugins.isolation=host; HTTP route must invoke the plugin-scoped context. Assert `result['provider']` and nonempty `result['text']` only on a genuine successful call.
- [ ] Run the isolated bridge test and record the failing path. Dashboard API imports are separate modules and do not receive ctx automatically; do not rely on import-time shared globals.
- [ ] Implement the supported context handoff within the package. If the host does not offer a supported route-to-context contract, stop with a concrete missing-capability finding; do not bypass host credential ownership.
- [ ] Exercise an explicit tiny live inference call, record actual model/provider, then run the plugin validator. Commit only after the bridge is proven.

### Task 2 — Safe article lookup and retrieval
**Files:** article_content.py, tests/test_article_content.py, dashboard/plugin_api.py.
**Contracts:** `get_article(article_id)` resolves existing CLI records; `fetch_article(url)` returns text, original/final URL and coverage. `ContentError(code, message)` carries safe errors.
- [ ] Write failing tests for nonexistent IDs, private/mapped addresses, redirect-to-metadata, rebinding, timeout, oversized decoded bodies and challenge/login pages. Example assertion: `with self.assertRaises(ContentError): fetch_article('http://169.254.169.254/latest/meta-data/')`.
- [ ] Run each targeted test red before implementing its behavior.
- [ ] Implement DNS-pinned HTTP(S) connections, TLS name verification, per-hop validation, bounded reads and extraction. Declare bounded dependency versions in plugin manifest; use plugin dependency consent/install isolation, not edits to the Hermes environment.
- [ ] Add a controlled public extraction integration check and preserve provenance. Never pass title-only text to the model as article content. Run all tests and commit.

### Task 3 — Cache and generation lifecycle
**Files:** article_summary.py, tests/test_article_summary.py, dashboard/plugin_api.py.
**Contract:** Request by existing article ID and explicit consent; response includes overview/key points or escaped summary text, coverage, source URLs, timestamps, model/provider and cached flag. Errors never masquerade as success.
- [ ] Write tests red for duplicate concurrent requests, removed articles, content/model/prompt invalidation, expiry, size eviction, profile isolation, empty/malformed model output and failure not cached. Example: concurrent identical calls assert model call count equals one and both responses have matching provenance.
- [ ] Implement profile-scoped storage and request ownership, fetch deadline plus 60-second model deadline, successful-only atomic cache writes and 2-generation bound. No raw HTML/credentials in persistence.
- [ ] Test failure and timeout recovery. Prefer bounded synchronous request/response if the bridge supports its deadline; if async jobs are necessary, persist opaque ownership and restart failure states with explicit tests, never hide work in untracked threads.
- [ ] Run full backend tests and a real live summary before committing. The provider result must not be synthesized.

### Task 4 — Desktop and web detail panels
**Files:** desktop/plugin.js, dashboard/dist/index.js, tests/test_desktop.cjs, tests/test_ui.cjs.
**Contract:** Title opens details without fetch/inference/read mutation. Explicit Summarize sends article ID plus consent through the existing authenticated backend. Closing/switching prevents stale state.
- [ ] Write behavioral tests red for title click causing zero model/read calls, explicit consent, fetching/summarizing/error states, switching selection, cached result and preserved read state.
- [ ] Implement metadata panel with Summarize and Open original; use escaped text and native theme tokens. Provide an explicit provider-data notice before first generation.
- [ ] Add Refresh and actionable 401/404/405/network/CLI/model errors; failed loads show unknown/stale rather than zero. Bound request deadlines above backend budget; do not automatically retry mutations or generation.
- [ ] Run Node behavioral tests and real web browser tests. Deliver updated local Desktop file for Mac; obtain user-assisted remote verification without claiming the agent controls the Mac.
- [ ] Commit tested UI work.

### Task 5 — Release verification and installation docs
**Files:** README.md, plugin.yaml, dashboard/manifest.json, .github/workflows/tests.yml, docs/verification/article-summaries.md.
- [ ] Add CI for Python/JS tests and plugin validation with pinned tool/action versions; fixture networks remain isolated, secrets never enter CI.
- [ ] Test original CLI writes only with isolated BLOGWATCHER_DB. Check no real read state changed from summary interactions.
- [ ] Perform independent security/correctness review, fix concrete findings with regression tests, run exact-head CI and live plugin-host summary smoke test.
- [ ] Document extraction fidelity, paid inference, cache retention/limits, remote Mac/VPS packaging and server restart after API route additions. Record exact executed results and explicit gaps.
- [ ] Publish PR without merging. Offer install of the pinned verified commit and separate Mac Desktop artifact; require scoped consent before restarting the live dashboard.

## Execution method recommendation
Native execution with an independent whole-branch review: tasks are tightly coupled through the LLM bridge, retrieval and summary response contracts. Resolve the bridge gate first rather than implementing parallel assumptions.
