# Article-summary execution record

Plan: docs/superpowers/plans/2026-10-09-article-summary-plan.md
Base main: 6ea58daecbbef3d02f7d075e61940fffdaa064eb

- User authorized direct implementation on main and concise README. Production installation is not changed by these repository edits.
- Bridge: 78fb3c29fc04a242eb64d6279bb964e0d0c0d625; independent implementation tests prove explicit package-module context handoff in plugin-host mode. Parent inspected source and exercised production summary API separately.
- Retrieval: destination validation, DNS-pinned socket/TLS hostname verification, redirects, bounded text and semantic extraction; unit tests pass. Real public article fetch returned 7957 characters, labeled excerpt-only.
- Summary service: successful-only atomic cache, seven-day expiry, 50MiB eviction, content/config/prompt key, two-slot generation bound and same-article deduplication. Unit tests cover success cache, model/config/content invalidation, duplicate calls and empty model result.
- UI: title click opens detail without inference/read writes; explicit consent before summary. Web browser verified actual panel; tests cover both surfaces. Summary responses carry attribution and coverage, rendered as escaped text.
- Production API live smoke in an isolated PluginHost returned HTTP200, genuine provider=openai-codex model=gpt-6.1-sol-900k summary of a subscribed Simon Willison article. No provider credentials read or copied and no main service restart.
- Actual separate `hermes dashboard` launch on loopback port9137 with an isolated home and checkout symlink also returned HTTP200 from authenticated production summary endpoint, without manual host.load; a web browser opened details successfully.
- Local suite at this point: 37 Python tests (one optional runtime integration skipped in the plain interpreter); five JS behavior tests pass. Explicit runtime integration/live bridge command must run separately before publication.
- CI workflow added; remote CI not yet exercised.

## Rulings
- Extraction uses a small standard-library HTML parser favoring article/main and ignoring navigation/scripts. Fallback is excerpt-only, not full fidelity. This avoids mutating Hermes dependencies; complex publisher layouts can still fail or yield weaker coverage and are not hidden.
- Summary is a bounded synchronous call rather than a job system. UI shows 'Fetching and summarizing…' together because no streaming status channel is introduced. Closing selection doesn't cancel a model call; no automatic paid retries. Cost if wrong: a long-running host call may outlast client patience; timeout/unknown-outcome behavior must remain explicit.
- Direct main work follows the user's explicit instruction, rather than the original plan's PR-only flow. No automatic deployment/service restart; Mac runtime interaction needs user-assisted testing.
