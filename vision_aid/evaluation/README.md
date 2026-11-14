# Evaluator Overview

This evaluator measures how many findings from a human accessibility audit the
va-dat tool also catches. It only measures coverage of the human audit. Extra
problems the tool reports don't help or hurt the score.

va-dat finds problems in two ways, and the evaluator reports on each one
separately:

1. **Programmatic checks**: va-dat's rule-based checks. They use no AI, so they
   give the same results on a page no matter which model you test.
2. **LLM checks**: va-dat sends parts of the page to a model and asks it to find
   problems. This is the part you compare across models.

This guide calls these the two sources.

Each problem in the human audit is a **human finding**. A **match** links a human
finding to the tool findings that describe the same problem on the same page.

Run every command from the repository root as
`uv run visionaid-evaluate <command>`, and add `--help` to any command to see
its options. The [quick start in the root README](../../README.md#evaluator-quick-start)
has the full command sequence to copy.

## General Workflow

1. **[Capture the pages](#1-capture-the-pages).** `capture` downloads every page
   listed in the audit and saves its HTML.
2. **[Create the mapping](#2-create-the-mapping).** `human-finding-mapping-prepare`
   writes review CSV files. In them you record which source should catch each
   human finding and which issues from the programmatic checks already match
   it. Then
   `human-finding-mapping-approve` checks your answers and turns them into the
   mapping file. You do this once per audit and reuse the mapping for every
   evaluation run.
3. **[Run the model](#3-run-the-model).** `run` (one page) or `run-all` (every
   page) sends the prompts to the model you choose.
4. **[Review the LLM matches](#4-review-the-llm-matches).** You record which LLM
   findings match each human finding.
5. **[Build the report](#5-build-the-report).** `report` or `report-all` checks
   your review and writes `report.html`.

`capture`, `human-finding-mapping-prepare`, `run`, and `run-all` each write to a
new folder, so they never overwrite earlier work. `report` and `report-all`
replace the old report in the run folder.

## The human audit file

The human audit is an Excel file. Commands read
`Pristine Accessibility Defect Report.xlsx` from the repository root by default,
and Git ignores that name. To use another human audit in the same format, pass
`--human-audit`.

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

Name the folder to save them in with `--output-dir`. The folder can't exist yet.

```bash
uv run visionaid-evaluate capture \
  --human-audit './Pristine Accessibility Defect Report.xlsx' \
  --output-dir .model-evaluation/pristine-snapshots
```

`capture` doesn't run JavaScript, so a page that builds its content with
JavaScript is saved mostly empty. This can be a problem with websites built on modern frontend frameworks like React.js, so keep that in mind.

## 2. Create the mapping

### What is a mapping?

A human finding mapping is a JSON file that records two decisions for each
human finding:

- **Its classification**: which source should be able to catch it.

    | Value                  | Use it when                                                                    |
    | ---------------------- | ------------------------------------------------------------------------------ |
    | `llm_eligible`         | The saved HTML shows the issue, but finding it needs an LLM.                   |
    | `programmatic`         | The programmatic checks report the issue on the saved page.                    |
    | `unavailable_evidence` | The saved HTML can't show the issue, for example low contrast inside an image. |
    | `ambiguous`            | The human finding itself is too unclear to judge fairly.                       |

- **Its programmatic matches**: the issues from the programmatic checks that
  describe the same problem on the same page. For example, a human "image has no
  alt text" finding matches the programmatic checks' missing-alt issue for that
  image. A human finding can
  have several matches or none.

### Why do we need this?

We need the classifications because not every human finding is a fair test
of the model in the va-dat tool. The classification decides which
findings the model is graded on, so it isn't marked down for ones it could
never catch.

The programmatic matches give the programmatic checks credit for the human
findings they catch. You record them here, not in each run, because the
programmatic checks give the same results every time for the same HTML.
Reviewing them once is enough.

### How to create it

The `human-finding-mapping-prepare` command runs the programmatic checks on the
captured pages and writes a review folder. Point `--snapshots` at the
`snapshots.json` from step 1, and name a new folder for the review with
`--output-dir`:

```bash
uv run visionaid-evaluate human-finding-mapping-prepare \
  --human-audit './Pristine Accessibility Defect Report.xlsx' \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --output-dir .model-evaluation/pristine-mapping-review
```

The review folder has three CSVs. You look things up in the first and fill in
the other two.

- `programmatic-findings.csv` is the list of every issue the programmatic
  checks found, with the rule, element, and location of each. Every issue gets a
  reference like `P001-F003`, which means the third issue found on the first
  page. You don't edit this file. You only look up references in it.
- `classifications.csv` has one row per human finding. For each row, read the
  human finding and decide who should be able to catch it: the LLM, the
  programmatic checks, or neither. Then fill in two columns:
    - `classification`: one of the four values from the
      [classification table](#what-is-a-mapping), such as `llm_eligible`.
    - `classification_reason`: a sentence on why you picked it, for example "The
      focus order can't be seen in the HTML."

    If you classify a finding as `programmatic`, you also need to list matching
    issues for it on every page in `programmatic-review.csv`. If you classify it
    as `unavailable_evidence` or `ambiguous`, you can't list any.

- `programmatic-review.csv` is where you record the programmatic matches. It
  has one row per human finding per page, so a `Global` finding shows up once
  for every page. For each row, look through `programmatic-findings.csv` for
  issues on that page that describe the same problem as the human finding:
    - If you find any, put their references in the `programmatic_finding_refs`
      column, separated by semicolons, for example `P001-F003;P001-F007`.
    - If you don't, leave that column blank.

    Either way, explain your decision in the `programmatic_reason` column.
    Sharing a WCAG criterion isn't enough. The issue has to describe the same
    problem as the human finding.

Once you've filled in `classifications.csv` and `programmatic-review.csv`, run
the `human-finding-mapping-approve` command. It takes the same `--snapshots`,
the review folder in `--review-dir`, and your name in `--reviewer`:

```bash
uv run visionaid-evaluate human-finding-mapping-approve \
  --human-audit './Pristine Accessibility Defect Report.xlsx' \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --review-dir .model-evaluation/pristine-mapping-review \
  --reviewer "Your name"
```

It checks that every row is filled in and every reference is valid, and writes
the mapping to `human-finding-mapping.json` in the review folder. Pass `--output`
to save it somewhere else.

The snapshots and the mapping are both tied to the exact audit file. If the
spreadsheet changes at all, even by re-saving it, start again from `capture`.

A run also stops with an error if it can't find an issue the mapping approved.
That can happen after a new capture or a change to the programmatic checks. Make
a new mapping when it does.

## 3. Run the model

`run` evaluates one saved page and `run-all` evaluates every page in
`snapshots.json`. Both take the mapping with `--human-finding-mapping`.

Without `--live`, a run is a free preview. It prepares the prompts and prints the
prompt count, model settings, and prices, but sends nothing. With `--live` it
calls the model. It asks you to type `yes` first, unless you pass
`--approve-live`.

Every run, preview or live, writes to a new folder and prints its path. Steps 4
and 5 need the folder from the live run.

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

To evaluate one page, find its HTML file and URL in `snapshots.json` and pass
them as `--html` and `--source-url`:

```bash
uv run visionaid-evaluate run \
  --human-audit './Pristine Accessibility Defect Report.xlsx' \
  --html .model-evaluation/pristine-snapshots/page-001.html \
  --source-url https://pristineai.com/ \
  --human-finding-mapping .model-evaluation/pristine-mapping-review/human-finding-mapping.json \
  --model claude-haiku-5-5 --max-cost-usd 1.00
```

This command is a preview. Add `--live` to call the model.

`run-all` takes `--snapshots` instead of `--html` and `--source-url`, and
`--max-cost-usd` covers all pages together:

```bash
uv run visionaid-evaluate run-all \
  --human-audit './Pristine Accessibility Defect Report.xlsx' \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --human-finding-mapping .model-evaluation/pristine-mapping-review/human-finding-mapping.json \
  --model claude-haiku-5-5 --max-cost-usd 5.00
```

The evaluator sends each prompt once, with no retries. If a request fails or the
cost reaches the limit, the run stops and `run.json` records it as incomplete,
with the cause in `incomplete_reason`. You can't report on an incomplete run, and
running again starts over and pays for every request again.

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
section. Don't count a finding that only shares a
WCAG criterion, points at a different element, or misses part of the problem.
Each ID can be used for only one human finding per page.

For `run-all`, review every page under `pages/`. Global findings
appear on every page, so review them on each.

To have an agent do the review, give it the run folder and this prompt:

```text
Review LLM matches in this run, fill its LLM decision columns in review.csv, and generate the report with attribution describing your review. For a full evaluation, review every page before using report-all. Keep approved classification and Programmatic fields unchanged.
Count a match when a finding identifies the same underlying accessibility problem in the same element or relevant section, even if its wording, certainty, examples, or recommended fix differ from the human audit.
Treat examples in a human finding as illustrations unless they clearly describe separate defects. A different remediation recommendation does not invalidate detection.
Conditional or tentative findings can count when they identify the reported defect and the human audit supplies supporting context. Use the saved HTML to confirm the location.
Allow multiple findings from one source on one page to cover a human finding together. Reject matches that merely share a WCAG criterion, concern another element, or leave a distinct part undetected.
Inspect every row. Leave the LLM ID blank for a miss and record qualifications or partial evidence in review_notes.
```

## 5. Build the report

Run `report` on a `run` folder, or `report-all` on a `run-all` folder. Both
take the folder in `--run-dir` and who did the review in `--reviewer`:

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
| Programmatic | Programmatic catches out of all `programmatic` findings.      |
| Overall      | Findings caught by either source, out of every human finding. |

The Programmatic rate isn't a real measure of the programmatic checks. A finding
is only classified `programmatic` when the checks already catch it, so the rate
is 100% whenever there are any such findings. With none, the report shows the
rate as not defined.

A finding caught only by the other source counts toward Overall, not toward
either source's catch rate.

With 10 findings, 6 `llm_eligible`, 2 `programmatic`, and 2 that neither source
can test, catching all 8 testable ones gives LLM 6/6, Programmatic 2/2, and
Overall 8/10.

In the combined report each Global finding counts once, and it's caught if a
source catches it on any one page.

## Generated files

A `run` writes to `.model-evaluation/runs/<run-id>/`. A `run-all` writes one
folder per page to `.model-evaluation/full-runs/<run-id>/pages/<page-run-id>/`.
Each of these folders contains:

| File                                              | Contents                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `report.html`                                     | The offline report: cost, detection rates, and a filterable table of human findings.  |
| `review.csv`                                      | The review you fill in.                                                               |
| `run.json`                                        | The model and its request settings, the cost, stopping reason, and `format_failures`. |
| `snapshot.html`                                   | The page HTML the run used.                                                           |
| `normalized-llm-findings.json`                    | LLM findings with their IDs.                                                          |
| `artifacts/normalized-programmatic-findings.json` | Programmatic check issues with their IDs.                                             |
| `artifacts/prompts/*.json`                        | The exact prompts sent to the model.                                                  |
| `artifacts/raw-llm-responses.json`                | Model replies and token usage.                                                        |

A `run-all` also writes two files to `.model-evaluation/full-runs/<run-id>/`:

| File          | Contents                                                                                                                                              |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `full.json`   | The model and its request settings, the cost limit, total cost and tokens across all pages, whether the run finished, and each page's URL and folder. |
| `report.html` | One report for the whole site, with rates pooled across pages and each Global finding counted once.                                                   |

The evaluator skips va-dat's false-positive filter and LLM deduplication, so its
findings won't match the CSV the main tool produces.

## Command Overview

| Command                         | When to run                                                                    | What it does                                                                                                            | Required flags                                                        | Optional flags                                         |
| ------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------ |
| `capture`                       | Once per audit                                                                 | Downloads the HTML for every URL in the audit and writes `snapshots.json`                                               | `--output-dir`                                                        | `--human-audit`                                        |
| `human-finding-mapping-prepare` | Once per audit, after `capture`                                                | Runs the programmatic checks on the snapshots and writes the three review CSVs                                          | `--snapshots`, `--output-dir`                                         | `--human-audit`                                        |
| `human-finding-mapping-approve` | Once per audit, after the reviewer fills in the CSVs                           | Checks the CSVs for completion and saves the mapping file                                                               | `--snapshots`, `--review-dir`, `--reviewer`                           | `--output`, `--human-audit`                            |
| `run`                           | Each time you test a model on one page                                         | Runs the programmatic checks and saves the prompts for one saved HTML file. With `--live`, sends the prompts to the LLM | `--html`, `--source-url`, `--max-cost-usd`, `--human-finding-mapping` | `--model`, `--live`, `--approve-live`, `--human-audit` |
| `run-all`                       | Each time you test a model on the whole audit                                  | Does what `run` does for every snapshot                                                                                 | `--snapshots`, `--max-cost-usd`, `--human-finding-mapping`            | `--model`, `--live`, `--approve-live`, `--human-audit` |
| `report`                        | After a `run` with `--live`, once the reviewer fills in `review.csv`           | Checks the review and writes `report.html` for that page                                                                | `--run-dir`, `--reviewer`                                             |                                                        |
| `report-all`                    | After a `run-all` with `--live`, once the reviewer fills in every `review.csv` | Checks every review and writes one report per page plus a combined one                                                  | `--run-dir`, `--reviewer`                                             |                                                        |
