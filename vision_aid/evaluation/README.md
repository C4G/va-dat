# Evaluator Overview

This evaluator measures how many findings from a human accessibility audit the
va-dat tool also catches. It only measures coverage of the human audit. Extra
problems the tool reports don't help or hurt the score.

va-dat finds problems in two ways, and the evaluator scores each one separately:

- **The programmatic checker** is va-dat's set of rule-based checks. It uses no
  AI, so it gives the same results on a page no matter which model you test.
- **The LLM checks** send parts of the page to a model and ask it to find
  problems. This is the part you compare across models.

Each problem in the human audit is a **human finding**. A **match** links a human
finding to the tool findings that describe the same problem on the same page.

Run every command from the repository root as
`uv run visionaid-evaluate <command>`, and add `--help` to any command to see
its options. The [quick start in the root README](../../README.md#evaluator-quick-start)
has the full command sequence to copy.

## The General Workflow

1. **[Capture the pages](#1-capture-the-pages).** `capture` downloads every page
   listed in the audit and saves its HTML.
2. **[Create the mapping](#2-create-the-mapping).** `human-finding-mapping-prepare`
   writes review CSV files. In them you record which source should catch each
   human finding and which checker results already match it. Then
   `human-finding-mapping-approve` checks your answers and turns them into the
   mapping file. You do this once per audit and reuse the mapping for every
   evaluation run.
3. **[Run the model](#3-run-the-model).** `run` (one page) or `run-all` (every
   page) sends the prompts to the model you choose.
4. **[Review the LLM matches](#4-review-the-llm-matches).** You record which LLM
   findings match each human finding.
5. **[Build the report](#5-build-the-report).** `report` or `report-all` checks
   your review and writes `report.html`.

Every command writes to a new folder and won't overwrite earlier work.

## The human audit file

The human audit is expected to be in a certain format and location. It should be an Excel file in the repository root. Commands read
`Pristine Accessibility Defect Report.xlsx` by default, and Git ignores that
name. To use another human audit in the same format, pass `--human-audit`.

The audit is private, and so is everything made from it. Keep the files you
generate under `.model-evaluation/`, which Git ignores. Runs always go there, and
the examples below put snapshots and the mapping there too.

The Excel file needs two tabs:

- **`Defect report`** has one row per human finding.
- **`URL list`** lists the pages to evaluate.

Other tabs are ignored.

### Defect report tab

The first row must have these headers, in this order:

```text
Sr. #, element name, Browser Combination, Page name, Issue Title,
Steps to Reproduce, actual result, expected result, Recommendation for Fix,
WCAG Sc, Type of Change, comment
```

Every row needs an `Issue Title`. Each finding's `Steps to Reproduce` must
contain exactly one of the URLs from the `URL list` tab. That's how the
evaluator assigns the finding to a page. A finding with `Page name` set to
`Global` applies to every page.

### URL list tab

The first row must include a `URL` header. List one page per row under it,
and don't repeat a URL. Other columns are ignored. `capture` downloads these
pages in the order listed.

## 1. Capture the pages

`capture` saves the HTML the server returns for each URL as `page-001.html`,
`page-002.html`, and so on, plus a `snapshots.json` that lists which file came
from which URL. Later commands read the pages from these files, so every model
is tested on the same HTML.

`capture` doesn't run JavaScript. Keep this in mind, since modern frontend
frameworks often build most of the page's HTML with JavaScript.

## 2. Create the mapping

### What is a mapping?

A human finding mapping is a JSON file that records two decisions for each
human finding:

- **Its classification**: which source should be able to catch it.

  | Value                  | Use it when                                                            |
  | ---------------------- | ---------------------------------------------------------------------- |
  | `llm_eligible`         | The saved HTML shows the issue, and but finding it needs an llm.       |
  | `programmatic`         | The programatic checks can find the issue.                             |
  | `unavailable_evidence` | The HTML alone can't show the issue in question, for example an image. |
  | `ambiguous`            | The human finding itself is too unclear to judge fairly.               |

- **Its programmatic matches**: the checker results that describe the same
  problem on the same page. For example, a human "image has no alt text" finding
  matches the checker's missing-alt result for that image. A human finding can
  have several matches or none.

### Why do we need this?

We need the classifications because not every human finding is a fair test
of the model in the va-dat tool. The classification decides which
findings the model is graded on, so it isn't marked down for ones it could
never catch.

We of course need the programmatic matches because it evaluates the programatic side of the va-dat tool, but we specifically conduct the matchings at this time because the programatic checks are deterministic. They give the same results every time given the same input, so these matches only need to be reviewed once, here, instead of again in every evaluation run.

### How to create it

`human-finding-mapping-prepare` runs the programmatic checks on the captured
pages and writes a review folder with three CSVs. You only edit two of them.

`programmatic-findings.csv` is the list of every issue the programmatic checks
found, with the rule, element, and location of each. Every issue gets a
reference like `P001-F003`, which means the third issue found on the first page.
You don't edit this file, you just look up references in it.

`classifications.csv` has one row per human finding. Fill in the
`classification` column with one of the values from the table above, and say
why in `classification_reason`.

`programmatic-review.csv` is where you record the programmatic matches. It has
one row per human finding per page, so a Global finding shows up once for every
page. For each row, look through `programmatic-findings.csv` for issues on that
page that describe the same problem as the human finding:

- If you find any, put their references in `programmatic_finding_refs`,
  separated by semicolons, for example `P001-F003;P001-F007`.
- If you don't, leave `programmatic_finding_refs` blank.

Either way, explain your decision in `programmatic_reason`. Two issues that
only share a WCAG criterion aren't a match, they need to be the same problem.

Then run `human-finding-mapping-approve` with `--reviewer`. It checks that every
row is filled in and every reference is valid, and writes
`human-finding-mapping.json` to the review folder.

The mapping is tied to the exact audit file and checker output it was made
from. Finding IDs come from the spreadsheet's checksum, so editing the
spreadsheet needs a new mapping. Changing the snapshots or the checker code does
too, because runs would no longer find the approved checker results.

## 3. Run the model

`run` evaluates one saved page and `run-all` evaluates every page in
`snapshots.json`. Both take the mapping with `--human-finding-mapping`.

Without `--live`, a run is a free preview: it prepares the prompts and shows the
page count, prompt count, model settings, and prices, but sends nothing. With
`--live` it calls the model. It asks you to type `yes` first, unless you pass
`--approve-live`.

| Model               | `--model`           |
| ------------------- | ------------------- |
| Haiku 5.5 (default) | `claude-haiku-5-5`  |
| Sonnet 5.5          | `claude-sonnet-5-5` |
| Opus 5.5            | `claude-opus-5-5`   |
| GPT-6 Luna          | `gpt-6-luna`        |
| GPT-6.1 Sol         | `gpt-6.1-sol`       |

All models run at medium effort with a 24,192 token output cap. Live runs need
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the environment or `.env`.

`--max-cost-usd` is required, even for previews. The evaluator checks it between
requests, so the request in flight can go over. Costs come from the provider's
reported token usage and the prices in `execution/pricing.json`.

To evaluate one page, find its HTML file in `snapshots.json`:

```bash
uv run visionaid-evaluate run \
  --html .model-evaluation/pristine-snapshots/page-001.html \
  --source-url https://pristineai.com/ \
  --human-finding-mapping .model-evaluation/pristine-mapping-review/human-finding-mapping.json \
  --model claude-haiku-5-5 --max-cost-usd 1.00
```

`run-all` takes `--snapshots` instead of `--html` and `--source-url`, and
`--max-cost-usd` covers all pages together.

A run marked complete can still have responses the evaluator couldn't parse.
Check `format_failures` in the run's `run.json` if findings seem to be missing.

## 4. Review the LLM matches

Each page's run folder has a `review.csv` with one row per human finding on
that page. The classification and programmatic matches are already filled in
from the mapping. Don't change them: `report` rejects a review where they were
edited.

Compare each row with the LLM's findings in `normalized-llm-findings.json`, and
check `snapshot.html` when you need to confirm where something is. Fill in
three columns:

- `llm_finding_id`: the LLM finding IDs that cover the human finding, separated
  by semicolons. Blank means a miss.
- `match_reason`: why they match. Required when you enter an ID.
- `review_notes`: anything else, like partial matches. Notes don't earn credit.

Count a match when the finding describes the same problem on the same element or
section. Wording, confidence, and the suggested fix can differ. Several findings
can cover one human finding together. Don't count a finding that only shares a
WCAG criterion, points at a different element, or misses part of the problem.
Each ID can be used for only one human finding per page.

Validation can't tell a deliberate miss from a row you skipped, so go through
every row. For `run-all`, review every page under `pages/`. Global findings
appear on every page, so review them on each.

To have an agent do the review, give it the run folder and this prompt:

```text
Review LLM matches in this run, fill its LLM decision columns in review.csv, and generate the report with attribution describing your review. For a full evaluation, review every page before using report-all. Keep approved classification and Programmatic fields unchanged. Use practical semantic matching.
Count a match when a finding identifies the same underlying accessibility problem in the same element or relevant section, even if its wording, certainty, examples, or recommended fix differ from the human audit.
Treat examples in a human finding as illustrations unless they clearly describe separate defects. A different remediation recommendation does not invalidate detection.
Conditional or tentative findings can count when they identify the reported defect and the human audit supplies supporting context. Use the saved HTML to confirm the location.
Allow multiple findings from one source on one page to cover a human finding together. Reject matches that merely share a WCAG criterion, concern another element, or leave a distinct part undetected.
Inspect every row. Leave the LLM ID blank for a miss and record qualifications or partial evidence in review_notes. Apply full coverage consistently.
```

## 5. Build the report

Run `report` on a `run` folder, or `report-all` on a `run-all` folder:

```bash
uv run visionaid-evaluate report \
  --run-dir '.model-evaluation/runs/<run-id>' \
  --reviewer "Your name and review method"
```

Both check the review and refuse to report on a preview or an unfinished run.
`report-all` writes a report for each page and a combined one for the whole
site. `report` also works on a single page of a `run-all` run, in
`.model-evaluation/full-runs/<run-id>/pages/<page-run-id>/`.

Regenerating a report deletes the old one first, so a failed validation leaves
no report rather than a stale one. Copy it somewhere if you want to keep it.

### How scoring works

| Rate         | Counts                                                        |
| ------------ | ------------------------------------------------------------- |
| LLM          | LLM catches out of all `llm_eligible` findings.               |
| Programmatic | Checker catches out of all `programmatic` findings.           |
| Overall      | Findings caught by either source, out of every human finding. |

With 10 findings, 6 `llm_eligible`, 2 `programmatic`, and 2 that neither source
can test, catching all 8 testable ones gives LLM 6/6, Programmatic 2/2, and
Overall 8/10.

A catch by the "wrong" source counts toward Overall only. The Programmatic rate
is always 100% in a valid report, because a finding is only `programmatic` when
the checker fully covers it. It reflects the approved mapping and isn't a real
measure of checker recall.

In the combined report each Global finding counts once, and it's caught if a
source fully catches it on any one page. Combined rates are pooled counts, so
don't average the per-page rates to get them.

## Generated files

A `run` writes to `.model-evaluation/runs/<run-id>/`. A `run-all` writes one
folder per page to `.model-evaluation/full-runs/<run-id>/pages/<page-run-id>/`.
Each of these folders contains:

| File                                              | Contents                                                                             |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `report.html`                                     | The offline report: cost, detection rates, and a filterable table of human findings. |
| `review.csv`                                      | The review you fill in.                                                              |
| `run.json`                                        | Settings, cost, stopping reason, and `format_failures`.                              |
| `snapshot.html`                                   | The page HTML the run used.                                                          |
| `normalized-llm-findings.json`                    | LLM findings with their IDs.                                                         |
| `artifacts/normalized-programmatic-findings.json` | Checker findings with their IDs.                                                     |
| `artifacts/prompts/*.json`                        | The exact prompts sent to the model.                                                 |
| `artifacts/raw-llm-responses.json`                | Model replies and token usage.                                                       |

A `run-all` also writes two files to `.model-evaluation/full-runs/<run-id>/`:

| File          | Contents                                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `full.json`   | Settings, the cost limit, total cost and tokens across all pages, whether the run finished, and each page's URL and folder. |
| `report.html` | One report for the whole site, with rates pooled across pages and each Global finding counted once.                         |

The evaluator skips va-dat's false-positive filter and LLM deduplication, so its
findings won't match the CSV the main tool produces.
