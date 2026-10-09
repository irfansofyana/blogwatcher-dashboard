# Blogwatcher Hermes Companion — Design

## Intent
A self-hosted companion for users of the original `Hyaxia/blogwatcher` CLI. Users see their subscribed sources and unread/all articles inside Hermes Desktop and `hermes dashboard`, manage exactly the state the installed CLI permits, and ask their existing Hermes agent about those articles. No separate web app, direct SQLite writes, feed engine, scheduler, or custom chat runtime.

## Ownership and boundaries
- Blogwatcher owns source discovery, article storage, deduplication, and read state. One backend adapter executes an explicitly allowlisted CLI binary with argument vectors (never a shell), bounded timeout/output, and `BLOGWATCHER_DB` inherited or explicitly configured. It parses the original CLI's human-readable output; a format mismatch is an error, not an empty inbox.
- Hermes owns plugin authentication, AI credentials, agent chat, and remote access. A single plugin package ships a Python agent tool layer, a dashboard FastAPI router, a Desktop ESM page, and a web-dashboard tab. The UI clients share a JSON contract rather than a JS component library.
- Both surfaces call the same authenticated backend namespace. Source names and URLs are data, never shell fragments. The plugin never writes Blogwatcher's DB.
- The CLI and DB must be accessible from the Hermes host/profile. Tailscale can expose authenticated Hermes dashboard privately; there is no plugin-specific listener.

## Core flows
1. Inbox loads unread by default, with all/read toggle, source filter, source/date/title/link rows, and original-article links. Pagination or bounded results prevent overwhelming UI. No fabricated teaser when absent.
2. Source list includes name, site URL, feed URL, selector, last scan when emitted. Add accepts name + URL and optional feed URL, selector, user agent. Removal requires confirmation that Blogwatcher deletes its articles. No edit because CLI lacks edit; no individual article deletion.
3. Scan all or one source on demand; report new counts/errors; reload views. No dashboard scheduler.
4. Read/unread one article and read-all (global or source) through CLI. Confirm global and source-wide read-all.
5. Read-only agent tools expose bounded source/article reads; model text never becomes a shell command or a write confirmation. Desktop and web link to existing Hermes chat. Contextual article-to-composer injection is not promised without a verified API.

## AI and content roadmap
- First working slice: deterministic inbox, CLI actions, agent tools; no independent LLM calls or background processing.
- Next: opt-in briefing on fetched content with exact source URL and clear access failures. Only summarize content actually retrieved, not headlines masquerading as full text. Feed descriptions/teasers need a separate read-only enrichment layer because the user's installed CLI does not display them.
- Later, if warranted: deduplication, relevance filters, recurring digest. These never silently change read status or hide sources.

## Failure and security
- No CLI, unsupported output, timeout, nonzero exit, missing DB, and permission errors are visible and distinct. Parse only complete entries; cap text/process output and reject control characters for UI display.
- Mutations are POST-only, explicit and allowlisted; no direct arbitrary command/flag execution. Validate article IDs and names; no automatic retry of destructive actions. Keep untrusted feed text out of instructions and escape it in UI.
- Trust the Hermes dashboard's authentication, but do not advertise unauthenticated public exposure. Test permissions and profile path against real Hermes host integration before release.

## Verification
- Unit tests with isolated fake CLI cover parsing, argument arrays, limits, missing/unsupported CLI, and failures.
- End-to-end test against original CLI with `BLOGWATCHER_DB` pointing at an isolated test database; verify add/list/scan/read/unread/remove while preserving the user's own DB.
- Load plugin in Hermes Desktop and dashboard, check both render and actions. Agent tool discovery and real chat invocation must be exercised before claiming end-to-end AI support.

## Phase boundary
The first slice is working local code with tests and install instructions. A release requires actual host-side UI and agent verification; any missing integration is documented as a gap, not marked complete.
