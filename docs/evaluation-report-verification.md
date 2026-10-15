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
| Automated accessibility | axe-core 4.11.1, WCAG 2 A/AA and 2.1/2.2 AA tags | No violations or incomplete checks in the tested initial document |
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
