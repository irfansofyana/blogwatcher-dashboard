# Blogwatcher Dashboard for Hermes

A companion to the **original [Hyaxia/blogwatcher](https://github.com/Hyaxia/blogwatcher)** CLI. It adds an unread inbox and source management to Hermes Desktop and the Hermes web dashboard, plus agent tools for asking your existing Hermes agent about subscribed articles. Blogwatcher remains the owner of the database and scanning; this plugin never writes SQLite directly.

## Current slice (0.1.0)

- Unread inbox, all articles, source filter, original links, paging, read/unread and confirmed read-all.
- List, add, and **confirmed remove** sources; removal also deletes that source's articles, as in the CLI.
- Scan all or one selected source on demand; no scheduler.
- Read-only agent tools to list articles and sources. State-changing actions stay in the user-clicked UI; a model-supplied confirmation flag is not human authorization.
- Desktop page and `hermes dashboard` tab; both use the same plugin backend.

**Not included:** source editing (the CLI has no edit command), per-article deletion, teaser text, AI summaries, a separate website, or a second chat interface. “Chat with Hermes” opens Hermes's built-in chat; contextual article-to-chat handoff remains unverified on the web dashboard. Do not summarize titles as though they were full article content.

## Requirements

- A compatible original `blogwatcher` executable accessible to the Hermes process; this has been tested against Irfan's original Go build (`--version` reports `dev`). The unrelated `blogwatcher-cli` fork is not supported.
- Hermes Agent with Desktop/plugin SDK and web-dashboard plugin support. The Python dashboard plugin runs using Hermes's FastAPI dependency; no separate Python server or package manager is required.
- The CLI must access the same Blogwatcher DB as the user. If the CLI and Hermes run under different accounts/containers, configure `BLOGWATCHER_DB` explicitly and ensure both processes can read/write that file. **Do not mount the DB separately into an untrusted process.**

## Install (review first)

Place this repository as **one plugin folder** at `$HERMES_HOME/plugins/blogwatcher-dashboard/`. For local development, a symlink from there to your checkout works. This is not a Hermes core patch. Then enable its agent/backend half with `hermes plugins enable blogwatcher-dashboard --no-allow-tool-override`; enable its Desktop half in **Capabilities → Plugins** (the unified package's Desktop copy defaults off). Start/restart the dashboard; its Blogwatcher tab appears in navigation. The dashboard plugin routes follow the Hermes dashboard's existing auth gate.

`BLOGWATCHER_BIN` optionally specifies the absolute path to the CLI binary **in the Hermes host's launch environment**. If the executable is already on the Hermes process's `PATH`, no override is needed. `BLOGWATCHER_DB` is the original CLI's own database override; leave it unset when the CLI and Hermes use the same home and default database. Example for a local CLI process:

```bash
BLOGWATCHER_BIN=/absolute/path/to/blogwatcher hermes dashboard --host 127.0.0.1
```

For a service/desktop launch, put the executable on the service's `PATH` or set the environment in that service launcher; setting it only in a different interactive shell does not change an already-running Hermes process. **Never edit Hermes core files.** Prefer Tailscale access to the authenticated Hermes dashboard over exposing the dashboard publicly. There is no plugin-specific listener or Tailscale setup.

## Validate and test

```bash
hermes plugins validate /path/to/blogwatcher-dashboard
python -m unittest discover -s tests -v
node --test tests/test_ui.cjs
node --experimental-vm-modules --test tests/test_desktop.cjs
node --check dashboard/dist/index.js
node --input-type=module --check < desktop/plugin.js
```

`tests/test_real_cli.py` uses a temporary `BLOGWATCHER_DB` and a local RSS fixture. It adds, scans, toggles, and removes **only test data**, never the user's subscriptions. It skips when the original binary isn't installed; set `BLOGWATCHER_TEST_BIN` to its absolute path if needed.

## Design and known boundaries

See `docs/superpowers/specs/2026-10-09-blogwatcher-hermes-design.md` and `docs/superpowers/plans/2026-10-09-blogwatcher-hermes-first-slice.md`. Blogwatcher has human-oriented output rather than a JSON API, so this adapter checks record counts and fails closed on unexpected output. Listing all articles requires the CLI to emit every record before pagination; very large databases may need an upstream machine-readable/paginated CLI command rather than an unsafe SQLite shortcut. The UI renders publisher titles as text and only opens HTTP(S) links.
