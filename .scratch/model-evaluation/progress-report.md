# Model evaluation suite progress report

Updated: September 20, 2026

## Term used in this report

**Reference workbook** means the authorized Excel file containing the findings
from the prior human accessibility audit. Its individual tabs are worksheets,
and their rows supply the source evidence for the benchmark's reference
defects. The generated Eligibility and Matches Excel files are review
workbooks, not the reference workbook.

## Why the evaluation suite is separate

- I built a separate evaluation suite because the production CSV is a cleaned
  customer deliverable rather than a complete record of model performance.

- The CSV has no normalizers for six registered non-summary prompt categories:
  table semantics, placeholder-only labels, form-group labels, form
  instructions, complex image descriptions, and media captions.

- The CSV also skips failed or malformed responses, combines model and
  programmatic findings, applies false-positive filters, and can use another
  LLM for deduplication.

- Scoring that output would measure the report-processing pipeline along with
  the audit model.

- The evaluation suite instead normalizes every raw prompt response, preserves
  failures and provenance, separates programmatic coverage, and scores only
  approved matches against eligible workbook rows.

- I reused the production pipeline for prompt generation and provider requests
  so the evaluation still tests the same audit behavior used by the
  application.

## CLI command order

Run the following commands in order. Complete the Eligibility workbook before
command 2 and each generated Matches workbook before its following
`--import-matches` command. `RUN_DIR` is the evaluation-run path printed by
command 3.

```bash
# 1. Build the benchmark from the human-audit reference workbook.
#    This imports the reference defects and freezes the homepage HTML.
#    --homepage-url identifies which workbook page rows belong to the
#    benchmark. It selects the Home and applicable Global reference defects
#    but does not fetch the webpage.
#    --snapshot-url identifies where to download the HTML that models will
#    inspect. It records the captured content and its provenance.
#    Both values are the same for this proof of concept because the workbook
#    homepage and the captured benchmark page are both pristineai.com.
uv run visionaid-evaluate prepare \
  --workbook-sha256 "$WORKBOOK_SHA256" \
  --homepage-url https://pristineai.com/ \
  --snapshot-url https://pristineai.com/ \
  --temporal-assumption "$TEMPORAL_ASSUMPTION"

# Manually complete .model-evaluation/reviews/eligibility.xlsx.
# Classify who is responsible for each reference defect before scoring begins.

# 2. Validate the completed eligibility decisions and create the approved
#    reference set used by every evaluation run.
uv run visionaid-evaluate review \
  --eligibility-workbook .model-evaluation/reviews/eligibility.xlsx

# 3. Plan the model evaluation without making provider requests.
#    This freezes the prompts, model settings, evidence identities, and cost
#    guardrail. Save the evaluation-run path printed by this command.
uv run visionaid-evaluate audit --max-audit-cost-usd 1.00

RUN_DIR=".model-evaluation/runs/REPLACE_WITH_PRINTED_RUN_ID"

# 4. Generate a workbook that compares deterministic checker findings with
#    the human-audit reference defects. This review measures checker coverage,
#    not model performance.
uv run visionaid-evaluate review \
  --run-dir "$RUN_DIR" \
  --kind programmatic

# Manually complete the generated programmatic Matches workbook.

# 5. Validate and save the programmatic match decisions.
uv run visionaid-evaluate review \
  --run-dir "$RUN_DIR" \
  --kind programmatic \
  --import-matches

# 6. Display the saved billable intent, request approval, and run the model.
#    The command preserves raw responses, usage, failures, and canonical audit
#    findings. It cannot overwrite evidence from an earlier live attempt.
uv run visionaid-evaluate audit \
  --live \
  --run-dir "$RUN_DIR"

# 7. Generate a workbook that compares the model's findings with the eligible
#    human-audit reference defects. These matches determine model recall.
uv run visionaid-evaluate review \
  --run-dir "$RUN_DIR" \
  --kind audit

# Manually complete the generated audit Matches workbook.

# 8. Validate and save the audit match decisions used for model scoring.
uv run visionaid-evaluate review \
  --run-dir "$RUN_DIR" \
  --kind audit \
  --import-matches

# 9. Verify that the live evidence and both reviews belong to this run, then
#    calculate the score and write JSON, CSV, and Markdown reports.
uv run visionaid-evaluate report --run-dir "$RUN_DIR"
```

## CLI workflow in detail

The four commands describe stages of one evaluation rather than four unrelated
utilities. Each stage produces evidence that the next stage verifies and uses.

### `prepare`

- I added `prepare` to establish the benchmark before any model is evaluated.
  It requires an authorized local workbook rather than downloading or
  substituting private source data.

- It creates the ignored `.model-evaluation` workspace so private inputs and
  derived evidence stay outside version control.

- When supplied with the approved workbook checksum and homepage URL, it
  verifies the workbook, imports every applicable Home and Global row, and
  preserves the original sheet, row, wording, location, WCAG evidence, and
  recommendation.

- It writes `references/imported.json` as the unapproved reference inventory
  and `reviews/eligibility.xlsx` as the human-readable classification
  workbook. Importing a row does not make it scorable until its eligibility
  decision is reviewed and accepted.

- When supplied with a snapshot URL, it captures the exact HTML that the audit
  pipeline will consume and records the source URL, capture time, HTTP
  metadata, temporal assumption, and SHA-256.

- It refuses to overwrite or silently recapture an existing snapshot because
  changing page content between model runs would invalidate the comparison.

- `prepare` makes no provider request and incurs no model cost.

### `audit`

- I made `audit` dry by default because possessing an API key should never be
  enough to spend money.

- In planning mode, it requires an accepted reference set, the frozen
  snapshot, and a positive maximum audit cost. It then runs the production
  pipeline without provider calls to determine the exact prompts and payloads
  that would be sent.

- Planning creates a unique evaluation-run directory and freezes the approved
  reference set, prompt text, payloads, prompt hashes, parser identity, model
  configuration, pricing identity, retry policy, repository state, estimated
  input usage, and cost guardrail.

- It prints the model, endpoint, reasoning effort, benchmark identity, prompt
  names, request count, retry policy, estimated input usage, maximum cost, and
  output destination so billable intent is visible before execution.

- Live mode is a separate invocation that requires `--live`, the planned run
  directory, an API key, and interactive or explicit automatic approval. It
  revalidates the saved evidence before creating the provider client.

- Live execution sends prompts sequentially, records every attempt, applies
  bounded retries only to transient failures, tracks billed usage against the
  saved cost limit, and stops before another request could exceed that limit.

- It preserves raw responses and provider metadata, then normalizes successful
  responses into canonical audit findings. Authentication errors, malformed
  output, exhausted retries, and incomplete runs remain recorded instead of
  disappearing from the result.

- A live destination is write-once. Repeating an experiment requires a newly
  planned run so evidence from separate approvals cannot be mixed.

### `review`

- I added `review` because neither benchmark eligibility nor semantic finding
  matches can be decided safely from string similarity alone.

- The first review occurs after preparation. A reviewer classifies every
  imported reference in `eligibility.xlsx`, records a rationale, decision,
  identity, confidence, and timestamp, then imports the completed workbook as
  `references/approved.json`.

- The second review occurs per evaluation run. The command creates separate
  match workbooks for `audit` findings and `programmatic` findings so model
  performance cannot be confused with deterministic checker coverage.

- Each match workbook presents reference evidence and finding evidence side by
  side. The reviewer decides whether they describe the same underlying
  accessibility failure at a compatible page, location, element, or element
  group.

- Importing a completed match workbook validates decision states, reviewer
  provenance, evidence compatibility, required sub-defects, and one-to-one
  matching before it writes the decision JSON used for scoring.

- Candidate generation and workbook export never award points. The scorer
  receives only accepted, validated decisions.

### `report`

- I added `report` as the final deterministic stage so presentation cannot
  change the approved score.

- It accepts an evaluation-run directory and discovers the frozen reference
  set, canonical audit findings, canonical programmatic findings, both sets of
  approved match decisions, and the live manifest.

- It verifies that those artifacts belong to the same run and refuses to
  report when live execution, normalization, or either review is missing.

- It calculates workbook-row recall, programmatic coverage, combined workbook
  coverage, estimated audit cost, tokens, latency, unmatched findings, and
  format failures from the verified evidence.

- It writes JSON, CSV, and Markdown from one score object so all three formats
  agree on totals and individual workbook-row dispositions.

- `report` does not call a model or reinterpret review decisions. Running it
  again against unchanged evidence produces the same scoring result.

## Shared model request layer

- I created `AuditRequestClient` so model evaluations exercise the same
  provider request code used in production. This prevents request behavior from
  drifting between the application and the evaluation suite.

- I added `AuditRequestConfig` to control and record the model, reasoning
  effort, temperature, and maximum output tokens for each run.

- I added configurable reasoning effort so OpenAI reasoning models can be
  compared at a known setting.

- I allowed temperature to be omitted because some models reject the parameter
  rather than accepting a value.

- I added model capability checks to prevent unsupported parameters from
  causing failed requests.

- I preserved production's existing temperature and output-token defaults so
  moving production to the shared client would not change current audit
  behavior.

- I added automatic routing for Anthropic, OpenAI, and Gemini so callers do not
  need provider-specific request logic.

- I recorded requested and resolved configuration so each evaluation shows
  what settings the provider received.

- I added detailed token usage for cost calculations, including cached and
  reasoning tokens when providers report them.

- I added provider response details, stop reasons, duration, and structured
  failures so incomplete runs can be diagnosed without repeating billable
  requests.

- I added provider-client injection so tests can inspect exact request
  parameters without making live API calls.

## Private inputs and benchmark evidence

- I created an ignored `.model-evaluation` workspace because the source
  workbook, derived references, captured HTML, reviews, raw responses, and
  reports contain private project data.

- I added workbook checksum validation because a changed or substituted
  workbook would silently change the benchmark.

- I preserved each reference defect's original workbook sheet, row, wording,
  location, WCAG evidence, and recommendation so every score can be traced back
  to its source.

- I added an immutable homepage snapshot with its URL, capture time, HTTP
  metadata, and SHA-256 because every model must receive the same page content.

## Eligibility and scoring

- I added eligibility review because the model should only lose points for
  defects it had enough evidence and responsibility to detect.

- I defined four eligibility classifications: `llm_eligible`, `programmatic`,
  `unavailable_evidence`, and `ambiguous`.

- `llm_eligible` means the audit model receives enough evidence in its prompt
  and is responsible for making the required accessibility judgment. Only
  accepted references in this class enter the model-recall denominator. This
  classification does not assume the model will find the defect.

- `programmatic` means the defect belongs to a deterministic checker rather
  than the audit model. The row counts toward programmatic and combined
  coverage only when an actual programmatic finding is reviewed and matched;
  the classification alone does not award credit.

- `unavailable_evidence` means the current audit pipeline does not receive the
  visual, styling, interaction, cross-page, or other evidence needed to judge
  the workbook claim. It identifies a benchmark limitation, not a model miss
  and not a claim that the source defect is invalid.

- `ambiguous` means the workbook claim, expected scope, or required sub-defects
  cannot yet be interpreted confidently enough for fair assignment or
  scoring. It describes uncertainty in the reference, not uncertainty in a
  model response.

- An accepted `ambiguous` classification is a completed review decision. It is
  different from an eligibility decision that still has a `needs_review`
  state.

- I kept `unavailable_evidence` and `ambiguous` references visible in reports
  but excluded them from both the model and programmatic denominators. This
  prevents missing evidence or unresolved benchmark meaning from helping or
  hurting a model.

- I separated programmatic coverage from model recall because deterministic
  checker results should not improve or reduce a model's ranking.

- I added `EligibilityReviewer` and `MatchReviewer` interfaces so human
  workbook review and a future Astra reviewer can produce the same validated
  decisions without changing scoring or reporting.

- I kept the scorer separate from review so it calculates results only from
  approved decisions and produces the same result from the same inputs.

- I made workbook-row recall over accepted `llm_eligible` defects the primary
  model metric because the mandated workbook is the benchmark source.

- I made estimated audit cost the only ranking tie-breaker. Token usage,
  latency, unmatched findings, malformed output, and programmatic coverage
  remain visible but do not alter rank.

## Run safety and reproducibility

- I added evaluation-run planning because the model configuration, prompt set,
  benchmark, reference set, parser versions, pricing, retry policy, and cost
  limit must be fixed before a billable request begins.

- I added a positive cost guardrail, explicit `--live` flag, API-key
  requirement, and point-of-use approval because credentials alone must never
  trigger spending.

- I made live-run output immutable because retrying into the same directory
  would mix evidence from separate executions.

- I added bounded retries for timeouts, rate limits, and server failures
  because those failures may be temporary.

- I disabled retries for authentication errors, invalid requests, and
  malformed successful responses because repeating them would spend money
  without addressing the cause.

## Normalization, review, and reporting

- I added canonical finding normalization for every registered non-summary
  prompt because provider responses use different JSON shapes that cannot be
  compared directly.

- I preserved malformed responses and parsing failures instead of dropping
  them because output-format reliability is part of the evaluation evidence.

- I added candidate-match workbooks because semantic accessibility findings
  cannot be matched safely by WCAG number or text similarity alone.

- I enforced one-to-one approved matches because allowing one finding to
  satisfy several unrelated workbook rows would inflate recall.

- I added JSON, CSV, and Markdown reports from one score object so every format
  agrees on totals, row dispositions, coverage, cost, and failures.

## Verification

- I added synthetic tests for the complete lifecycle so CI can verify the
  suite without the private workbook, public network access, provider
  credentials, or billable requests.

- The current test suite passes all 76 tests.

- A production pipeline dry run also passed without provider calls. It produced
  14 programmatic findings and generated 10 model prompts from the committed
  HTML fixture.

## Current proof-of-concept status

- The evaluation framework is complete. Eleven implementation tickets are
  resolved, and the remaining ticket covers the real Luna homepage proof of
  concept.

- The private homepage benchmark contains 16 reviewed reference defects: five
  programmatic, three `llm_eligible`, six unavailable to the current pipeline,
  and two ambiguous.

- The three `llm_eligible` defects form the current model-recall denominator.
  Unavailable and ambiguous defects remain reported without affecting the
  score.

- The frozen Pristine homepage snapshot and its provenance are saved in the
  private workspace.

- The benchmark dry run generated 29 programmatic findings and eight active
  model prompts.

- Five programmatic workbook rows have accepted one-to-one matches. The
  remaining programmatic candidates were reviewed and rejected.

- The first Luna run was planned for eight sequential requests with 5,776
  estimated input tokens, medium reasoning, no temperature parameter, and a
  $1.00 cost limit.

- The provider rejected the first live request because the API key was invalid.
  The runner stopped immediately, used zero tokens, incurred no cost, and
  marked the run incomplete and unrankable.

- The failed run remains preserved rather than overwritten.

- A fresh replacement run has been planned, and its five programmatic match
  decisions have been validated.

- The replacement run has not made a live provider request. It is waiting for
  a valid OpenAI Platform API key.

- There is no Luna efficacy score yet. Reporting a score before the replacement
  live run and audit-match review would misrepresent the current state.

## Remaining work

- Replace the rejected credential with a valid OpenAI Platform API key.

- Execute the prepared replacement Luna run.

- Generate and review the audit-finding match workbook.

- Import the approved audit match decisions.

- Generate the final JSON, CSV, and Markdown evaluation reports.
