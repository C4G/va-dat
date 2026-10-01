# va-dat — Vision Aid Digital Accessibility Testing

LLM-powered tools that analyze websites for WCAG accessibility issues and generate structured remediation reports. A Computing for Good course project at Georgia Tech (OMSCS) partnered with the Vision Aid Digital Accessibility Testing Team.

There are two ways to use it: a **web app** (paste a URL or HTML, get findings and a CSV) and a **CLI pipeline** for batch or scripted runs. Both share the same analysis code.

## How It Works

The pipeline takes a raw HTML file and produces targeted accessibility findings through four steps:

```
HTML file (e.g. 1.9 MB)
    │
    │  Step 0 — Programmatic Checks (no API cost)
    │  Rule-based detection of missing alt, empty links, duplicate IDs, etc.
    │
    │  Step 1 — Extract
    │  Three extractors parse the HTML into structured JSON payloads,
    │  discarding layout noise (CSS, scripts, divs) and keeping only
    │  semantically relevant content. ~92% token reduction.
    │
    ├── semantic_checklist_01.py  → headings, links, landmarks, tables, iframes
    ├── forms_checklist_02.py    → form fields, labels, groups, instructions
    └── nontext_checklist_03.py  → images, SVGs, icon fonts, media
                                    Combined: ~39k tokens (from ~487k)
    │
    │  Step 2 — Slice & Call
    │  Each payload is sliced into targeted pieces. Each slice is paired
    │  with a focused prompt template and sent to the LLM individually.
    │  Up to 18 element-specific calls + 3 optional summary calls.
    │
    │  Step 3 — Save
    │  Raw JSON results are saved per-prompt for downstream processing.
    │
    │  Step 4 — Report
    │  The report generator reads all saved results, normalizes findings
    │  from both programmatic and LLM sources, and writes a unified CSV.
```

## Repository Structure

```
├── index.html                                   # Web UI + team site (all markup/CSS/JS inline)
├── styles.css
│
├── entry_points/                                # Entry points
│   ├── api_server.py                            # Serves the site and the /api/* audit endpoints
│   ├── run_pipeline.py                          # Runs the full pipeline from the CLI
│   └── generate_report.py                       # Combines findings into unified CSV report
│
├── processing_scripts/
│   ├── llm/                                     # Modular prompt system + templates
│   │   ├── registry.py                          #   Maps each evaluation task to its template + slicer
│   │   ├── templates.py                         #   Parses .txt prompt files, fills {payload} placeholders
│   │   ├── slicers.py                           #   Extracts targeted JSON slices from extractor payloads
│   │   ├── semantic_checklist_01.txt            #   7 prompts for semantic structure
│   │   ├── forms_checklist_02.txt               #   6 prompts for form accessibility
│   │   └── nontext_checklist_03.txt             #   8 prompts for non-text content
│   │
│   ├── llm_client/                              # Provider-independent audit requests
│   │   ├── audit.py                             #   API requests and response metadata
│   │   └── client.py                            #   Model-provider capability helpers
│   │
│   ├── llm_preprocessing/                       # HTML → structured JSON extractors
│   │   ├── semantic_checklist_01.py             #   Headings, links, landmarks, tables, iframes
│   │   ├── forms_checklist_02.py                #   Form fields, label associations, groups
│   │   └── nontext_checklist_03.py              #   Images, SVGs, icon fonts, media
│   │
│   ├── programmatic/                            # Rule-based checks (no LLM needed)
│   │   ├── semantic_checklist_01.py             #   Semantic structure checks
│   │   ├── forms_checklist_02.py                #   Form accessibility checks
│   │   └── nontext_checklist_03.py              #   Non-text content checks
│   │
│   └── docs/pipeline.md                         # Pipeline architecture documentation
│
├── vision_aid/ingestion/
│   ├── file_crawler.py                         # fetch_page / fetch_pages_nested (used by the server)
│   └── pull_html.py                            # Standalone HTML download helper
│
├── Dockerfile                                  # Multi-stage uv build → runtime image
├── docker-compose.yml                          # Local run (Coolify deploys the image directly)
├── DEPLOY.md                                   # Coolify deployment notes
│
├── .github/workflows/
│   ├── ci.yml                                  # On PR to main: deps, imports, pipeline, image smoke test
│   └── publish.yml                             # On push to main: build → GHCR → trigger Coolify
│
├── test_files/                                 # HTML files to analyze
│   ├── home.html                               #   visionaid.org homepage (~1.9 MB)
│   └── dat_visionaid_home.html                 #   Smaller trimmed variant (~143 KB)
│
├── semantic_checklist/                         # Source of truth: Deque WCAG checklist PDFs
│   ├── 01-semantic-checklist.pdf
│   ├── 02-forms-checklist.pdf
│   └── 03-nontext-checklist.pdf
│
├── pipeline_walkthrough.ipynb                  # Colab-compatible step-by-step pipeline notebook
│
├── docs/                                       # Architecture documentation
│   └── modular-prompts-plan.md                 #   Full architectural plan
│
├── reports/                                    # Historical raw JSON audit output
│
├── test_results/
│   ├── chatgpt/                                # Legacy ChatGPT testing results
│   └── claude/                                 # Pipeline-generated CSV reports
│       └── report_YYYY-MM-DD.csv
│
└── output/                                     # Generated at runtime (not committed)
    ├── manifest.json
    ├── programmatic_findings.json
    ├── payloads/
    └── prompts/
```

## Architecture Deep-Dive

### Extractors (existing code)

Each extractor has an `extract(file_path)` function that parses HTML with BeautifulSoup and returns a structured dict:

| Extractor | Focus | Output tokens (visionaid.org) |
|-----------|-------|-------------------------------|
| `semantic_checklist_01.py` | Page title, headings, links, landmarks, tables, iframes | ~17,600 |
| `forms_checklist_02.py` | Form fields with label source, instructions, required flags | ~2,500 |
| `nontext_checklist_03.py` | Images (4 categories), SVGs, icon fonts, video/audio | ~19,200 |

These files live in `processing_scripts/llm_preprocessing/` and were authored by ahildebrandt3 and Andrew Yin. They should not need modification unless a new checklist (CL04+) is added.

### Prompt Registry Pattern (new)

The core of the modular system is in `processing_scripts/llm/`:

- **`registry.py`** — Defines 21 `PromptSpec` dataclass entries, each linking a prompt name to its template file, slicer function, WCAG criteria, and output type. This is the single source of truth for what the pipeline evaluates.

- **`slicers.py`** — Contains one function per prompt (e.g., `slice_headings()`, `slice_flagged_links()`) that extracts exactly the data that prompt needs from the full extractor payload. This is what achieves the token reduction.

- **`templates.py`** — Parses the `.txt` prompt template files (which contain multiple numbered prompts separated by dashed headers) and fills in the `{payload}` placeholder with the sliced JSON at runtime.

### Pipeline Orchestrator (new)

`entry_points/run_pipeline.py` ties everything together:

1. Runs the three extractors to get structured payloads
2. Runs programmatic checks on the CL01 payload
3. Iterates over the prompt registry, slicing payloads and assembling prompts
4. Calls the Anthropic API for each non-empty prompt (or saves dry-run output)
5. Writes a manifest with token counts, timing, and cost data

### Report Generator (new)

`entry_points/generate_report.py` reads the pipeline output and produces a flat CSV:

1. Loads `manifest.json` for run metadata (date, model)
2. Normalizes `programmatic_findings.json` (59 rule-based issues) into report rows
3. For each `output/prompts/*.json`, applies a prompt-specific normalizer that understands the response schema and extracts issues
4. Assigns sequential IDs and writes to `test_results/claude/report_YYYY-MM-DD.csv`

The normalizer registry mirrors the prompt registry — one normalizer function per prompt type that knows how to detect issues in that prompt's response shape.

## How to Extend

### Adding a new prompt type

1. **Slicer** — Add a function in `processing_scripts/llm/slicers.py` that extracts the relevant data from the extractor payload
2. **Template** — Add a new numbered prompt section to the appropriate `.txt` file in `processing_scripts/llm/`
3. **PromptSpec** — Add an entry in `processing_scripts/llm/registry.py` linking the slicer, template, and WCAG criteria
4. **Normalizer** — Add a normalizer function in `entry_points/generate_report.py` and register it in the `NORMALIZERS` dict

### Adding a new extractor/checklist (CL04+)

1. Create a new extractor in `processing_scripts/llm_preprocessing/` with an `extract(file_path)` function
2. Create corresponding prompt templates in `processing_scripts/llm/`
3. Add slicer functions in `processing_scripts/llm/slicers.py`
4. Register new `PromptSpec` entries in `processing_scripts/llm/registry.py`
5. Add normalizers in `entry_points/generate_report.py`
6. Update `entry_points/run_pipeline.py` to call the new extractor

## Setup

This project uses [uv](https://docs.astral.sh/uv/). It installs the right
Python version itself, so there is no separate Python install or `venv` step.

```bash
# Install uv once (see the uv docs for Windows/other options)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create the environment and install exactly the locked dependencies
uv sync
```

Then either prefix commands with `uv run`, or activate the environment:

```bash
uv run python entry_points/run_pipeline.py --help
# or
source .venv/bin/activate        # Linux/macOS
# or: .venv\Scripts\activate      # Windows
```

`uv.lock` pins every dependency, including transitive ones, so everyone gets
an identical environment. To change a dependency, edit `pyproject.toml` and run
`uv lock`, then regenerate the pip fallback below.

<details>
<summary>Using pip instead (graders, Colab, or no uv available)</summary>

`requirements.txt` is a generated export of `uv.lock` — **do not edit it by
hand**; regenerate it with the command in its header. Python 3.11+ required.

```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
# or: venv\Scripts\activate     # Windows

pip install -r requirements.txt
pip install -e . --no-deps
```

If `python -m venv` fails with an `ensurepip` error, your Python is missing its
venv module (`sudo apt install python3-venv` on Debian/Ubuntu). uv avoids this
problem entirely.

</details>

Create a `.env` file with your provider API key(s) (only needed for live runs, not dry-run):

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
```

`.env` is gitignored. Never commit a key.

> **A run with no resolvable key silently becomes a dry run** — programmatic
> checks only, no LLM findings, no CSV, and still a `200 OK` from the web app.
> The only signal is `summary.dry_run` in the response.

## Private Model Evaluation

### Choose an evaluation model

Each Evaluation run uses one fixed model through Anthropic's direct API.
Choose it with `--model`; omitting the flag selects Haiku 4.5. The evaluator
accepts only these exact IDs:

| Model | `--model` value | Thinking | Effort |
| --- | --- | --- | --- |
| Haiku 4.5, default | `claude-haiku-4-5-20251001` | 16,000-token budget | Omitted |
| Opus 5.5 | `claude-opus-5-5` | Adaptive | Medium |
| Sonnet 5.5 | `claude-sonnet-5-5` | Adaptive | Medium |

For example, add `--model claude-opus-5-5` to the run command below to evaluate
Opus. Friendly names and aliases are rejected. Thinking settings are fixed
presets, and all three models use a 24,192-token output cap that includes
thinking and final text. Adaptive thinking does not reserve a fixed number of
tokens for final text. Temperature is omitted and summaries are disabled.
The selected model and settings are saved with each run.

### Get a final report with the supplied Human audit

From the repository root, use the supplied `Pristine Accessibility Defect Report.xlsx`
(16 Home and Global defects). These steps work after deleting `.model-evaluation/`.

1. **Save a Benchmark snapshot.** The evaluator does not download the page.
   Create the ignored directory and save the homepage HTML there:

   ```bash
   mkdir -p .model-evaluation
   curl --fail --location --silent --show-error \
     --output .model-evaluation/pristine-home.html https://pristineai.com/
   test -s .model-evaluation/pristine-home.html
   ```

   Check that the file contains the intended homepage. `curl` saves server HTML;
   if the browser builds the content, save rendered HTML there instead. Use
   `https://pristineai.com/` as its source URL.

2. **Set up live access and choose a limit.** Set `ANTHROPIC_API_KEY` in your
   environment or the ignored repository-root `.env`. Set `MAX_COST_USD` to a
   positive amount you approve. The limit is checked before each paid request;
   a request in progress can put the final cost above it.

3. **Start a live Evaluation run.** Run this command in a terminal:

   ```bash
   MAX_COST_USD=1.00  # Example; replace with the amount you approve.
   uv run visionaid-evaluate run \
     --human-audit "Pristine Accessibility Defect Report.xlsx" \
     --html .model-evaluation/pristine-home.html \
     --source-url https://pristineai.com/ \
     --max-cost-usd "$MAX_COST_USD" \
     --live
   ```

   The CLI shows the selected model's thinking settings, effort, output token cap,
   prompt count, token rates, pricing version, snapshot checksum, and limit.
   The cost guardrail is checked between requests; a request underway can exceed it.
   Type `yes` to approve
   paid requests; `--approve-live` skips the prompt. It copies the snapshot,
   imports Human findings, runs checks, and saves responses and usage.

4. **Check completion and review the findings.** Use the printed run directory:

   ```bash
   RUN_DIR='.model-evaluation/runs/<RUN_ID>'
   ```

   Confirm `"complete": true` in `$RUN_DIR/run.json`; otherwise, address the
   failure or cost limit and start a new live run. Failed requests are not
   retried. Use `$RUN_DIR/normalized-llm-findings.json` and
   `$RUN_DIR/normalized-programmatic-findings.json` for finding IDs and evidence.
   `$RUN_DIR/artifacts/raw-llm-responses.json` has model responses;
   `$RUN_DIR/artifacts/raw-programmatic-findings.json` has the original checker output.

5. **Make the human decisions in one CSV.** Open `$RUN_DIR/review.csv` in
   Excel or a CSV-aware text editor. Review every Human finding and fill in
   the decision columns using the guide below. Save the file as CSV.

6. **Generate the final report.** Run `report` after completing the review,
   naming whoever made the decisions:

   ```bash
   uv run visionaid-evaluate report --run-dir "$RUN_DIR" --reviewer "Your name or agent description"
   ```

   Open `$RUN_DIR/report.md`. It explains how to read the homepage evaluation,
   then shows the model, run ID, reviewer, three detection rates, and estimated
   cost with token counts and the pricing date. A table follows the Human audit's
   original order and marks catches by each part, including cross-catches. The
   remaining sections show what each part caught and why each match counts,
   every missed finding with any recorded explanations, and findings not
   testable from the page file with their reasons. IDs, locations, and raw JSON
   stay in the run artifacts. Not-testable findings are left out of the LLM and
   Programmatic rates but remain in the Overall denominator. Reporting rejects
   incomplete runs, missing classifications, and invalid or reused finding IDs.

### How the evaluator reads LLM responses

The evaluator measures the tool as it is, so it reads each LLM response the
way the tool's CSV report does, using the tool's own code rather than a copy.

**Parsing.** Each response is parsed with the tool's JSON parser, including its
code-fence and repair steps. A response the tool cannot parse, or whose shape
the check's rule cannot read (for example one object where a list is expected),
is an Unreadable response: it gives no LLM findings, `run.json` lists the check
under `format_failures`, and the run continues with the next check.

**What counts as a finding.** For the 12 checks the tool's CSV report covers,
the tool's own per-check rule decides, and each row it would write becomes one
LLM finding:

- Page title and landmarks: one finding per entry in `issues`. Yes/no answers
  such as `is_descriptive` are ignored.
- Headings: one finding per entry in `issues`, plus one per entry in
  `vague_headings`.
- Link clarity, iframe titles, label quality, and decorative verification: one
  finding per item whose verdict (`is_clear`, `is_descriptive`, or
  `likely_decorative`) is `false`. A missing verdict counts as a pass.
- Required field indicators, informative alt quality, actionable image alt,
  SVGs, and icon fonts: one finding per item with a non-empty `issues` list,
  with its issues joined. An item the model judged acceptable gives no
  finding, even if a yes/no answer such as `has_accessible_name` is `false`.

Each finding's problem, element, and location are the text the tool would
write in its row. `raw_source` keeps the full item, or for page title,
headings, and landmarks the whole response plus the specific issue.

**What is skipped.** The tool's false-positive filter and LLM deduplication are
not applied. The filter guesses from the page HTML and can remove a finding
other than the one it matched; deduplication costs extra LLM calls and is not
repeatable. Evaluation counts therefore measure what the model reported and
will not match the rows in the tool's downloadable CSV report.

**Checks shown on screen only.** Six checks have no rule in the tool's CSV
report; their results appear only in the web app's on-screen panel:
`table_semantics`, `placeholder_as_label`, `group_labels`, `form_instructions`,
`complex_descriptions`, and `media_captions`. The evaluator still reads them,
giving at most one finding per item, and only when the item's `issues` list is
non-empty (for tables, `issues` or `header_clarity_issues`). Every
`placeholder_as_label` item is a finding, because that check only receives
placeholder-only fields. Yes/no answers never create a finding on their own.
A table response may be one object or a list. These findings have
`"screen_only": true`, and `report.md` labels them "shown on screen only, not
in the tool's CSV report".

### Evaluation run files

The run root holds the review evidence and scored results. Supporting files
are together under `$RUN_DIR/artifacts/`. Without `--live`, the command prepares
the prompts but makes no model requests; neither LLM output file exists yet.
Successful reporting adds `report.md` at the root.

New runs and reporting use only this layout. Existing run directories remain
untouched and require manual reorganization before the updated `report` command
can read them. Move their supporting files into `artifacts/`, including the
`prompts/` and `payloads/` directories, preserving filenames. There is no
compatibility fallback or automatic migration.

| File | Role |
| --- | --- |
| `review.csv` | Original Human audit evidence, source sheet and row, stable IDs, and the decision columns the reviewer edits. |
| `snapshot.html` | The full Benchmark snapshot used to judge testability and coverage. |
| `normalized-llm-findings.json` | LLM findings with `finding_id` values for `review.csv`, read as described above. An Unreadable response can appear in `artifacts/raw-llm-responses.json` without producing a finding here. |
| `normalized-programmatic-findings.json` | Checker results converted to findings with `finding_id` values for `review.csv`. |
| `run.json` | Configuration, snapshot checksum, prompt list, completion status, format failures, token usage, and estimated cost. `complete: true` does not imply that every response parsed successfully; check `format_failures`. |
| `report.md` | Scored results generated after successful reporting. |
| `artifacts/human-findings.json` | Canonical imported Home and Global Human findings used to validate and score the review. |
| `artifacts/pricing.json` | The versioned public model rates and capture date used to estimate this run's cost from reported usage. Older runs retain their original price schedule. |
| `artifacts/raw-llm-responses.json` | Live model replies, request outcomes, and reported token usage, including responses that could not be parsed into findings. |
| `artifacts/raw-programmatic-findings.json` | Original output from the Programmatic checks. |
| `artifacts/prompts/*.json` | The exact `prompt_text` and filtered `payload_slice` prepared for each model request. These files do not hold model replies in an Evaluation run. |
| `artifacts/payloads/cl01_payload.json` | Extracted headings, links, landmarks, tables, and other semantic page structure. |
| `artifacts/payloads/cl02_payload.json` | Extracted forms, fields, and labels. |
| `artifacts/payloads/cl03_payload.json` | Extracted images, SVGs, icons, and media. |

The payload files show extracted page data before filtering. The prompt files
show what the model actually received after filtering and slicing. To review a
Human finding, compare its original evidence in `review.csv` with the two
normalized findings files and inspect `snapshot.html` for the full Benchmark
evidence. Check
`artifacts/raw-llm-responses.json` when an LLM finding is missing or malformed, and
check the file under `artifacts/prompts/` to see whether the model received the
relevant evidence.
Record decisions in `review.csv`; the `report` command reads that CSV and the
run evidence to write `report.md`. The pipeline briefly writes
`artifacts/manifest.json`, but the Evaluation command removes it and keeps the
relevant metadata in
`run.json`.

Earlier private experiments may also contain `preflight.json` with advance
token counts and a spending plan, `format-diagnostics.json` with an offline
inspection of malformed replies, and `review-validation.json` with checks on
the completed review. The standard `visionaid-evaluate run` command does not
create those files or perform those extra checks.

### Fill in `review.csv`

The CSV has one row for each of the 16 Home or Global Human findings. Keep
the header, all rows, and their `human_finding_id` values. The columns from
`human_finding_id` through `comment` identify the Human finding and preserve its
original evidence. Use them to understand the defect, but do not edit them.
In particular, `source_sheet` and `source_row` point back to the Human audit,
`page_scope` says Home or Global, and `source_element` copies the Human audit's
`element name`. It is not an inferred location on the page.

For **every row**, fill in `classification`:

| `classification` value | Use it when |
| --- | --- |
| `llm_eligible` | The Benchmark snapshot contains enough evidence to judge the defect, and the issue calls for the LLM's judgment. |
| `programmatic` | A Programmatic check can establish the defect from the available evidence. Classification alone does not mean the checker found it. |
| `unavailable_evidence` | The snapshot lacks evidence needed to verify the defect, such as behavior that requires interaction or a browser or assistive technology observation. |
| `ambiguous` | The Human finding is too unclear to decide fairly whether a finding covers it. |

Base the classification on the Human finding and available evidence, not on
whether this run happened to produce a matching finding. In
`classification_reason`, write a short explanation of that choice, including
what evidence is missing or unclear when applicable. This explanation is
optional, but `classification` cannot be blank when you generate the report.

Then complete the remaining decision columns for that row:

| Column | What to enter |
| --- | --- |
| `llm_finding_id` | Copy `finding_id` values from `$RUN_DIR/normalized-llm-findings.json` only when the selected LLM findings **jointly cover the whole Human finding**. Separate multiple IDs with semicolons (`;`). Otherwise leave blank. |
| `programmatic_finding_id` | Copy `finding_id` values from `$RUN_DIR/normalized-programmatic-findings.json` only when the selected Programmatic findings **jointly cover the whole Human finding**. Use semicolons for multiple IDs. Otherwise leave blank. |
| `match_reason` | If either finding-ID cell has an ID, briefly explain how those findings cover the full defect, including the relevant element or behavior. If both ID cells are blank, this can be blank. |
| `review_notes` | Optional context, such as a more precise location or a finding that covers only part of the defect. Notes do not award coverage. |

You may use findings from both files for one row. Each finding ID must exist in
the named file and can be assigned to only one Human finding. Leave both ID
cells blank when no findings fully cover the row; that records a miss, even if
you describe partial evidence in `review_notes`. For `unavailable_evidence` and
`ambiguous` rows, leave both ID cells blank. The report command checks these
rules and requires a `match_reason` whenever you enter an ID.

The run directory and Human audit are excluded from version control.
This one-homepage result does not establish broad model equivalence.

### Start a run without `--live`

Save the Benchmark snapshot in step 1, then run this from the repository root:

```bash
uv run visionaid-evaluate run --html .model-evaluation/pristine-home.html \
  --source-url https://pristineai.com/ --max-cost-usd 1.00
```

This needs no API key or approval. It creates an incomplete run with
`artifacts/raw-programmatic-findings.json`, `normalized-programmatic-findings.json`,
LLM prompts, and `review.csv`. Use the normalized file's `finding_id` values
for programmatic matches. It makes no model requests and cannot produce a
final report. `--max-cost-usd` must be positive but is not spent without
`--live`. Start a new live run at step 3 to finish the evaluation.

## Running the Web App

```bash
uv run python entry_points/api_server.py      # http://localhost:8000
```

Serves the UI and the audit API from one process. Users can paste their own API
key into the form instead of configuring one server-side; per-request keys take
priority over the environment.

The audit endpoints stream **NDJSON** — progress events, one JSON object per
line, then a final `{"type":"result"}` object. Parsing that body with a single
`res.json()` fails; the front end branches on content type.

To run it in a container:

```bash
docker compose up --build                     # http://localhost:8000
HOST_PORT=8789 docker compose up --build      # if 8000 is taken
```

## Deployment

Merges to `main` build the image, push it to `ghcr.io/c4g/va-dat`, and trigger a
Coolify deploy to <https://va-dat.c4g.dev>. See [DEPLOY.md](DEPLOY.md) — in
particular the proxy settings, since response buffering breaks the progress
stream and short read timeouts cut off long audits.

Note that Coolify runs the **image**; the hardening in `docker-compose.yml`
(`read_only`, `tmpfs`) applies to local runs only.

## Continuous Integration

`.github/workflows/ci.yml` runs on every PR to `main` and needs no API key —
everything it does is free:

- `uv.lock` is in sync with `pyproject.toml`, and `requirements.txt` matches the lock
- entry points import
- the tracked synthetic pytest suite (`uv run pytest -q`), with no private data or provider calls
- a full pipeline dry run, asserting prompts generated, findings found, and zero tokens consumed
- `index.html`'s inline JavaScript parses
- the Docker image builds, becomes healthy, serves the site, and returns a valid NDJSON audit

Default pytest discovery is limited to `tests/`, where `tests/test_evaluation.py`
covers the evaluator end to end through its CLI with a fake provider. Optional
detailed evaluator cases live in the ignored `.local-tests/evaluation/` folder;
run them with `uv run pytest -q .local-tests/evaluation`. CI never needs them.

## Running the Pipeline

### Dry run (no API calls, no cost)

Generates all prompts and saves them as JSON files so you can inspect them before spending money:

```bash
uv run python entry_points/run_pipeline.py --html test_files/dat_visionaid_home.html --dry-run
```

### Live run

Sends prompts to the LLM and saves responses:

```bash
uv run python entry_points/run_pipeline.py --html test_files/home.html
```

### Generate report

After a live run, combine all findings into a single CSV:

```bash
uv run python entry_points/generate_report.py
uv run python entry_points/generate_report.py --output-dir ./output --report-dir ./test_results/claude/
```

### Pipeline options

| Flag | Default | Description |
|------|---------|-------------|
| `--html` | (required) | Path to the HTML file to analyze |
| `--output-dir` | `./output` | Directory for results |
| `--model` | `claude-sonnet-5` | Anthropic model to use |
| `--dry-run` | off | Generate prompts without calling the API |
| `--include-summaries` | off | Include the 3 cross-cutting summary prompts |
| `--show-cost` | off | Print estimated dollar cost of the run based on model pricing |
| `--env-file` | `.env` | Path to environment file |

### Report generator options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `./output` | Directory containing pipeline output |
| `--report-dir` | `./test_results/claude/` | Directory to write the CSV report |

## Output Structure

### Pipeline output (`output/`)

```
output/
├── manifest.json                 # Run metadata, token counts, prompt status
├── programmatic_findings.json    # Rule-based checker results (free)
├── payloads/                     # Raw extractor output (for inspection)
│   ├── cl01_payload.json
│   ├── cl02_payload.json
│   └── cl03_payload.json
└── prompts/                      # One file per prompt
    ├── page_title.json           # Contains prompt text, payload slice, and API response
    ├── heading_structure.json
    ├── link_clarity.json
    └── ...
```

### Report output (`test_results/claude/`)

The report CSV has 13 columns matching the Vision Aid team's standard format:

| Column | Description |
|--------|-------------|
| `ID` | Sequential row number |
| `element_name` | HTML element (e.g. `<img class="...">`, `<a> "link text"`) |
| `browser_combination` | Always `N/A` (static HTML analysis) |
| `page_title` | Page title from the analyzed HTML |
| `issue_title` | Short issue description |
| `steps_to_reproduce` | Element snippet or inspection steps |
| `actual_result` | What was found |
| `expected_result` | What WCAG requires |
| `recommendation` | Suggested fix |
| `wcag_sc` | WCAG success criterion (e.g. `1.1.1`) |
| `category` | Issue category (e.g. `Programmatic / Non-text Content`) |
| `log_date` | Date of the pipeline run |
| `reported_by` | `Programmatic` or the LLM model string |

## Cost Estimate

For visionaid.org homepage (using Claude Sonnet):

| Approach | Input tokens | Cost |
|----------|-------------|------|
| Monolithic (entire HTML) | ~487,000 | ~$1.52 |
| Element-specific pipeline | ~18,000 | ~$0.32 |

The pipeline skips prompts with empty payloads (e.g., no forms on the page = no form prompts), so actual cost varies by page content.

## Attribution

| Contributor | What they own | Key files |
|---|---|---|
| ahildebrandt3 | Extractors, programmatic checkers (CL01–CL03), CL01 prompts | `processing_scripts/llm_preprocessing/`, `processing_scripts/programmatic/` |
| Andrew Yin | CL02 + CL03 extractors, CL02 + CL03 prompts, LLM client, pipeline docs | `processing_scripts/llm_preprocessing/`, `processing_scripts/llm_client/`, `processing_scripts/llm/*.txt` |
| nfulton99 | HTML ingestion, packaging | `vision_aid/ingestion/pull_html.py`, `pyproject.toml` |
| ColeANiblett | Pipeline orchestration, prompt system, report generator | `processing_scripts/llm/{registry,slicers,templates}.py`, `entry_points/`, `docs/` |
