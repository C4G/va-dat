# Evaluator guide

The evaluator checks how many findings from a human accessibility audit the va-dat
tool also catches. You give it the audit spreadsheet and saved page HTML, it runs the
programmatic checks and llm checks via one model, and a reviewer marks which tool findings
match each human finding. The report shows detection rates per source.

It measures coverage of the human audit and nothing else. Extra tool findings
don't affect the score.

The [quick start in the root README](../../README.md#evaluator-quick-start) has
the full command sequence. Run everything from the repository root. Use
`uv run visionaid-evaluate COMMAND --help` for options.

## General Workflow

Each command below runs as `uv run visionaid-evaluate <command>`.

1. **Capture the pages.** The `capture` command downloads every page listed in
   the audit and saves its HTML.
2. **Create the mapping.** The `human-finding-mapping-prepare` command writes
   review CSV files. You fill them in, then the `human-finding-mapping-approve`
   command turns them into the [mapping](#what-a-mapping-is) file. You do this
   once per audit and reuse it for every model.
3. **Run the model.** The `run` command (one page) or `run-all` command (every
   page) prepares the prompts. Without the `--live` flag it's a free preview.
   With `--live` it calls the model.
4. **Review the matches.** You edit each run's `review.csv` file to record which
   LLM findings match each human finding.
5. **Build the report.** The `report` or `report-all` command checks your review
   and writes a `report.html` file.

Every command writes to a new directory and won't overwrite earlier work.

## Human audit Excel file format

The audit spreadsheet and the mapping files are private and kept out of Git.
Put the spreadsheet in the repository root. Use  
`Pristine Accessibility Defect Report.xlsx` or any other audit in this format.

The `Defect report` tab needs these headers, in order, in the first row:

```text
Sr. #, element name, Browser Combination, Page name, Issue Title,
Steps to Reproduce, actual result, expected result, Recommendation for Fix,
WCAG Sc, Type of Change, comment
```

A `URL list` tab with a `URL` column lists the pages to evaluate. Each finding's
`Steps to Reproduce` must contain exactly one of those URLs, which is how the
evaluator assigns it to a page. A finding with `Page name` set to `Global`
applies to every page.

Finding IDs come from the file's checksum. If you edit the spreadsheet, you
need a new mapping.

## Capture

`capture` saves the HTML the server returns. It doesn't run JavaScript which should be kept in mind since modern frontend frameworks heavily rely on html to be generated via JavaScript.

## What a mapping is

A human finding mapping is a JSON file that records two decisions for each
human finding in the audit:

- **Its classification.** Which source should be able to catch it: the LLM, the
  programmatic checker, or neither (because the HTML can't show it, or the human
  finding is too vague).
- **Its programmatic matches.** va-dat's rule-based checks, which use no AI, run
  on every page and report their own list of problems. A match links a human
  finding to the checker results that describe the same problem on the same
  page, for example a human "image has no alt text" finding and the checker's
  missing-alt result for that image. A human finding can have several matches
  or none.

The scores depend on both. The LLM rate only counts `llm_eligible` findings, so
without classifications there's nothing to divide by. The checker's output
doesn't change between models, so its matches only need reviewing once.

Doing this once per audit, before any model runs, also keeps comparisons fair.
Every model is scored against the same decisions, and nobody can reclassify a
finding after seeing what a model caught. `report` rejects a `review.csv` whose
approved columns were edited.

## Approve a human finding mapping

`human-finding-mapping-prepare` writes a review folder with three CSVs. Fill in
two of them.

In `classifications.csv`, give each human finding one classification and a
reason.

| Value                  | Use it when                                                                   |
| ---------------------- | ----------------------------------------------------------------------------- |
| `llm_eligible`         | The saved HTML shows the problem, and judging it needs a model.               |
| `programmatic`         | Existing checker findings fully cover it on every page it applies to.         |
| `unavailable_evidence` | The HTML alone can't show it, for example keyboard or screen reader behavior. |
| `ambiguous`            | The finding is too unclear to judge fairly.                                   |

In `programmatic-review.csv`, list the checker findings that cover each human
finding on each page. Copy references like `P001-F003` from
`programmatic-findings.csv` and separate several with semicolons. Leave it blank
if nothing matches, and explain either way. Sharing a WCAG criterion isn't
enough for a match.

Then run `human-finding-mapping-approve` with `--reviewer`. It checks that every
row is filled in and the references are valid, and writes
`human-finding-mapping.json`. Pass that path to `run` or `run-all` with
`--human-finding-mapping`.

Keep the snapshots and checker code unchanged after approval. If the checker
output changes, runs will fail to find the approved findings, and you need a new
mapping.

## Models and cost

| Model               | `--model`           |
| ------------------- | ------------------- |
| Haiku 5.5 (default) | `claude-haiku-5-5`  |
| Sonnet 5.5          | `claude-sonnet-5-5` |
| Opus 5.5            | `claude-opus-5-5`   |
| GPT-6 Luna          | `gpt-6-luna`        |
| GPT-6.1 Sol         | `gpt-6.1-sol`       |

All models run at medium effort with a 24,192 token output cap. Live runs need
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the environment or `.env`, and ask you
to type `yes` before spending (or pass `--approve-live`).

`--max-cost-usd` is required, even for previews. The evaluator checks it between
requests, so the request in flight can go over. Costs come from the
provider's reported token usage and the prices in `execution/pricing.json`.

A run marked complete can still have responses the evaluator couldn't parse.
Check `format_failures` in `run.json` if findings seem to be missing.

## Evaluate one page

```bash
uv run visionaid-evaluate run \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --html .model-evaluation/pristine-snapshots/page-001.html \
  --source-url https://pristineai.com/ \
  --human-finding-mapping .model-evaluation/pristine-mapping-review/human-finding-mapping.json \
  --model claude-haiku-5-5 --max-cost-usd 1.00
```

Look up the HTML file for your URL in `snapshots.json`. Add `--live` to run it
for real, then review and report:

```bash
uv run visionaid-evaluate report \
  --run-dir '.model-evaluation/runs/<run-id>' \
  --reviewer "Your name and review method"
```

`report` also works on a single page inside a full run, under
`.model-evaluation/full-runs/<run-id>/pages/<child-run-id>`.

## Review LLM matches

Each run folder has a `review.csv` with one row per human finding on that page.
Compare it with `normalized-llm-findings.json`, and check `snapshot.html` when
you need to confirm where something is. Fill in three columns and leave the rest
alone.

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
every row.

To have an agent do the review, give it the run directory and this prompt:

```text
Review LLM matches in this run, fill its LLM decision columns in review.csv, and generate the report with attribution describing your review. For a full evaluation, review every page before using report-all. Keep approved classification and Programmatic fields unchanged. Use practical semantic matching.
Count a match when a finding identifies the same underlying accessibility problem in the same element or relevant section, even if its wording, certainty, examples, or recommended fix differ from the human audit.
Treat examples in a human finding as illustrations unless they clearly describe separate defects. A different remediation recommendation does not invalidate detection.
Conditional or tentative findings can count when they identify the reported defect and the human audit supplies supporting context. Use the saved HTML to confirm the location.
Allow multiple findings from one source on one page to cover a human finding together. Reject matches that merely share a WCAG criterion, concern another element, or leave a distinct part undetected.
Inspect every row. Leave the LLM ID blank for a miss and record qualifications or partial evidence in review_notes. Apply full coverage consistently.
```

## How scoring works

| Rate         | Counts                                                        |
| ------------ | ------------------------------------------------------------- |
| LLM          | LLM catches out of all `llm_eligible` findings.               |
| Programmatic | Checker catches out of all `programmatic` findings.           |
| Overall      | Findings caught by either source, out of every human finding. |

With 10 findings, 6 LLM eligible, 2 programmatic, and 2 untestable, catching all
8 testable ones gives LLM 6/6, Programmatic 2/2, and Overall 8/10.

A catch by the "wrong" source counts toward Overall only. The Programmatic rate
is always 100% in a valid report, because the mapping requires full checker
coverage for that category. It reflects the approved mapping and isn't a real
measure of checker recall.

In combined reports each Global counts once. It's caught if a source fully
catches it on any one page. Combined rates are pooled counts, so don't average
the per-page rates to get them.

## Reports and saved files

`report.html` is a single offline file. It shows cost, detection rates, and a
table of human findings you can expand and filter. **Print report** prints the
summary without the findings table.

The run folder keeps everything else. The files you'll most likely open are:

| File                                              | Contents                                                |
| ------------------------------------------------- | ------------------------------------------------------- |
| `review.csv`                                      | The review you fill in.                                 |
| `run.json`                                        | Settings, cost, stopping reason, and `format_failures`. |
| `normalized-llm-findings.json`                    | LLM findings with their IDs.                            |
| `artifacts/normalized-programmatic-findings.json` | Checker findings with their IDs.                        |
| `artifacts/prompts/*.json`                        | The exact prompts sent to the model.                    |
| `artifacts/raw-llm-responses.json`                | Model replies and token usage.                          |

A full run adds `full.json` with the page order and totals, plus a folder per
page under `pages/`.

Regenerating a report deletes the old one first, so a failed validation leaves
no report rather than a stale one. Copy it somewhere if you want to keep it.

The evaluator skips va-dat's false-positive filter and LLM deduplication, so its
findings won't match the CSV the main tool produces.

## Troubleshooting

| Problem                                | Fix                                                                        |
| -------------------------------------- | -------------------------------------------------------------------------- |
| Approved mapping required              | Prepare and approve a mapping, then pass `--human-finding-mapping`.        |
| Audit checksum or page mismatch        | Use the same spreadsheet and snapshots the mapping was approved with.      |
| Expected checker finding not found     | The snapshot or checker code changed. Restore it or approve a new mapping. |
| Directory or output already exists     | Pick a new path.                                                           |
| Missing LLM findings in a complete run | Check `format_failures` in `run.json` and the raw responses.               |
| Unknown or reused finding ID           | Copy IDs from this page's findings file and use each once.                 |

Older run folders from before the current layout aren't supported. Make new runs
instead.
