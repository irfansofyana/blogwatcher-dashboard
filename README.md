# Blogwatcher for Hermes

Read and manage your [original Blogwatcher](https://github.com/Hyaxia/blogwatcher) subscriptions inside Hermes Desktop and `hermes dashboard`. No Hermes patches or direct SQLite writes.

## Features

- Unread/all inbox, source filters, pagination and read/unread controls.
- Add/remove sources and scan on demand. Removal deletes the source's articles.
- Expand multiple articles inline, with formatted summaries and independent controls. Opening loads saved results without publisher access or inference.
- Explicitly **Summarize** or **Regenerate** using your Hermes model. Neither action marks articles read.
- Read-only agent tools for articles and subscriptions.

Summaries use retrieved text, not headlines. They show coverage and model attribution, reuse successful results for seven days (50 MiB cap), display older saved results as stale until eviction, and require consent before sending article text to your model provider. Hermes may retry or use configured fallback models; the plugin never retries a generation itself. Inaccessible/blocked pages produce an error, not a guessed summary. Private-network fetches are blocked.

## Install

On the **Hermes backend host**, ensure `blogwatcher` is on the service's PATH, then:

```bash
hermes plugins install https://github.com/irfansofyana/blogwatcher-dashboard --enable
```

Restart the **dashboard/API server** after installation or updates that add routes. Open **Blogwatcher** in the web sidebar. Keep Hermes's authentication enabled for remote access.

For Desktop on the same machine: **Capabilities → Plugins → Rescan**, then enable Blogwatcher.

For Desktop on a **different machine**, copy `desktop/plugin.js` to:

```text
~/.hermes/desktop-plugins/blogwatcher-dashboard/plugin.js
```

Rescan and enable the local Desktop plugin. It calls the connected remote backend; the client needs neither Python nor Blogwatcher. Update both copies together.

Optional backend launch variables: `BLOGWATCHER_BIN` (absolute executable path) and `BLOGWATCHER_DB` (the CLI's database override). The `blogwatcher-cli` fork is not supported. AI requires the backend plugin's registered Hermes LLM context; no separate API key is needed in the UI.

## Development

```bash
hermes plugins validate .
python -m unittest discover -s tests -v
node --test tests/test_ui.cjs
node --experimental-vm-modules --test tests/test_desktop.cjs
```

Run Python tests in an environment with Hermes/FastAPI. Real-CLI tests use a temporary database; set `BLOGWATCHER_TEST_BIN` if necessary. Live inference tests are opt-in and may spend tokens. The reader doesn't bypass paywalls or execute publisher JavaScript. Native agent chat embedding, source editing and scheduled scans are outside this plugin's scope.
