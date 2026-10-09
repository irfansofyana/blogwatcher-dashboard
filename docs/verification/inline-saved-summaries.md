# Inline saved summaries verification

Approved scope: safe Markdown formatting; inline details for multiple independently expanded article rows; immediate offline saved-summary lookup plus explicit regeneration.

- 45 Python tests passed with installed-runtime bridge probe enabled. Includes offline cache read across service recreation, stale labeling, successful regeneration bypass, failed regeneration preserving saved output, real HTTP route lookup/404/explicit regeneration, and original CLI lifecycle in an isolated database.
- 10 web and 7 Desktop behavioral tests passed. Safe React text nodes render headings, lists, bold and inline code. No raw HTML execution or automatic paid inference. Multi-row state and close/reopen late-response races covered.
- Plugin validation passed; no Hermes core changes.
- Browser fixture verification loaded the actual web plugin with real React. Clicking test article 20 preserved scrollY at 2882 before and after expansion; details were inside its list item. Headings, strong, code and ordered lists existed in the DOM; injected script count was zero. Opening article 21 left two rows expanded and recorded zero POST calls. Fixture data was explicitly synthetic; this was not an inference test or production API deployment test.
- Existing successful cache files are read directly; no cache migration, publisher request or model call occurs on GET. Results older than seven days are labeled stale until bounded-storage eviction. Regenerate retains previous output during work/errors and requires explicit provider-cost consent.
- Independent review found two backend bugs; regressions reproduced them before fixes. Regeneration now has its own in-flight identity instead of inheriting a normal cache-read request, and bounded cache reads accept valid multibyte output up to the generation character limit. Atomic writes use unique temporary files for concurrent modes. UI review found no important reproducible defect.
- Production install is unchanged. Desktop on Mac requires a separate client file update. Remote CI is still pending publication.
