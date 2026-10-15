# Evaluation report verification

## Individual HTML report, 2026-10-15

The individual `report` command was verified against synthetic completed runs
through the public CLI. Provider responses in the execution fixtures are replayed;
report regeneration reads saved evidence and makes no model requests.

- Full suite: 137 tests passed, including existing Full evaluation reporting.
- `ruff check vision_aid/evaluation tests`: passed. Repository-wide Ruff also
  reports 74 existing findings outside these directories; those files were not
  changed for reporting.
- CLI coverage includes hand-calculated source and Overall rates, cross-catches,
  zero denominators, empty findings, attribution, evidence ownership, invalid
  decisions, canonical Human evidence despite edited CSV copies, jointly matched
  findings, readable IDs/check provenance, code-like evidence, blank notes, and
  failure on missing required rendering fields.
- Jinja2 uses HTML autoescaping and strict undefined values. A failed rendering
  publishes no HTML and preserves a superseded Markdown report. Successful
  generation atomically replaces HTML and removes that report's Markdown output.
- `uv build --wheel` included the Jinja template and CSS. Installing the wheel
  into a fresh environment and invoking its `visionaid-evaluate report` from
  `/tmp`, outside the checkout, generated the report successfully.

A generated report containing six Human findings, a joint match, and hostile
HTML-like model/reviewer text was copied into a directory containing only
`report.html`. Checks used the local-file protocol with networking disabled:

| Check | Actual coverage | Result |
| --- | --- | --- |
| Standalone resources | Chromium 153.0.8010.12, Linux, Playwright offline context | No HTTP requests; report readable |
| Automated accessibility | axe-core 4.14.0, WCAG 2 A/AA and 2.1/2.2 AA tags | No violations or incomplete checks in the tested initial document |
| Narrow layout | Chromium viewport 320 × 800 CSS pixels | Document and body width 320; findings table scrolls in its own region |
| Native disclosure | Chromium, JavaScript disabled, focus first summary and press Enter | Evidence opened; six disclosures were initially collapsed |

The disposable copied report was saved at
`/tmp/va-dat-ticket01-standalone/report.html`; the installed-package smoke output
was saved under `/tmp/va-dat-ticket01-installed-run/`. These temporary artifacts
are not committed.

Manual keyboard inspection, actual browser zoom, and screen-reader verification
remain outstanding. Headless keyboard automation and a narrow viewport do not
establish those manual results or WCAG conformance. The stakeholder's browser and
screen-reader setup is unknown. Combined HTML reports, charts, filtering,
search, and complete printing require later ticket verification.


## Full HTML report, 2026-10-15

Both `report` and `report-all` now publish standalone HTML. The combined report
reuses the validated page reviews and shared evidence templates. No live provider
calls were made during report verification. Existing scoring and review validation
remain authoritative.

- Full suite: 140 tests passed. `ruff check vision_aid/evaluation tests` and
  `git diff --check` passed.
- Public CLI tests preserve the worked eight-original case with rates of 2/4 LLM,
  1/3 Programmatic, and 5/8 Overall. They cover joint matches, cross-catches,
  partial evidence across pages, conflicting Global classifications, ownership,
  empty pages, zero denominators, reviewer attribution, stale parent removal,
  child preservation, and replacement of regenerated Markdown only.
- Parsed HTML assertions cover original source order, one overview row per
  original, readable matched IDs, text, check identity and run provenance,
  every Global page decision, two disclosure levels, independent panels, and
  absence of external resources. Missing required parent provenance fails
  rendering without publishing a parent or deleting completed child HTML.
- The saved 17-page run was regenerated in a disposable copy at
  `/tmp/va-dat-html-verification/20261011T015629-880f3e7c` with attribution to
  its original saved reviewer decisions. It retains 86 originals and 198 page
  decisions. Combined counts remain 28/62 LLM, 18/18 Programmatic, and 46/86
  Overall. Independent inspection resolved all 187 matched ID occurrences to
  readable problem text and confirmed all 86 original IDs and titles. The parent
  contains 86 finding disclosures and 119 Global page disclosures, all initially
  collapsed.
- `uv build --wheel` packaged the page, Full, shared evidence and method
  templates and embedded CSS. A fresh environment at
  `/tmp/va-dat-ticket02-installed` generated both scopes from `/tmp`, outside
  the checkout, using a separate disposable run copy under
  `/tmp/va-dat-ticket02-installed-runs`.

The parent was copied alone to `/tmp/va-dat-ticket02-standalone/report.html`.
Chromium 153.0.8010.12 opened it via the local-file protocol with networking
disabled and made no HTTP requests. axe-core 4.14.0 reported no violations or
incomplete checks for WCAG 2 A/AA and 2.1/2.2 AA tags in the initial document.
At a 320 × 800 CSS-pixel viewport, document and body widths stayed at 320 pixels;
the table retained its own scroll region. With JavaScript disabled, keyboard
Enter opened a Global finding and two of its page disclosures independently,
leaving both page panels open with readable matching evidence.

These browser checks are automated. Actual browser zoom, manual keyboard
inspection, and screen-reader verification remain outstanding. Charts,
filtering, search, and complete printing are later ticket work; no WCAG
conformance claim is made.

## Detection charts, 2026-10-15

Both commands now render labelled detection overview bars with exact counts,
percentages and semantic tables. The LLM result appears first with a stronger
border and larger label. Programmatic and Overall denominators remain separate.
Python prepares all chart percentages from the existing deterministic counts;
charts contain no script or external dependency. A zero denominator has a text
explanation and no bar. Full reports include page LLM results in original page
order, with an explanation of varying eligibility, repeated Globals and the
limits of comparing pages.

- Full suite: 140 tests passed. Existing public CLI fixtures now assert chart
  and table results for individual cross-catches, the worked combined 2/4 LLM,
  1/3 Programmatic and 5/8 Overall case, and page LLM counts of 1/3, 1/3 and 1/2.
  Empty original sets and empty page results retain undefined source rates in
  words. Nonempty Overall denominators still report a truthful 0.0% when no
  findings were caught. Individual reports omit the page comparison.
- `ruff check vision_aid/evaluation tests` and `git diff --check`: passed.
- `uv build --wheel` bundled `charts.html` and `charts.css` with the shared
  templates. The wheel was installed in a fresh environment at
  `/tmp/va-dat-ticket03-installed`; its `report-all` and `report` commands
  generated both scopes from `/tmp`, outside the checkout, against a separate
  disposable copy at `/tmp/va-dat-ticket03-installed-runs`. No saved review
  decisions were changed and no live model calls were made.
- The installed parent retained 28/62 LLM, 18/18 Programmatic and 46/86 Overall;
  the first individual page retained 3/9 LLM, 5/5 Programmatic and 8/16 Overall.
  Copied standalone files contain only their respective `report.html` under
  `/tmp/va-dat-ticket03-standalone/full` and `/tmp/va-dat-ticket03-standalone/page`.

Chromium 153.0.8010.12 opened both copied files through `file:` in offline
contexts. axe-core 4.14.0 reported no violations or incomplete checks using
WCAG 2 A/AA and 2.1/2.2 AA tags. No HTTP requests occurred. Browser assertions
located the named figures and captioned tables, measured rendered bar lengths
against the displayed 45.2%, 100.0%, 53.5% parent values and 33.3%, 100.0%, 50.0%
page values, and confirmed 17 page-comparison table rows. With JavaScript
disabled these labels, values, tables and graphics remained available. A
320 × 800 CSS-pixel viewport retained a 320-pixel document width in both scopes;
tables retained their own scroll regions. Automated keyboard Enter opened the
first native disclosure in both scopes.

These checks do not replace actual screen-reader reading, manual keyboard
inspection or actual browser zoom. Those checks remain outstanding under the
assistive-technology verification ticket, and no WCAG conformance claim is made.

## Search, filters and disclosures, 2026-10-15

Both report commands now embed search, source-aware outcome filters, clear and
visible-evidence expand/collapse controls. Full reports also filter by page.
These controls use only evidence already embedded in the document. Detection
results and charts continue to describe the complete run.

- After merging the chart work, the complete suite passed with 143 tests,
  including three browser tests. Ruff for `vision_aid/evaluation` and `tests`,
  and `git diff --check`, passed.
- The browser tests generate reports through the public `report-all` CLI using
  synthetic saved reviews and replayed provider responses. They copy parent and
  child HTML into a directory without run evidence, then open the files offline.
  They cover initially hidden Human and tool evidence and rationale, matching
  page/excerpt controls, independently opened page matches, combined versus
  selected-page Global outcomes, cross-catches, eligible source misses,
  not-testable results, combined page/outcome/text filters, empty results,
  clearing, stable complete-run results, live counts, preserved filter focus,
  visible-only expand/collapse and native disclosures with JavaScript disabled.
- A wheel built with `uv build --wheel` includes `controls.html` and `filters.js`.
  A fresh environment at `/tmp/va-dat-ticket04-installed` invoked both commands
  from `/tmp`. The same three browser checks passed against the installed
  package's copied standalone outputs at
  `/tmp/va-dat-ticket04-installed-standalone/`.
- The saved 17-page evaluation regenerated from a separate disposable copy at
  `/tmp/va-dat-ticket04-runs/20261011T015629-880f3e7c`. Its parent was copied alone
  to `/tmp/va-dat-ticket04-standalone/report.html`. No saved reviews changed and
  no live provider calls were made.
- Chromium 153.0.8010.12 with networking disabled made no HTTP requests for the
  saved parent or installed-package synthetic parent and child. All three
  documents stayed within a 320 CSS-pixel viewport, with the findings tables
  retaining their scroll regions. Native disclosures opened by keyboard with
  JavaScript disabled. axe-core 4.14.0 reported no violations or incomplete
  checks against WCAG 2 A/AA and 2.1/2.2 AA tags, both initially and after
  searching, selecting a page where available, and expanding visible evidence.

To repeat the committed browser checks, install Playwright in a local Node
module directory and provide a compatible Chromium executable, then run:

```sh
REPORT_BROWSER_MODULES=/path/to/node_modules \
REPORT_BROWSER_EXECUTABLE=/path/to/chromium \
uv run pytest tests/test_report_interactions.py -q
```

The tests skip when these environment variables or Node are absent. They require
no browser test service or runtime network connection. In environments with
non-system browser libraries, also set `LD_LIBRARY_PATH` to those libraries.

These are automated browser checks. Manual keyboard inspection, actual browser
zoom and screen-reader verification remain outstanding, including spoken filter
count announcements. The stakeholder's assistive technology setup remains
unknown. Complete printing is the next implementation ticket; these results do
not establish WCAG conformance.

## Complete printing, 2026-10-15

Both generated report scopes expose Print complete report after their embedded
print script initializes. The action reveals every original finding, page
decision, compact page-table row and nested disclosure before invoking browser
printing. It restores hidden states and independently opened disclosures on
`afterprint`, without changing filter values, counts, evidence or scoring.
Keyboard focus and scroll position return when screen media resumes. The same
browser notification handles completion and cancellation.

Print styling lays each finding out as a full-width block with labelled outcomes;
long evidence can continue across sheets. Charts retain exact labels and their
equivalent data tables, other tables repeat their column headers, and controls,
search excerpts and selected-page filter summaries are omitted. Ordinary browser
printing follows the current reading state. With JavaScript disabled, readers
can open native disclosures before using the browser's Print command; no scripted
print or filter controls are offered.

- The full suite passed with 144 tests, including four optional browser checks.
  Ruff for `vision_aid/evaluation` and `tests`, and `git diff --check`, passed.
- The committed print check uses CLI-generated synthetic parent and child
  reports, each copied into its own directory without run evidence or other HTML
  files, and opens them through `file:` with networking disabled. It exercises
  active text, page and outcome filters, independently opened nested Global
  panels, and 250 lines of review notes spanning sheets. Real headless Chromium
  A4 PDFs include all matched IDs, saved Human and tool text, rationale, notes,
  charts' exact data, metadata and scoring explanations. Basic no-JavaScript
  printing includes the manually opened evidence. The check also verifies full
  evidence and caption widths and preservation of ordinary-print filtering.
- Completion and cancellation state restoration are exercised with simulated
  browser lifecycle events. The PDF export itself also emits Chromium print
  lifecycle events. This does not exercise a human completing or cancelling a
  native preview dialog; that remains a manual check under ticket 06.
- `uv build --wheel` bundled `print.css` and `print.js`. A fresh environment at
  `/tmp/va-dat-ticket05-installed` invoked installed `report-all` and `report`
  commands from `/tmp` against disposable synthetic and real saved runs. The
  committed print browser check passed against the installed package's
  synthetic outputs. No live provider calls were made.
- The real run regenerated in a separate disposable copy at
  `/tmp/va-dat-ticket05-runs/20261011T015629-880f3e7c`. Its standalone installed
  outputs and temporary PDFs are under
  `/tmp/va-dat-ticket05-standalone/real/`, in separate `full` and `page`
  directories. Source run evidence and review decisions were not edited.
- Chromium 153.0.8010.12 on Linux exported the complete real Full report as
  273 A4 sheets and its homepage as 35 sheets. `pdftotext` found all 86 original
  titles and 187 matched finding IDs in the parent, and all 16 original titles
  and 23 matched IDs in the homepage. Comparison of 3,118 parent evidence text
  blocks found all ordinary text, with nine private-use icon glyph fragments
  containing U+F104 failing exact PDF text extraction. All 426 homepage blocks
  matched. Saved evidence is preserved as supplied; these results do not promise
  exact font-glyph preservation. Raster inspection checked representative printed
  table and full-width evidence pages.
- The real copied documents made no network requests or browser script errors.
  Initial-document axe-core 4.14.0 checks with WCAG 2 A/AA and 2.1/2.2 AA tags
  reported no violations or incomplete checks. Both retained a 320 CSS-pixel
  document width, and native disclosures opened by keyboard without JavaScript.
  A separate fully expanded 320-pixel scan reported no violations but left
  color-contrast checks incomplete for table cells obscured by their scroll
  containers. Initial and targeted expanded checks do not establish coverage
  of every possible expanded state.

Run the browser checks as documented above. The print case additionally requires
Poppler's `pdftotext`; it skips when that executable is unavailable. Only the
Chromium/Linux combination above has been exercised for printing. Native preview
completion/cancellation, other browsers, actual zoom, manual keyboard inspection,
private-use icon appearance and screen-reader reading remain under ticket 06.
Accessible PDF production and claims of WCAG conformance remain outside this
verification. Headless PDF text checks do not establish accessible PDF output.

## Integration review, 2026-10-15

The spec review found no implementation issues. The standards review identified
duplicated document layout in the individual and Full templates. Both now extend
one shared `base.html` for the document metadata, embedded assets, skip link,
model and reviewer attribution, navigation, print button and scripts. Their
scope-specific evidence, charts and scoring explanations remain in the existing
templates.

- The complete suite passed with 144 tests, including all four browser cases.
  Scoped Ruff for `vision_aid/evaluation` and `tests`, and `git diff --check`,
  passed. Existing public CLI and browser tests cover this template refactor;
  no tests tied to the inheritance implementation were added.
- A fresh wheel includes `base.html`. Installed commands generated both scopes
  from `/tmp`, outside the checkout, against a separate saved-run copy at
  `/tmp/va-dat-report-review-runs/20261011T015629-880f3e7c`. Both generated files
  match their pre-refactor HTML except for blank lines. No live provider calls
  were made.
- Independent final integration inspection confirmed 86 overview rows, 198 page
  decisions and 187 matched ID occurrences, with all saved classifications,
  rationale and notes retained. Rates remain 28/62 LLM, 18/18 Programmatic and
  46/86 Overall, and saved cached-token accounting is unchanged. SHA-256 checks
  confirmed all 342 original source files were unchanged.
- The installed outputs were copied alone to the `full` and `page` directories
  under `/tmp/va-dat-report-review-standalone/`. Chromium 153.0.8010.12 opened
  both through `file:` with networking disabled and made no HTTP requests.
  axe-core 4.14.0 reported no violations or incomplete checks for WCAG 2 A/AA
  and 2.1/2.2 AA tags in each initial document. Both document and body widths
  stayed at 320 CSS pixels in a 320-pixel viewport. All 205 Full and 16 page
  disclosures started collapsed; keyboard Enter opened a native disclosure
  with JavaScript disabled in both scopes. These results also matched the
  independent integration checks before the layout refactor.

The manual assistive-technology and native print-preview checks listed above
remain outstanding under ticket 06. These automated checks do not establish
WCAG conformance or accessible PDF output.

## Jinja template suffixes, 2026-10-15

All 12 report template sources now end in `.jinja`, retaining their content
extensions, such as `base.html.jinja`, `report.css.jinja`, and `filters.js.jinja`.
Template references, package data, and HTML autoescaping use the new names.

The 144-test suite passed with browser checks enabled, including hostile-evidence
escaping. Scoped Ruff, lock validation, and whitespace checks passed. A fresh
wheel contained all 12 renamed sources, and its installed `report` and
`report-all` commands generated both scopes outside the checkout using a
disposable saved run. No live provider calls were made.

## Static asset separation, 2026-10-15

The seven HTML templates retain `.html.jinja` names under `templates/`. The
two static JavaScript files now use `.js` under `js/`, and the three static
stylesheets use `.css` under `css/`. Python reads these trusted package assets
as literal text and embeds them in the report; Jinja no longer processes them
as templates. Review and model text remain HTML-escaped.

All 144 tests passed with browser checks enabled, including search, filtering,
printing, offline reading, and hostile-evidence escaping. Scoped Ruff and
whitespace checks passed. A fresh wheel contained seven HTML templates, two
JavaScript assets, and three CSS assets in their separate folders. Its installed
`report` and `report-all` commands generated both scopes outside the checkout
from a disposable saved run, with no live provider calls.
