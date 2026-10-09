# Article Detail and Reliable On-Demand Summaries

## Approved intent
Improve the existing original-Blogwatcher companion on main, without patching Hermes. Both the Hermes web tab and Mac Desktop UI must support a detail panel and explicit summarization using the VPS backend. Clicking an article does not spend tokens or mark it read. Blogwatcher's database remains CLI-owned.

## User experience
- Clicking a title opens an article detail panel showing title, source, published date and original URL. Separate Open original and Summarize actions.
- Summarize explicitly authorizes retrieval and sending retrieved article text to the configured Hermes model provider. Show this notice before first generation; never claim private/local inference unless configured.
- States: metadata ready, fetching content, summarizing, completed, failed. Closing or switching panels prevents a late result from appearing under another article.
- Successful result: overview, key points, original and final source URLs, retrieved-at and generated-at timestamps, model/provider attribution, coverage label and cache indication.
- Coverage label is 'extracted article text' rather than a guarantee of publisher completeness. Truncated input is 'excerpt only'; insufficient or inaccessible content yields no summary. No summary invented from a headline.
- Summaries render escaped text. No article HTML or arbitrary model markup execution.

## Architecture
One server-side summary service shared by both plugin surfaces. New authenticated routes accept an existing article ID, not a browser-provided arbitrary URL. The backend resolves the ID through original Blogwatcher CLI output. Article extraction, cache and model calls are independent modules with test seams.

Host-owned Hermes LLM calls are preferred to direct provider SDKs: no keys in renderer, no separate agent, no new chat runtime. A technical integration gate must prove dashboard route -> plugin-scoped ctx.llm works in actual Hermes plugin-host mode. Do not assume register(ctx) and dashboard imports share module globals. If the supported context cannot be reached, report the missing contract; do not patch core or copy credentials.

## Retrieval safety
- HTTP(S) only, no credentials in URLs; reject private, loopback, link-local, multicast, reserved and unspecified IPv4/IPv6, including mapped addresses and metadata endpoints.
- Validate every redirect (at most 3). Resolve DNS and pin the approved destination used by the connection while preserving TLS host verification; resolving once and allowing the HTTP client to resolve again is insufficient protection against DNS rebinding.
- No environment-proxy bypass of validation, browser automation, logged-in sessions, paywall bypass or JavaScript execution.
- Fetch wall-clock deadline 20 seconds, maximum decoded response 2 MiB, maximum model input 30000 characters. Allow HTML/plain-text only. Reject login/challenge/empty extraction; remove scripts/styles/navigation with an article extraction library.

## Model and cache behavior
- One host-managed facade call with a 60-second per-call timeout, maximum output 800 tokens, and no tools. The user approved inheriting Hermes’s internal retry/fallback policy; disclose possible additional token spend before generation. The plugin itself never retries generation. Article text is untrusted evidence, explicitly separated from system instructions.
- Cache successful results in plugin-owned profile-scoped storage, never Blogwatcher SQLite. Key includes article URL, normalized content hash, prompt version and resolved model configuration. Cache 7 days, cap storage at 50 MiB; evict oldest records. Do not persist credentials or raw HTML.
- Metadata lookup per request prevents returning a summary for a removed article. Concurrent same-article/config requests share one generation and the same failure; no plugin-level automatic retry. Hermes-owned retries/fallbacks remain permitted by explicit user approval. Bound concurrent generations to 2 per profile. A timeout/disconnect may have consumed tokens; say so before offering an explicit retry.
- No process-global cross-profile cache or credentials. Background tasks preserve owning profile scope. If jobs are asynchronous, expose opaque job IDs and reject cross-profile reads. On restart in-flight jobs fail clearly; never report completion from missing state.

## Reliability improvements in this slice
- Initial loading and refresh failures are not '0 articles'. Preserve existing list as visibly stale when refresh fails.
- Refresh button and read-only diagnostics distinguish API missing/disabled (404), wrong method/route (405), expired auth (401), CLI unavailable, parse failure and temporary network failure.
- Request generations and stable article identity prevent obsolete list/summary responses replacing current selection.
- No automatic retry of mutations; tell the user to refresh after unknown outcome.
- UI API deadlines exceed the server's bounded work; if jobs are used, poll via host-supported query primitives and stop on unmount. Preserve Mac-local Desktop file + VPS package deployment instructions, including necessary dashboard restart after route changes.

## Acceptance and release gates
1. Tests demonstrate no model call on title click; read state unchanged on detail/summary.
2. Tests cover blocked network destinations, redirects, DNS rebinding, oversized/slow responses, insufficient content, malicious HTML and prompt injection separation.
3. Tests cover cache invalidation, concurrent duplicate requests, cross-profile isolation, model/auth failure, timeout, malformed/empty model result, restart recovery and stale selection.
4. Exercise the real Hermes plugin loader and plugin-host HTTP route with host-owned model auth; a mocked provider is not evidence of successful live generation.
5. Test web interactions on an isolated DB and Mac-local UI against VPS APIs; user-assisted Mac checks are explicit when the agent cannot access the Mac.
6. Independent code review, exact-head CI and plugin validation before release. Publication is a PR; merge or active deployment requires user approval. No service restart without a scoped user approval.

## Alternatives considered
- Generate immediately on click: rejected because inspection should not create hidden cost.
- Use existing chat for every summary: rejected for this flow because the result belongs to the detail panel and should not clutter conversations.
- Direct provider client: rejected unless the supported Hermes bridge is genuinely unavailable and the user explicitly approves a separate credential/configuration boundary.

## Deferred
Title search, bookmarks, tagging, digests, relevance ranking, automatic summaries, and full chat embedding are out of scope.

## Source
Hermes Plugin LLM Access: https://hermes-agent.nousresearch.com/docs/developer-guide/plugin-llm-access (checked during design; documents host-managed ctx.llm.complete/acomplete, timeouts, audit, provider/model attribution and trust gates).
