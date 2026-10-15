# Full evaluation report accessibility audit

Audited on 2026-10-15 against the report generator at `c5ece05a`.
The initial audit identified two accessibility improvements. The tested states produced no
confirmed axe violations, but expanded evidence includes unresolved automated
contrast checks. This is not a WCAG conformance assessment or a screen-reader
verification pass. The initial audit left report code unchanged. Both recommended
corrections were subsequently implemented as recorded below.

## Scope and reproducible evidence

The report was regenerated with the current checkout's public `report-all`
command from a disposable copy of the saved 17-page Full evaluation
`20261011T015629-880f3e7c`. It contains 86 original Human findings and 198 page
decisions. Existing reviewer attribution was retained. No live provider calls
were made and source evaluation evidence was not edited.

The generated file was copied alone to
`/tmp/va-dat-accessibility-audit/standalone/report.html` and opened through `file:`
with networking disabled. Its SHA-256 is
`ae786b54bc84030cdad8b7655e5fbce16d7ba8bcfb5d88ec42af0c1e6bcac7e1`.
The browser was headless Chromium 153.0.8010.12 on Linux; the accessibility
engine was axe-core 4.14.0 with `wcag2a`, `wcag2aa`, `wcag21aa` and `wcag22aa`
tags. No HTTP requests or JavaScript errors occurred.

Audit scripts, JSON results and screenshots are retained locally in
`.scratch/html-evaluation-reports/accessibility-audit-2026-10-15/`. That directory
is ignored by Git. The scripts use the existing local Playwright installation
at `/tmp/va-dat-report-browser/node_modules` and the cached Chromium executable.

## Recommended corrections

### P2: Keep findings-table text readable on narrow screens

At 320 CSS pixels, the collapsed findings table compresses all seven columns
into approximately 294 pixels. The first disclosure's text box is only
19.625 pixels wide and 204.75 pixels tall. Labels such as "View details",
"Programmatic checks", and the finding title break into one or two characters
per line. The document avoids horizontal overflow by making its contents very
difficult to read. This also affects readers using a magnified narrow layout.

Reproduce by opening the standalone report at 320 pixels with every disclosure
collapsed, then tabbing to its first "View details" control. The screenshot
`narrow-keyboard-focus.png` records the result.

The combination of `overflow-wrap: anywhere` on every cell and no minimum
findings-table width causes the compression. See
`vision_aid/evaluation/css/report.css:13` and
`vision_aid/evaluation/templates/full.html.jinja:18`.

Give the findings table and key columns readable minimum widths inside the
existing keyboard-focusable horizontal scroll region, or use a narrow layout
that preserves each value's header association. A temporary browser-only
prototype with a 64rem table minimum and 16rem minima for the title and details
cells kept the document at 320 pixels, allowed local table scrolling, and gave
the disclosure approximately 234 pixels of width. This illustrates a possible
correction; its exact widths still need design review and expanded-state checks.
No prototype styles were saved into the product.

This is a confirmed readability problem, not a claimed automatic failure of
WCAG 1.4.10. WCAG allows horizontal scrolling for data tables requiring a
two-dimensional layout. See [W3C's Reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

### P2: Give evidence disclosures finding-specific names

All 86 top-level disclosure controls have the accessible name "View details".
Chromium's accessibility tree confirms the repeated names on native
`DisclosureTriangle` nodes. Page-decision disclosures identify the URL but also
repeat it across different findings. Readers navigating controls independently
of the table must recover the surrounding row context to identify the evidence.

Add the Human finding title or ID to each top-level disclosure's accessible
name. For example, "View details: No main landmark defined on the page".
Include the finding identity alongside the URL for nested page decisions.
Keep the visible action text in the accessible name and retain native
`details`/`summary` expanded-state behavior.

The relevant rendering locations are
`vision_aid/evaluation/templates/full.html.jinja:24` and
`vision_aid/evaluation/templates/evidence.html.jinja:13`. The individual report
uses the same generic top-level wording and should receive the same correction.

This is a navigation improvement, not a confirmed WCAG failure. Existing row
headers provide programmatic context; repeated names alone do not establish a
violation. See [W3C's Headings and Labels guidance](https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html).

## Check results

| Check | Observed result |
| --- | --- |
| Initial collapsed report | axe: zero violations, zero incomplete checks |
| All evidence expanded at 1280 pixels | axe: zero violations; 28 incomplete color-contrast checks |
| LLM-missed filter | axe: zero violations, zero incomplete checks; status reports 34 of 86 originals |
| Selected page and expanded evidence at 320 pixels | axe: zero violations; 762 incomplete color-contrast checks |
| Increased text spacing | axe: zero violations, zero incomplete checks in the collapsed report with 1.5 line height, .12em letter spacing, .16em word spacing and 2em paragraph spacing |
| Standard 320, 640 and 1280 pixel layouts | Document width matches viewport; table readability issue described above |
| Skip link | Activation bypasses the header; next Tab enters the report's pricing-table region |
| Keyboard evidence access | Enter opens both native evidence levels; focus remains on the operated summary |
| Focus indication | Keyboard-focused summary has a visible 3px brown outline; scroll regions retain the browser's default focus outline |
| JavaScript disabled | Basic report remains readable; Enter opens native disclosure; enhancement controls stay hidden |
| Forced colors | Chart fill remains distinct from its track using the system highlight color; exact values remain text |
| Existing interaction/print regression tests | Three browser cases passed, including offline filters, disclosures and PDF content/restoration checks |

The incomplete contrast checks report content overlapped or partially obscured
from axe's perspective, including horizontally clipped table cells. They are
neither passes nor confirmed contrast failures. A screenshot of one flagged
expanded evidence block shows readable, non-overlapping text. That spot check
does not resolve every incomplete node.

The shared CSS text colors were also calculated against their backgrounds:

| Foreground / background | Contrast ratio |
| --- | --- |
| Body `#182838` / white | 15.01:1 |
| Links and disclosure labels `#164e88` / white | 8.47:1 |
| `#164e88` / pale panel `#edf2f6` | 7.51:1 |
| Focus outline `#8c3500` / white | 8.00:1 |
| Focus outline `#8c3500` / pale panel `#edf2f6` | 7.10:1 |

These combinations exceed the normal-text minimum in
[W3C's Contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
They do not resolve geometry-related incomplete checks by themselves.

The existing browser regression checks were run with:

```sh
REPORT_BROWSER_MODULES=/tmp/va-dat-report-browser/node_modules \
REPORT_BROWSER_EXECUTABLE=/home/reagan/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome \
LD_LIBRARY_PATH=/tmp/va-dat-report-browser/local-libs/usr/lib/x86_64-linux-gnu \
uv run pytest tests/test_report_interactions.py -q
```

Result: `3 passed in 4.74s`.

## Remaining verification

Actual screen-reader operation was not performed. Test heading and table
navigation, disclosure names and expanded-state announcements, live filter-count
announcements, and reading of long Global evidence with a representative
browser/screen-reader combination. Browser accessibility-tree inspection does
not establish spoken output or ease of navigation.

Actual browser zoom, native print-preview completion/cancellation, exhaustive
inspection of expanded contrast nodes, and accessible PDF output remain
unverified. Viewport resizing, increased text spacing, headless PDF generation
and simulated print lifecycle checks do not establish those results. The
assistive-technology verification ticket remains open and its unperformed
criteria remain unchecked.

## Corrections implemented, 2026-10-15

Full and individual reports now give each top-level disclosure the accessible
name "View details: [Human finding title]" while preserving its visible text.
Page-decision disclosures include the page URL and Human finding title in their
accessible names. Native disclosure behavior and HTML autoescaping are retained.

Screen tables now retain minimum readable widths inside their existing
keyboard-focusable scroll regions. The findings table has a 64rem minimum,
with 16rem minima for finding-title and details cells. Expanded evidence is
16rem wide on narrow screens, and nested page-decision tables scroll within
that evidence. These width rules apply to screen media; the complete-print
layout retains its existing page-width evidence blocks.

Verification covered both report scopes:

- The selected reporting/evaluation suite passed all 87 tests, including the
  three browser interaction and print cases. Following the final narrow-evidence
  adjustment, all three browser cases passed again. Browser coverage includes
  keyboard horizontal scrolling, readable collapsed controls, and expanded
  evidence that fits a 320-pixel viewport.
- Regenerated copies of the saved 17-page Full report and first individual
  report were opened offline. Their initial axe scans had zero violations
  and zero incomplete checks. Chromium's native accessibility tree contained
  the finding-specific names for both disclosure levels.
- At 320 pixels, both documents remained 320 pixels wide. Their findings tables
  were 1024 pixels wide and scrolled locally. The first collapsed summary had
  approximately 234 pixels of width; with evidence expanded it had 256 pixels.
- Scoped Ruff and whitespace checks passed. No live evaluation or model API
  requests were made; generation reused saved evidence and test providers were
  mocked.

Updated samples are `.scratch/html-evaluation-reports/verification/full/report.html`
and `.scratch/html-evaluation-reports/verification/page/report.html`.
Follow-up browser results, screenshots and the verification script are saved
beside the original local audit artifacts with `fix-`/`fixed-` names. The manual
verification limitations above remain outstanding.
