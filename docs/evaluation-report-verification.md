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
