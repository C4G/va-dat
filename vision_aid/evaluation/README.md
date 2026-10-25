# Evaluator guide

The evaluator compares va-dat's programmatic and LLM findings with an existing
human accessibility audit. A reviewer selects complete matches; the evaluator
validates the evidence and calculates detection rates. Each invocation uses one
fixed model preset against saved HTML.

Start with the [quick start in the repository README](../../README.md#evaluator-quick-start)
for the complete command sequence. **Run all commands in this guide from the
repository root**, the `va-dat/` directory containing `pyproject.toml` and the
root README. All relative paths in the examples start there, even though this
guide lives in `vision_aid/evaluation/`.

- [Inputs and command reference](#inputs-and-command-reference)
- [Capture and reuse snapshots](#capture-and-reuse-snapshots)
- [Approve a human finding mapping](#approve-a-human-finding-mapping)
- [Model settings and execution](#model-settings-and-execution)
- [Evaluate one page](#evaluate-one-page)
- [Review LLM matches](#review-llm-matches)
- [How scoring works](#how-scoring-works)
- [How responses become findings](#how-responses-become-findings)
- [Reports and saved files](#reports-and-saved-files)
- [Troubleshooting and compatibility](#troubleshooting-and-compatibility)

## Inputs and command reference

An evaluation needs a human audited Excel file, saved page HTML, and an approved human
finding mapping. Live execution also needs the selected provider's API key and
a positive spending allowance. Preview requires the approved mapping and a
positive allowance, but needs no key and makes no model requests.

Place the human audited Excel file, `Pristine Accessibility Defect Report.xlsx`,
directly in the repository root, alongside `pyproject.toml` and the root README.
The commands below expect it at `./Pristine Accessibility Defect Report.xlsx`.

The file and mapping are private local inputs, excluded from Git. Mappings
are not installed as package data. A fresh checkout must supply an approved
mapping or create one through CSV review. Obtain the project's human audited Excel file from
your project team or use a compatible audit of your own.

| Command | Purpose | Model requests |
| --- | --- | --- |
| `capture` | Download each URL listed in the human audit file and save `snapshots.json`. | None; downloads web pages. |
| `human-finding-mapping-prepare` | Create classification and programmatic-match review CSVs from saved inputs. | None. |
| `human-finding-mapping-approve` | Validate completed CSVs and export an approved mapping. | None. |
| `run` | Prepare one page and optionally execute its prompts. | Only with `--live` and approval. |
| `run-all` | Prepare every listed page and optionally execute them with one shared allowance. | Only with `--live` and approval. |
| `report` | Validate one completed page's review and generate its HTML report. | None. |
| `report-all` | Validate a completed full evaluation and generate combined and page reports. | None. |

Use `uv run visionaid-evaluate COMMAND --help` for a command's options.
`entry_points/model_evaluation.py` is a compatibility entry point to the same CLI.

### Human audited Excel file format

The importer expects a human audited Excel file with a `Defect report` tab.
Its first row must begin with these exact headers, in this order:

```text
Sr. #
element name
Browser Combination
Page name
Issue Title
Steps to Reproduce
actual result
expected result
Recommendation for Fix
WCAG Sc
Type of Change
comment
```

Each subsequent finding row needs an `Issue Title`. Original cell text, tab
name, and row number are preserved in the review evidence. Human finding IDs
derive from the entire file's SHA-256, tab, and source row. Changing the
file's bytes changes its identity and requires a new mapping review.

Capture, full evaluation, and mapping authoring also require a `URL list` tab
whose first row includes a `URL` column. Non-empty URLs define page identity and
execution order. Full input loading rejects repeated target URLs.

For each local finding, `Steps to Reproduce` must identify exactly one listed
target URL. Page names and recommendation URLs do not assign findings. Matching
uses the listed URL text; the known `/Contact/` alias maps to `/contact/`, while
other paths retain their case. Missing or ambiguous assignments stop preparation.
A finding whose `Page name` is `Global`, ignoring case and surrounding spaces,
applies to every listed page. Globals repeat in page reviews but retain one
original identity.

The project's Pristine audit has 86 original findings across 17 pages. Repeated
Globals produce 198 page-review rows; the homepage has 16 Home or Global rows.
These counts describe that human audit file, rather than limits imposed by the
evaluator.

The single-page importer retains Home and Global selection for older human audit
files without a `URL list`. The current mapping-authoring commands require that
tab; there is no CSV authoring route for those older files without adding it and
reviewing the resulting new human audit file identity.

## Capture and reuse snapshots

```bash
uv run visionaid-evaluate capture \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --output-dir .model-evaluation/pristine-snapshots
```

The output directory must be new. Capture downloads only listed URLs in source
order and follows redirects, retaining the originally listed URLs as page
identities. It saves `page-001.html`, `page-002.html`, and later files, then
writes `snapshots.json` with the audit checksum and relative HTML filenames.
Resolve filenames beside that mapping when reusing saved inputs.

Capture saves server HTML. It does not render JavaScript, interact with the page,
or discover more URLs. Inspect the saved content; if important content requires
rendering, replace the relevant HTML with a rendered snapshot before mapping
review. Reuse those same snapshots across models. Downloading again can change
checker evidence and prevent an approved mapping from resolving.

An HTTP or network error stops capture. Earlier HTML remains, but no snapshot
mapping is published until every download succeeds. Address the failure and
capture into a new directory.

Full input loading requires the mapping's audit checksum and ordered URLs to
match the human audit file. HTML paths must be relative, remain within the mapping's
directory, and point to existing files. Later evaluation commands read these
saved files without downloading again.

## Approve a human finding mapping

A mapping records each original finding's classification and its approved
programmatic matches or explained absence of matches on every applicable page.
Approve this independently of model output, then reuse it across model runs.
LLM matches are reviewed separately after each execution.

```bash
uv run visionaid-evaluate human-finding-mapping-prepare \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --output-dir .model-evaluation/pristine-mapping-review
```

Preparation reads the human audit file and saved snapshots and runs existing
programmatic checks. It makes no network or model requests and requires no model
choice, credentials, or allowance. The output directory must be new. It contains
three CSVs and a README:

| File | Review action |
| --- | --- |
| `classifications.csv` | Classify each original finding once, including each Global once. Fill `classification` and `classification_reason`. |
| `programmatic-review.csv` | Decide programmatic coverage for each applicable finding and page. Fill `programmatic_finding_refs` and `programmatic_reason`. |
| `programmatic-findings.csv` | Read-only checker catalog with references, page URLs, rule IDs, descriptions, elements, targets, and locations. |

### Classifications

| Value | Use it when |
| --- | --- |
| `llm_eligible` | Saved HTML contains enough evidence to judge the defect, and the issue needs semantic judgment or checks absent from existing rules. |
| `programmatic` | Existing checker findings fully cover the defect on every applicable page. Approval requires complete matches, rather than a rule that could theoretically detect it. |
| `unavailable_evidence` | Saved HTML lacks evidence needed to verify the defect, such as interaction or browser and assistive technology observations. |
| `ambiguous` | The human finding is too unclear to decide fairly whether tool findings cover it. |

Explain each choice in `classification_reason`. A Global has one classification
shared across all its pages. The workflow does not infer classifications or
change checker rules.

### Programmatic matches

Copy references such as `P001-F003` from the catalog into the matching page row.
Separate joint matches with semicolons, such as `P001-F003;P001-F004`, and explain
how they cover the whole human defect. A shared WCAG criterion is insufficient.
Select only that page's findings and use each reference for at most one human
finding. For no complete match, leave references blank and explain the absence.
Every page row requires a deliberate decision.

Programmatic classifications require complete matches on every applicable page.
LLM-eligible findings may have programmatic cross-catches. Unavailable and
ambiguous findings cannot claim matches. The [matching rules](#review-llm-matches)
also explain practical semantic coverage.

Keep original evidence, identities, headers, and every row unchanged. Sorting
rows is allowed. Save the two edited files as CSV; keep the catalog unchanged.

```bash
uv run visionaid-evaluate human-finding-mapping-approve \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --review-dir .model-evaluation/pristine-mapping-review \
  --reviewer "Your name and review method"
```

Approval rereads the original inputs, reruns checks, and verifies that the
catalog and original CSV evidence still agree. Keep snapshots and checker code
unchanged during review. Changed checker results require a new review.
Approval validates completeness, classifications, page ownership, unique
matches, and finding reuse. The reviewer decides whether matches semantically
cover the defect; the command records that judgment.

The output is `human-finding-mapping.json` in the review directory. Use `--output`
to choose another new filename. Approval refuses to overwrite an existing
mapping. Errors identify the affected file, finding, or page; edit the CSV and
retry. No reviewer needs to write JSON or calculate checksums.

### Mapping identity and reuse

Pass `--human-finding-mapping PATH` to `run` or `run-all`. Approval's default
output location is not automatically searched. Without an explicit path, the
CLI looks only for
`vision_aid/evaluation/human_finding_mappings/<audit-sha256>.json`, an ignored
local directory. Model and snapshot identities do not select a mapping.

Catalog references are review aids. Approval converts selected findings into
rule and evidence expectations. New runs resolve each expectation against their
own checker output to obtain actual finding IDs. Missing or non-unique matches
stop preparation or reporting with the finding, page, rule, and evidence to
investigate. An empty expectation list records an approved absence of coverage.

Each run copies the complete approved mapping to
`artifacts/human-finding-mapping.json` and records its checksum and approval
attribution. Full evaluations save the same mapping in the parent and every
child. Reporting uses those saved copies and rejects changes to fixed decisions.
Later edits to the original shared file do not rewrite historical runs.

To change approved decisions or checker rules, prepare and approve a new review
and create new runs. An unchanged audit checksum does not guarantee that new
page HTML or changed checker evidence will satisfy old expectations.

## Model settings and execution

Each run accepts one of these exact IDs. Friendly names and aliases are rejected.

| Model | `--model` | Endpoint | Thinking or reasoning |
| --- | --- | --- | --- |
| Haiku 5.5, default | `claude-haiku-5-5` | Anthropic Messages | Adaptive thinking, medium effort |
| Opus 5.5 | `claude-opus-5-5` | Anthropic Messages | Adaptive thinking, medium effort |
| Sonnet 5.5 | `claude-sonnet-5-5` | Anthropic Messages | Adaptive thinking, medium effort |
| GPT-6 Luna | `gpt-6-luna` | OpenAI Chat Completions | Medium reasoning effort |
| GPT-6.1 Sol | `gpt-6.1-sol` | OpenAI Chat Completions | Medium reasoning effort |

All presets omit temperature, disable summary prompts, and cap output at 24,192
tokens including thinking or reasoning and final text. Adaptive thinking does
not reserve a fixed final-text allowance. Equal effort labels and caps do not
establish equal computation between providers. Runs save the chosen model,
provider, endpoint, and settings.

The [root quick start](../../README.md#evaluator-quick-start) shows `run-all`
preview and live commands. Preparation creates every child page before showing
the full scope and asking for one live approval. Preview shows ordered pages,
prompt counts, settings, saved token prices, and the shared allowance.

Live Claude execution requires `ANTHROPIC_API_KEY`; live GPT execution requires
`OPENAI_API_KEY`, in the environment or repository-root `.env`. A missing key
stops live execution. Type exactly `yes` in an interactive terminal or pass
`--approve-live` for noninteractive approval. That flag requires `--live`.
Declined approval leaves prepared files and makes no model requests.

Every invocation creates a fresh directory. A preview remains incomplete and
cannot produce a final report. Adding `--live` to a later invocation creates
another run; it does not execute the previous preview directory.

### Page preparation and execution

Preparation copies each snapshot, imports local findings and all Globals, runs
the programmatic checks, and saves extractor payloads. The pipeline filters
payloads using programmatic results before slicing them into prompts. For
example, it can remove empty headings or skip a missing-title prompt. Empty
slices can also skip requests. The model sees extracted and filtered data;
inspect saved prompts to determine whether relevant evidence reached it.

Requests execute sequentially, in listed page order for full evaluations,
without retries or fallback models. Each request's responses and usage are saved
as execution progresses. A request failure stops later requests and pages.
Unreadable successful responses are recorded separately and execution continues.
Thus `complete: true` means execution completed, not that every response parsed
or every human finding was detected. Check `format_failures` in each `run.json`.

A full evaluation saves ordered page membership, status, stopping reason, cost,
and usage in `full.json`. Preparation failures retain earlier and partial
evidence. Execution failures retain completed and partial page evidence,
including reported usage from failed requests. A completed child can still
produce an individual report if a later page fails.

There is no resume or paid-output reuse command. After failure, a fresh live
invocation repeats all model requests, including pages completed previously.
Captured input HTML can be reused without downloading.

### Cost accounting

`--max-cost-usd` must be positive, including in previews. It is a limit checked
between requests, not a hard billing cap. A request underway can exceed it.
Execution completes after an overshoot if no work remains; otherwise it stops
before starting further requests. Full evaluation subtracts prior pages' saved
estimated costs and passes the remaining allowance to the next page.

Cost uses provider-reported usage and a saved, versioned public price schedule.
Each request selects its own price tier. GPT models use the higher tier above
272,000 total input tokens; Haiku 5.5 uses it above 100,000. Equality uses the
lower tier. Input counts from separate requests are not combined for tier
selection.

OpenAI cache reads and writes replace ordinary input charges. Completion usage
already includes reasoning. Anthropic cache categories are separate input
counts; the saved write rate is for five-minute caching. Raw responses retain
unchanged provider usage alongside disjoint billable categories and request
costs. Reports show saved estimated costs rather than repricing past runs.

## Evaluate one page

Use the same audit, approved mapping, and saved snapshot as the full workflow.
Find the desired URL's HTML filename in `snapshots.json`; `page-001.html` below
assumes the homepage is the first listed URL.

```bash
uv run visionaid-evaluate run \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --html .model-evaluation/pristine-snapshots/page-001.html \
  --source-url https://pristineai.com/ \
  --human-finding-mapping .model-evaluation/pristine-mapping-review/human-finding-mapping.json \
  --model claude-haiku-5-5 --max-cost-usd 1.00
```

This previews one page. Repeat with `--live` to start a fresh paid run. For a
human audit file with a `URL list`, the source URL selects its local findings and all
Globals. Unlisted URLs are rejected. Mapping authoring still reviews the
human audit file's full set of listed pages even if only one page will be executed.

After execution completes, review the printed run directory's `review.csv`, then:

```bash
uv run visionaid-evaluate report \
  --run-dir '.model-evaluation/runs/<live-run-id>' \
  --reviewer "Your name and review method"
```

The same `report` command accepts a completed child directory under
`.model-evaluation/full-runs/<run-id>/pages/<child-run-id>`, including after a
later page fails. Open that directory's `report.html`.

## Review LLM matches

After execution, compare `review.csv` with `normalized-llm-findings.json` and use
`snapshot.html` to verify the location and defect. Programmatic evidence is in
`artifacts/normalized-programmatic-findings.json`. Every applicable human finding
has one CSV row; review Globals separately on every page.

Edit only these columns:

| Column | What to enter |
| --- | --- |
| `llm_finding_id` | Finding IDs that jointly cover the whole human finding, separated by semicolons. Leave blank for a miss. |
| `match_reason` | Explain how the selected LLM findings cover the reported defect. Required when selecting LLM IDs. |
| `review_notes` | Optional qualifications, location details, or partial evidence. Notes alone award no credit. |

Keep `classification`, `classification_reason`, `programmatic_finding_id`, and
`programmatic_match_reason` unchanged. Those fields come from the approved
mapping. Keep all original evidence, IDs, headers, and rows. `source_sheet` and
`source_row` point back to the human audit file; `source_element` copies its element
name, rather than an inferred page location. `page_scope` can be `home`, `page`,
or `global`.

### Complete-match rules

- Match the same underlying accessibility problem in the same element or
  relevant section. Different wording, certainty, examples, or recommended fixes
  can still describe a valid detection.
- Treat examples as illustrations unless they clearly describe distinct defects.
  A different remediation recommendation does not invalidate detection.
- Conditional or tentative findings can count when they identify the reported
  defect and the human audit supplies supporting context. Confirm the location
  in the saved HTML and record qualifications in notes.
- Several findings from one source on one page can jointly cover a human
  finding. Reject matches that only share a WCAG criterion, identify another
  element, or leave a distinct part of the defect undetected.
- Each ID must exist in the correct source's findings file and can be assigned
  to only one human finding within that page review. Do not repeat an ID within
  a row.
- LLM and programmatic sources can each fully catch the same finding. Partial
  coverage from different sources does not combine into a complete catch.
- Unavailable and ambiguous findings cannot claim either source's matches.

A blank LLM ID is scored as a miss. Validation cannot distinguish a deliberate
miss from an unreviewed row, so inspect every row before reporting. It validates
structural rules and saved evidence; semantic coverage remains the reviewer's
judgment.

### Using an agent for review

Give an agent the specific live run directory and this prompt:

```text
Review LLM matches in this run, fill its LLM decision columns in review.csv, and generate the report with attribution describing your review. For a full evaluation, review every page before using report-all. Keep approved classification and Programmatic fields unchanged. Use practical semantic matching.
Count a match when a finding identifies the same underlying accessibility problem in the same element or relevant section, even if its wording, certainty, examples, or recommended fix differ from the human audit.
Treat examples in a human finding as illustrations unless they clearly describe separate defects. A different remediation recommendation does not invalidate detection.
Conditional or tentative findings can count when they identify the reported defect and the human audit supplies supporting context. Use the saved HTML to confirm the location.
Allow multiple findings from one source on one page to cover a human finding together. Reject matches that merely share a WCAG criterion, concern another element, or leave a distinct part undetected.
Inspect every row. Leave the LLM ID blank for a miss and record qualifications or partial evidence in review_notes. Apply full coverage consistently.
```

## How scoring works

Rates measure coverage of the supplied human audit. They do not measure
precision, false-positive rate, remediation quality, or every accessibility
defect on the site. Unmatched tool findings do not independently lower scores.
One homepage result cannot establish broad model equivalence.

| Rate | Caught count | Denominator |
| --- | --- | --- |
| LLM | LLM catches among `llm_eligible` findings. | All `llm_eligible` findings. |
| Programmatic | Programmatic catches among `programmatic` findings. | All `programmatic` findings. |
| Overall | Human findings fully caught by either source, counting each once. | All imported human findings, including unavailable and ambiguous findings. |

A cross-catch helps Overall but earns no credit in the expected source's rate.
For example, an LLM catch of a Programmatic-classified defect does not increase
the LLM rate. Findings with unavailable evidence or ambiguous descriptions stay
outside both source denominators and remain in Overall. A zero denominator
produces an undefined rate with an explanation and no bar.

For ten findings with six LLM eligible, two Programmatic, and two not testable,
complete detection of all eight testable findings gives LLM 6/6, Programmatic
2/2, and Overall 8/10. Both source rates are 100%; Overall is 80%.

The current mapping workflow requires complete checker matches for every
Programmatic-classified finding on every applicable page. Reporting rejects
missing expected checker evidence. Consequently, the Programmatic rate in a
successfully validated report is 100% whenever that category is non-empty.
It records approved checker coverage; it does not independently measure checker
recall against a set of potentially missed Programmatic findings.

### Combined results and Globals

Combined results count each original finding once. A Global earns source credit
when that source completely catches it on any single page. Multiple selected
findings on that page may jointly cover it. Partial evidence spread across
pages cannot earn credit. LLM and programmatic complete catches may come from
different pages, but Overall still counts the Global once. Repeated catches on
several pages also count once.

The approved mapping fixes each Global's classification across pages. Each
original enters its source denominator once, including a miss by that source.
Combined rates use pooled original-finding counts, not averages of page rates.
Page charts repeat Globals and have different eligible counts; do not add page
counts or average percentages to reconstruct combined scores. Page comparisons
are not controlled rankings of page or model quality.

## How responses become findings

The evaluator uses va-dat's JSON parser, including its code-fence and repair
steps. A response that cannot be parsed, or whose shape the check cannot read,
is Unreadable. Examples include one object where a list is required, or text
where `issues`, `vague_headings`, or `header_clarity_issues` must be a list.
An Unreadable response contributes no findings, is listed under `format_failures`
in `run.json`, and does not stop subsequent checks.

### Checks covered by the tool's CSV report

For the 12 checks with CSV normalizers, each row those rules would produce
becomes one LLM finding:

| Checks | Finding rule |
| --- | --- |
| Page title, landmarks | One finding per `issues` entry. Answers such as `is_descriptive` do not create findings. |
| Headings | One finding per `issues` entry and per `vague_headings` entry. |
| Link clarity, iframe titles, label quality, decorative verification | One finding per item whose `is_clear`, `is_descriptive`, or `likely_decorative` verdict is `false`. A missing verdict counts as a pass. |
| Required field indicators, informative alt quality, actionable image alt, SVGs, icon fonts | One finding per item with a non-empty `issues` list, joining its issues. A false yes/no answer alone does not create a finding. |

Problem, element, and location text use what va-dat would write in its CSV row.
`raw_source` preserves the full item, or for page title, headings, and landmarks
the whole response plus its specific issue.

Evaluation skips the tool's later false-positive filter and LLM deduplication.
The filter guesses from page HTML and can remove a finding other than the one
it matched. Deduplication costs extra model calls and is not repeatable.
Evaluation output therefore differs from the downloadable tool CSV. The
earlier payload filtering described under [execution](#page-preparation-and-execution)
still applies.

### Checks shown on screen only

Six checks have no CSV report normalizer: `table_semantics`,
`placeholder_as_label`, `group_labels`, `form_instructions`,
`complex_descriptions`, and `media_captions`. The evaluator still reads them.
It produces at most one finding per item with non-empty `issues`, or for tables,
`issues` or `header_clarity_issues`. Every `placeholder_as_label` item is a
finding because its input consists of placeholder-only fields. Yes/no answers
alone never create findings. Tables may return one object or a list.

These findings carry `"screen_only": true`. Matched evidence in HTML reports
labels them as shown on screen only and absent from the tool's CSV report.

## Reports and saved files

`report-all` requires every listed page's execution and review to validate.
It checks ordered membership, evidence ownership, saved mappings, approved
decisions, and actual expected checker findings before producing combined
results. It writes the parent's `report.html` and every child's `report.html`.
Both reporting commands require reviewer attribution and make no model requests.

Reports begin with cost, recorded usage, saved public price information, and
detection bars. Each bar has textual caught counts, eligible counts, and a
percentage. Full reports also compare page LLM rates in audit order. The human
findings table follows the human audit file's original order.

Open **View details** for the original human evidence, then **View page decisions**
for classifications, recorded explanations, mapping approval attribution,
matched findings, check identities, LLM rationale, and notes. Globals in full
reports include a table of page decisions. Native disclosures work with a
keyboard and with JavaScript disabled.

With JavaScript enabled, filter by detection outcome and, in full reports, page.
Caught filters include cross-catches; source-missed filters include only that
source's eligible findings. Selecting a page shows its outcomes beside the
combined results without changing detection rates. **Clear filters** restores
all rows. **Expand all dropdowns** and **Collapse all dropdowns** affect visible
rows and page panels. There is no built-in text search.

Reports embed styling, controls, original human evidence, and selected matching
evidence for offline use. A copied HTML file needs no neighboring files or
internet. Keep the run directory for snapshots, prompts, raw responses, and
unmatched tool findings; these are not all embedded in the report. Unreadable
response counts remain in each child's `run.json`, rather than appearing as a
combined HTML summary.

### Printing and regeneration

**Print report** prints the header, cost, and detection results through the last
bar chart. The findings table and detailed evidence are omitted. The browser's
Print command uses the same summary layout, including without JavaScript.
Printing works offline and preserves filters and opened disclosures without
changing scores or reviews. Browser PDF output is not verified as an accessible
PDF.

Regenerating from saved reviewed evidence makes no model calls. An individual
report is removed before its review is validated; the combined report is also
removed before full evidence validation. Invalid revised reviews therefore
cannot leave stale final results for that report. Preserve a separate copy
first if needed. Full validation failures leave existing child reports available.
Each new HTML file is published after rendering succeeds. Successful
regeneration removes superseded generated Markdown for those reports, leaving
unrelated historical runs alone.

### Page run files

Single-page runs live in `.model-evaluation/runs/<run-id>/`. Full evaluation
children use the same layout under
`.model-evaluation/full-runs/<run-id>/pages/<child-run-id>/`.

| Path relative to the page run | Contents |
| --- | --- |
| `README.md` | Review instructions and report command. |
| `review.csv` | Original human evidence, approved decisions, and editable LLM review columns. |
| `snapshot.html` | Copied page HTML used for the evaluation. |
| `run.json` | Configuration, identities, prompts, skipped prompts, filters, completion, stopping reason, format failures, usage, and estimated cost. |
| `normalized-llm-findings.json` | LLM findings and their run-specific IDs, saved during execution. |
| `report.html` | Generated offline page report. |
| `artifacts/human-finding-mapping.json` | Frozen approved mapping, with checksum and attribution in the manifest. |
| `artifacts/human-findings.json` | Canonical imported local and Global human findings. |
| `artifacts/normalized-programmatic-findings.json` | Checker findings with run-specific IDs. |
| `artifacts/raw-programmatic-findings.json` | Original checker output. |
| `artifacts/raw-llm-responses.json` | Model replies, request outcomes, raw usage, billable categories, and request cost estimates. |
| `artifacts/pricing.json` | Saved model rates, version, and capture date. |
| `artifacts/prompts/*.json` | Exact `prompt_text` and filtered `payload_slice` for each prepared request. These contain no model replies. |
| `artifacts/payloads/cl01_payload.json` | Extracted semantic structure before filtering. |
| `artifacts/payloads/cl02_payload.json` | Extracted forms, fields, and labels before filtering. |
| `artifacts/payloads/cl03_payload.json` | Extracted images, SVGs, icons, and media before filtering. |

Previews have no LLM response or normalized LLM findings files. Prompt files
show what is prepared for the model; raw response records show which requests
actually ran. Check prompts when relevant evidence seems missing and raw
responses when an answer is absent or malformed. The pipeline's temporary
`artifacts/manifest.json` is removed; evaluation metadata lives in `run.json`.

A full parent also contains `README.md`, `full.json`, `human-findings.json`, and
`artifacts/human-finding-mapping.json`. `full.json` records ordered child
membership and execution totals. Parent human findings retain unique originals
and page assignments. Reporting adds the combined `report.html`.

## Troubleshooting and compatibility

| Symptom | Action |
| --- | --- |
| Approved mapping required | Complete mapping CSV preparation and approval, then pass its JSON path explicitly. Previews also require it. |
| Audit checksum or page assignment mismatch | Use the same human audit file and its matching snapshot mapping. For a changed human audit file, capture and approve new inputs. Check local findings' reproduction URLs. |
| Expected checker evidence resolves to zero or several findings | Inspect the named page, rule, and evidence. Reuse the reviewed snapshots and checker code, or prepare and approve a new mapping for changed evidence. |
| Capture or review directory already exists | Choose a new directory. These commands preserve previous work. |
| Approval output already exists | Choose a new output filename. Approval refuses to overwrite mappings. |
| Live key missing | Set the selected provider's key in the environment or repository-root `.env`. |
| Live execution declined in a script | Use `--live --approve-live` for explicit noninteractive approval. |
| Incomplete execution or exhausted allowance | Read the stopping reason in `run.json` or `full.json`. Address it and start a fresh live invocation, which repeats paid requests. Completed children can still be reported individually. |
| Complete run with missing LLM findings | Check `format_failures`, raw replies, skipped prompts, and prepared payload slices. Unreadable responses yield no findings but do not stop execution. |
| Approved column changed | Restore the saved decision. To change responsibilities, approve a new mapping and create new runs. |
| Unknown or reused finding ID | Copy IDs from the correct page and source file. Use each ID for at most one human finding in that page's review. |
| Report disappears after failed regeneration | Correct the reported validation error and rerun reporting. The prior report is removed to prevent stale final results. |

Saved runs must have the current directory layout, mapping artifact, and manifest
fields. There is no automatic migration or compatibility fallback. Moving files
into `artifacts/` alone cannot update every older run format. Prepare new runs
when old evidence lacks required fields; retain earlier files as historical
artifacts. The former `correct-all` command is removed.

Earlier private experiments may contain `preflight.json`,
`format-diagnostics.json`, or `review-validation.json`. Standard evaluator
commands do not create those files or perform those extra experimental checks.
