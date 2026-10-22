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
│   ├── generate_report.py                       # Combines findings into unified CSV report
│   └── model_evaluation.py                      # Compatibility entry point for the evaluator CLI
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
├── vision_aid/
│   ├── evaluation/                             # Evaluation workflows, review, and shared schemas
│   │   ├── cli.py                              # CLI commands and operator interaction
│   │   ├── full.py                             # Full evaluation across all audited pages
│   │   ├── page.py                             # Shared page preparation and review validation
│   │   ├── review.py                           # Review CSV validation and detection counts
│   │   ├── schemas.py                          # Shared Human audit and finding types
│   │   ├── inputs/
│   │   │   └── human_audit.py                  # Import Human findings and audited URLs
│   │   ├── execution/
│   │   │   ├── llm_audit.py                    # LLM requests, saved responses, and cost guardrails
│   │   │   ├── normalization.py                # Convert tool responses into findings
│   │   │   ├── pricing.py                      # Load price schedules and estimate request cost
│   │   │   └── pricing.json                    # Versioned public model rates
│   │   └── reporting/
│   │       ├── html_report.py                  # Prepare report data and render standalone HTML
│   │       ├── templates/                      # Report HTML templates
│   │       ├── css/                            # Report styles
│   │       └── js/                             # Report filters and printing
│   └── ingestion/
│       ├── file_crawler.py                     # fetch_page / fetch_pages_nested (used by the server)
│       └── pull_html.py                        # Standalone HTML download helper
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

| Extractor                  | Focus                                                       | Output tokens (visionaid.org) |
| -------------------------- | ----------------------------------------------------------- | ----------------------------- |
| `semantic_checklist_01.py` | Page title, headings, links, landmarks, tables, iframes     | ~17,600                       |
| `forms_checklist_02.py`    | Form fields with label source, instructions, required flags | ~2,500                        |
| `nontext_checklist_03.py`  | Images (4 categories), SVGs, icon fonts, video/audio        | ~19,200                       |

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
- evaluator code, its entry point, and tests pass Ruff lint checks
- the tracked synthetic pytest suite (`uv run pytest -q`), with no private data or provider calls
- a full pipeline dry run, asserting prompts generated, findings found, and zero tokens consumed
- `index.html`'s inline JavaScript parses
- the Docker image builds, becomes healthy, serves the site, and returns a valid NDJSON audit

Default pytest discovery is limited to `tests/`, where `tests/test_evaluation.py`
covers the evaluator end to end through its CLI with a fake provider. Optional
detailed evaluator cases live in the ignored `.local-tests/evaluation/` folder;
run them with `uv run pytest -q .local-tests/evaluation`. CI never needs them.

Run the evaluator lint checks locally with the dev dependencies installed by `uv sync`:

```bash
uv run ruff check vision_aid/evaluation entry_points/model_evaluation.py tests
```

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

| Flag                  | Default           | Description                                                   |
| --------------------- | ----------------- | ------------------------------------------------------------- |
| `--html`              | (required)        | Path to the HTML file to analyze                              |
| `--output-dir`        | `./output`        | Directory for results                                         |
| `--model`             | `claude-sonnet-5` | Anthropic model to use                                        |
| `--dry-run`           | off               | Generate prompts without calling the API                      |
| `--include-summaries` | off               | Include the 3 cross-cutting summary prompts                   |
| `--show-cost`         | off               | Print estimated dollar cost of the run based on model pricing |
| `--env-file`          | `.env`            | Path to environment file                                      |

### Report generator options

| Flag           | Default                  | Description                          |
| -------------- | ------------------------ | ------------------------------------ |
| `--output-dir` | `./output`               | Directory containing pipeline output |
| `--report-dir` | `./test_results/claude/` | Directory to write the CSV report    |

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

| Column                | Description                                                |
| --------------------- | ---------------------------------------------------------- |
| `ID`                  | Sequential row number                                      |
| `element_name`        | HTML element (e.g. `<img class="...">`, `<a> "link text"`) |
| `browser_combination` | Always `N/A` (static HTML analysis)                        |
| `page_title`          | Page title from the analyzed HTML                          |
| `issue_title`         | Short issue description                                    |
| `steps_to_reproduce`  | Element snippet or inspection steps                        |
| `actual_result`       | What was found                                             |
| `expected_result`     | What WCAG requires                                         |
| `recommendation`      | Suggested fix                                              |
| `wcag_sc`             | WCAG success criterion (e.g. `1.1.1`)                      |
| `category`            | Issue category (e.g. `Programmatic / Non-text Content`)    |
| `log_date`            | Date of the pipeline run                                   |
| `reported_by`         | `Programmatic` or the LLM model string                     |

## Cost Estimate

For visionaid.org homepage (using Claude Sonnet):

| Approach                  | Input tokens | Cost   |
| ------------------------- | ------------ | ------ |
| Monolithic (entire HTML)  | ~487,000     | ~$1.52 |
| Element-specific pipeline | ~18,000      | ~$0.32 |

The pipeline skips prompts with empty payloads (e.g., no forms on the page = no form prompts), so actual cost varies by page content.

## Attribution

| Contributor   | What they own                                                          | Key files                                                                                                 |
| ------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| ahildebrandt3 | Extractors, programmatic checkers (CL01–CL03), CL01 prompts            | `processing_scripts/llm_preprocessing/`, `processing_scripts/programmatic/`                               |
| Andrew Yin    | CL02 + CL03 extractors, CL02 + CL03 prompts, LLM client, pipeline docs | `processing_scripts/llm_preprocessing/`, `processing_scripts/llm_client/`, `processing_scripts/llm/*.txt` |
| nfulton99     | HTML ingestion, packaging                                              | `vision_aid/ingestion/pull_html.py`, `pyproject.toml`                                                     |
| ColeANiblett  | Pipeline orchestration, prompt system, report generator                | `processing_scripts/llm/{registry,slicers,templates}.py`, `entry_points/`, `docs/`                        |

## Model Evaluation

### Choose an evaluation model

Each Evaluation run uses one fixed model through Anthropic Messages or OpenAI
Chat Completions.
Choose it with `--model`; omitting the flag selects Haiku 5.5. The evaluator
accepts only these exact IDs:

| Model | `--model` value | Provider endpoint | Thinking / reasoning | Effort |
| --- | --- | --- | --- | --- |
| Haiku 5.5, default | `claude-haiku-5-5` | Anthropic Messages | Adaptive thinking | Medium |
| Opus 5.5 | `claude-opus-5-5` | Anthropic Messages | Adaptive thinking | Medium |
| Sonnet 5.5 | `claude-sonnet-5-5` | Anthropic Messages | Adaptive thinking | Medium |
| GPT-6 Luna | `gpt-6-luna` | OpenAI Chat Completions | Reasoning | Medium |
| GPT-6.1 Sol | `gpt-6.1-sol` | OpenAI Chat Completions | Reasoning | Medium |

For example, add `--model gpt-6-luna` to the run command below to evaluate
GPT-6 Luna. Friendly names and aliases are rejected. Settings are fixed presets,
and all five models use a 24,192-token output cap that includes reasoning/thinking
and final text. Adaptive thinking does not reserve a fixed number of tokens for
final text. Matching effort labels and output caps do not imply equal computation
between providers. Temperature is omitted and summaries are disabled. The selected
model, provider, endpoint, and settings are saved with each run.

Preview any preset without either API key by omitting `--live`. The preview shows
its provider, endpoint, settings, public token rates, and cost guardrail. Live
requests run sequentially without retries or fallback models.

### Get a final report with the supplied Human audit

From the repository root, use the supplied `Pristine Accessibility Defect Report.xlsx`
(16 Home and Global defects). Keep the Excel file and its approved baseline
available locally. A fresh checkout must create a baseline through the CSV
workflow below or supply an existing file with `--baseline PATH`.

1. **Save a Benchmark snapshot.** For the one-page workflow,
   create the ignored directory and save the homepage HTML there:

   ```bash
   mkdir -p .model-evaluation
   curl --fail --location --silent --show-error \
     --output .model-evaluation/pristine-home.html https://pristineai.com/
   test -s .model-evaluation/pristine-home.html
   ```

   Check that the file contains the intended homepage. `curl` saves server HTML;
   if the browser builds the content, save rendered HTML there instead. Use
   `https://pristineai.com/` as its source URL.

2. **Set up live access and choose a limit.** Set `OPENAI_API_KEY` for GPT models
   or `ANTHROPIC_API_KEY` for Claude models in your environment or the ignored
   repository-root `.env`. Only the selected provider's key is required.
   Set `MAX_COST_USD` to a positive amount you approve. The limit is checked before each paid request;
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

   The CLI shows the selected model's provider, endpoint, thinking/reasoning settings,
   effort, output token cap, prompt count, token rates, pricing version, snapshot
   checksum, and limit.
   The cost guardrail is checked between requests; a request underway can exceed it.
   Estimated run cost sums each request's reported token usage at its applicable
   public price tier. GPT models use the higher tier above 272,000 total input
   tokens; Haiku 5.5 uses it above 100,000. Equality uses the lower tier, and
   input counts from separate requests are never combined to select a tier.
   OpenAI cache reads and writes replace ordinary input charges, and completion
   usage already includes reasoning. Anthropic's cache categories are separate
   input counts; its write rate is for five-minute caching.
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
   `$RUN_DIR/artifacts/raw-llm-responses.json` has model responses, unchanged raw
   provider usage, and each request's billable categories and estimated cost;
   `$RUN_DIR/artifacts/raw-programmatic-findings.json` has the original checker output.

5. **Review the LLM matches in one CSV.** Open `$RUN_DIR/review.csv` in
   Excel or a CSV-aware text editor. An approved Evaluation baseline populates
   classifications, reasons, and Programmatic matches. Review the LLM finding IDs,
   `match_reason`, and `review_notes` using the guide below. Keep the approved
   classification and Programmatic fields fixed. Save the file as CSV.

6. **Generate the final report.** Run `report` after completing the review,
   naming whoever made the decisions:

   ```bash
   uv run visionaid-evaluate report --run-dir "$RUN_DIR" --reviewer "Your name or agent description"
   ```

   Open `$RUN_DIR/report.html` in a browser. This self-contained offline report
   identifies the evaluated page, model, run ID, and reviewer, and leads with the
   LLM detection rate. Programmatic and Overall detection rates show exact counts
   and explain their denominators. Cost, recorded tokens, and saved pricing
   provenance are included.

   The findings table follows the Human audit's original order. Each **View
   evidence** control opens the original Human evidence, Eligibility classification,
   explanation, matched finding text and IDs, check identity, rationale, and notes.
   These native controls work with a keyboard and with JavaScript disabled. A copied
   HTML file needs no neighboring run files or internet connection.

   Not-testable findings remain in Overall while staying outside source-specific
   denominators. Reporting rejects incomplete runs, missing classifications, and
   invalid or reused finding IDs. Successful regeneration replaces that report's
   superseded Markdown file. It never repeats paid model calls.

### Capture the Human audit's listed pages

Save one Benchmark snapshot for each URL in the Human audit's `URL list` sheet:

```bash
uv run visionaid-evaluate capture \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --output-dir .model-evaluation/pristine-snapshots
```

The output directory must be new. Capture downloads only the listed URLs in
source order and follows redirects, retaining each originally listed URL as
the page identity. It saves separate `page-001.html`, `page-002.html`, and later
HTML files, then writes `snapshots.json` with the Human audit checksum and
source URLs mapped to relative HTML filenames. Resolve those filenames beside
`snapshots.json` when reusing the saved inputs.

Capture needs no model API key or Live-run approval. It saves server HTML and
does not render JavaScript or discover more pages. An HTTP or network error
stops capture immediately. Earlier HTML files remain, but capture writes no
snapshot mapping until every download succeeds. Start another capture in a
new directory after addressing the failure.

### Create an Evaluation baseline through CSV review

New `run` and `run-all` invocations require an approved Evaluation baseline,
including previews. The supplied Human audit can reuse its approved local
baseline when available. Baseline JSON files remain untracked and are not
included in installed package data; fresh checkouts must prepare or supply one.
For a new Human audit, capture its listed pages first, then prepare a review
using saved HTML and existing Programmatic checks:

```bash
uv run visionaid-evaluate baseline-prepare \
  --human-audit "/path/to/new-audit.xlsx" \
  --snapshots .model-evaluation/new-audit-snapshots/snapshots.json \
  --output-dir .model-evaluation/new-audit-review
```

The output directory must be new. Preparation makes no model requests or
network downloads and requires no model choice, credentials, or cost limit.
It copies the snapshots and retains the original Human evidence and checker
results. Open the generated CSV files in Excel or another CSV editor:

| File | What the reviewer does |
| --- | --- |
| `classifications.csv` | One row per original Human finding, including each Global once. Fill `classification` and `classification_reason`. |
| `programmatic-review.csv` | One row per applicable Human finding and page. Fill `programmatic_finding_refs` and `programmatic_reason`. |
| `programmatic-findings.csv` | Read-only catalog of checker findings with short references, page URLs, rule IDs, descriptions, element text, targets, and locations. |

Use the four classification values described below. Programmatic responsibility
is limited to existing rules that fully cover the original defect. In the page
review, copy references such as `P001-F003` from the catalog. Separate joint
matches with semicolons, for example `P001-F003;P001-F004`, and explain how they
together cover the complete defect. Select only that page's findings, and use
each reference for at most one Human finding. A shared WCAG criterion alone is
not a match. For no complete match, leave references blank and explain the
absence in `programmatic_reason`. Every page row needs a deliberate decision.
Programmatic classifications require complete matches on every applicable page;
LLM classifications may have Programmatic cross-catches; not-testable
classifications cannot claim matches.

Keep the original evidence, identities, headers, and all rows unchanged. Rows
may be sorted. Save the two edited files as CSV. The generated `README.md`
provides the review instructions beside the files. No reviewer needs to write
JSON, calculate checksums, or construct DOM selectors.

Approve the completed review:

```bash
uv run visionaid-evaluate baseline-approve \
  --review-dir .model-evaluation/new-audit-review \
  --reviewer "Reviewer name and review method"
```

Approval validates completeness, unchanged source evidence, classification
rules, page ownership, unique matches, and finding reuse before writing
`baseline.json` in the review directory. Use `--output /path/to/new-baseline.json`
to choose another new filename. Approval refuses to overwrite an existing
baseline. Errors identify the file and affected Human finding or page; edit the
CSV and retry. Approval records the reviewer's judgment; it does not automate
the semantic decision that selected findings fully cover the defect.

The CLI generates the audit checksum, stable Human identities, and reusable
rule/evidence expectations from the saved evidence. References such as
`P001-F003` are only review aids and do not become run-specific IDs in the
baseline. The baseline belongs to the Human audit alone; the prepared snapshots
support its review without becoming baseline selection keys.

Use the approved file when preparing each model run:

```bash
uv run visionaid-evaluate run-all \
  --human-audit "/path/to/new-audit.xlsx" \
  --snapshots .model-evaluation/new-audit-snapshots/snapshots.json \
  --baseline .model-evaluation/new-audit-review/baseline.json \
  --model gpt-6-luna --max-cost-usd 5
```

Add `--live` only when ready for the normal live-run approval. Each fresh run
copies its approved decisions and leaves only LLM matching rationale and notes
editable. Rule changes require deliberate new CSV review and approval. Editing
an Excel audit changes its checksum and Human identities, so prepare a new
review for the changed audit. The saved-run `correct-all` command has been
removed; new runs start with approved decisions. Existing saved evidence and
reports remain historical artifacts.

### Preview a Full evaluation

Prepare every listed page from the saved Benchmark snapshots:

```bash
uv run visionaid-evaluate run-all \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --model gpt-6-luna \
  --max-cost-usd 5
```

The snapshot mapping must match the supplied Human audit's checksum and every
listed URL in source order. HTML filenames resolve beside the mapping. The
preview uses saved HTML without downloading again and needs no model API key.
It displays all pages, the total prompt count, one fixed model preset, saved
token prices, and one positive allowance shared across the Full evaluation.

Local Human findings map to pages by the listed target URL in Steps to
Reproduce, preserving original text and identities. Page names and URLs in
recommendations do not assign findings. The known `/Contact/` alias maps to
`/contact/`; other paths retain their case. Missing or ambiguous assignments
stop preparation. Each page's review contains its local findings and every
Global finding, including pages with no local findings.

The Human audit checksum selects an available local Evaluation baseline
automatically from `vision_aid/evaluation/baselines/<audit-sha256>.json`.
That directory is ignored by Git. Newly approved files remain in their review
directory unless the operator explicitly chooses another output path.
For another audit, add `--baseline path/to/approved-decisions.json` to select
approved decisions explicitly. Preparation selects the source once and copies
the same complete baseline into the parent and every child as
`artifacts/evaluation-baseline.json`, with checksums in their manifests.
Each page receives the approved classifications and Programmatic explanations;
expected matches resolve to that child's actual finding IDs. Missing or
non-unique expected checker evidence stops preparation with the affected Human
finding and page. Audits without approved decisions must first complete the
CSV baseline preparation and approval steps above.

Each invocation creates a fresh `.model-evaluation/full-runs/<run-id>/`
directory. Its `full.json` records ordered membership and preparation status;
`human-findings.json` retains unique originals and their page assignments.
Each child under `pages/` keeps the existing Evaluation run files, including
its copied snapshot, prompts, pricing, Programmatic findings and review CSV.
Preview leaves execution incomplete and makes no paid requests. A preparation
failure stops later pages and retains earlier and partial evidence with its
stopping reason.

### Execute a Full evaluation

Add `--live` to the preview command to execute all prepared pages with the
selected provider's API key:

```bash
uv run visionaid-evaluate run-all \
  --human-audit "Pristine Accessibility Defect Report.xlsx" \
  --snapshots .model-evaluation/pristine-snapshots/snapshots.json \
  --model gpt-6-luna \
  --max-cost-usd 5 \
  --live
```

Every page is prepared before the CLI displays the full scope and asks for
one Live-run approval. Type `yes` to approve all listed pages, or add
`--approve-live` for explicit noninteractive approval. That option requires
`--live`. Declined approval makes no model requests. GPT models require
`OPENAI_API_KEY`; Claude models require `ANTHROPIC_API_KEY`.

Pages execute in URL-list order, using the same model preset throughout.
The allowance covers the entire Full evaluation. Before each page, the CLI
subtracts prior reported estimated cost and passes the remainder to that
page's executor, which checks the limit before each request. A request underway
can exceed the limit. If it completes all remaining work, execution still
completes; otherwise the CLI starts no further requests once the allowance
is exhausted. Request failures also stop later work, without retries.

The parent `full.json` saves page completion, stopping reason, estimated cost,
and reported usage, including usage from failed requests and partial pages.
Completed and partial child evidence remain available. A completed execution
still needs human review before final scoring. Completed page runs can use
the existing `report` command even if a later page fails.

Start a fresh invocation after failure. Each invocation creates new parent
and child directories and repeats every model request, including pages that
completed in a previous attempt. It reuses captured HTML without downloading
again; it does not resume or reuse previous paid outputs.

### Review and report a Full evaluation

After every page completes execution, edit each child's `review.csv` under
`.model-evaluation/full-runs/<run-id>/pages/`. When an Evaluation baseline is
saved, review each page's LLM matches, LLM matching rationale, and notes using
the one-page full Match requirements below. Keep the populated classifications,
classification reasons, Programmatic finding IDs, and approved Programmatic
explanations fixed. Each page includes all Global findings, whose LLM evidence
is reviewed separately on every page. Baseline creation establishes
responsibilities independently of what a model happened to catch.

Generate the individual page reports and the combined report:

```bash
uv run visionaid-evaluate report-all \
  --run-dir .model-evaluation/full-runs/<run-id> \
  --reviewer "Name and how the page decisions were reviewed"
```

`report-all` validates every listed execution, child evidence identity, and
page review before writing final combined rates to the parent's `report.html`.
It verifies that every child uses the exact approved source retained by the
parent, rejects edits to fixed decisions, and resolves all expectations against
actual page evidence again. Later edits to the original baseline file do not
change saved runs. Reports retain baseline approval attribution alongside the
LLM reviewer and distinguish approved Programmatic explanations from LLM
matching rationale.
Open that file in a browser. It is a self-contained offline document with every
original Human finding once, the reviewer attribution, and embedded readable
matching evidence. Global findings show a compact table of every page's decision,
including misses and findings Not testable from the page file. Open the independent
page evidence controls to compare the matches, check identities, rationale, and
notes for several pages. The parent needs no child reports or neighboring files.
The command also generates each child's `report.html` and totals saved estimated
cost, provider-reported usage, and Unreadable responses. The supplied
audit has 86 originals across 17 pages; repeated Globals produce 198 review
rows, while the combined Overall denominator stays 86.

A Global earns combined credit when one page's selected findings fully cover
it. Several findings from one source on that page may jointly cover it.
Partial evidence on different pages never earns combined credit. LLM and
Programmatic catches may come from different pages, but Overall counts that
Global once. Repeated catches on several pages also count once.

The approved baseline fixes each Global's classification across its pages.
Each original enters its source denominator once, including when that source
misses it. Not-testable originals remain in Overall. Combined rates use pooled
finding counts, rather than averages of page percentages. A catch by the other
source counts in Overall but earns no credit in the expected source's rate.

Missing or incomplete execution, invalid reviews, missing expected evidence,
inconsistent saved baselines, or conflicting testable Global classifications
withhold final combined rates. Restore approved decisions or investigate missing
checker evidence before running `report-all` again. Regenerating a report
removes the previous parent HTML and legacy Markdown report before validation,
so invalid revised reviews cannot leave stale combined rates. Available individual
reports and evidence remain. Each HTML file is published only after rendering
succeeds. Successful reporting removes superseded generated Markdown for the
regenerated reports; unrelated historical runs remain untouched. To report one
completed child after a later page failure, use:

```bash
uv run visionaid-evaluate report \
  --run-dir .model-evaluation/full-runs/<run-id>/pages/<child-run-id> \
  --reviewer "Name and how this page was reviewed"
```

### Reading the detection charts

Both report scopes lead with an LLM detection bar, followed by Programmatic and
Overall results. Bar length uses a common 0% to 100% scale. Every bar shows its
caught count, eligible count and percentage, with the same values in a labelled
semantic table. A rate with no eligible findings has an explanation and no bar.
The Overall denominator includes all imported Human findings, including findings
Not testable from the page file. Source-specific rates count only catches by that
source among the findings expected from it; cross-catches still earn Overall
credit.

Full reports also compare page LLM results in Human audit page order. Page
eligibility varies, and Global findings repeat in page results while counting
once in the combined result. Do not add page counts or average page percentages
to calculate the combined result. The comparison is not a controlled ranking of
pages or model quality. Individual reports omit this comparison.

Charts and their exact-data tables work offline without JavaScript. Labels and
values convey the results without relying on color; tables have their own
horizontal scroll regions on narrow screens.

### How the evaluator reads LLM responses

The evaluator reads each LLM response using va-dat's own parsing and reporting
code. This keeps the evaluation consistent with how va-dat produces its CSV
report.

**Parsing.** The evaluator parses each response with va-dat's JSON parser,
including its code-fence and repair steps. If va-dat cannot parse a response,
or the check's rule cannot read its structure, it counts as an Unreadable
response. Examples include one object where a list is expected, or text where
`issues`, `vague_headings`, or `header_clarity_issues` should be a list.
An Unreadable response gives no LLM findings. The evaluator lists the check
under `format_failures` in `run.json` and continues with the next check.

**What counts as a finding.** For the 12 checks covered by va-dat's CSV report,
the evaluator applies va-dat's per-check rules. Each row those rules would
produce becomes one LLM finding:

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

Each finding's problem, element, and location use the text va-dat would
write in its CSV row. `raw_source` keeps the full item, or for page title,
headings, and landmarks the whole response plus the specific issue.

**What is skipped.** The evaluator skips va-dat's false-positive filter and LLM
deduplication. The filter guesses from the page HTML and can remove a finding
other than the one it matched. Deduplication costs extra LLM calls and is not
repeatable. Evaluation counts therefore measure what the model reported and
will not match the rows in va-dat's downloadable CSV report.

**Checks shown on screen only.** Six checks have no rule in va-dat's CSV
report. Their results appear only in the web app's on-screen panel:
`table_semantics`, `placeholder_as_label`, `group_labels`, `form_instructions`,
`complex_descriptions`, and `media_captions`. The evaluator still reads them,
giving at most one finding per item, and only when the item's `issues` list is
non-empty (for tables, `issues` or `header_clarity_issues`). Every
`placeholder_as_label` item is a finding, because that check only receives
placeholder-only fields. Yes/no answers never create a finding on their own.
A table response may be one object or a list. These findings have
`"screen_only": true`. The individual Evaluation report, `report.html`, labels them as shown
on screen only and absent from va-dat's CSV report.

### Evaluation run files

The run root holds the review evidence and scored results. Supporting files
are together under `$RUN_DIR/artifacts/`. Without `--live`, the command prepares
the prompts but makes no model requests; neither LLM output file exists yet.
The `report` command adds `report.html` at an individual run root. The Full
evaluation `report-all` command adds `report.html` at the parent and each child
run root. Reports can regenerate from saved reviewed evidence without model calls;
both commands require explicit reviewer attribution.

Reports embed all evidence, styling and controls for offline use. Search includes
collapsed Human and matched tool evidence, recorded explanations, rationale and
notes. Each matching excerpt has a Show match control that opens its evidence
panel. Full reports can filter by page; selected-page outcomes appear beside the
combined outcomes without changing the complete-run detection results.

The LLM and Programmatic missed filters include only findings eligible for that
source. Caught filters include cross-catches by that source. Clear filters restores
all original findings. Expand all visible evidence and Collapse all visible
evidence affect the filtered rows and their visible page panels. With JavaScript
disabled, all findings and native evidence disclosures remain available.

Use **Print report** in either report to print the report header, cost and
detection results through the last bar chart. The findings table, detailed
evidence and scoring explanations after the charts are omitted. Printing works
offline and preserves filters and opened disclosures without changing scores
or saved reviews.

The browser's Print command uses the same summary layout, including when
JavaScript is disabled. Printed output and browser PDF
export are not verified accessible PDFs; accessible PDF production is outside
this feature's scope.

New runs and reporting use only this layout. Existing run directories remain
untouched and require manual reorganization before the updated `report` command
can read them. Move their supporting files into `artifacts/`, including the
`prompts/` and `payloads/` directories, preserving filenames. There is no
compatibility fallback or automatic migration.

| File                                       | Role                                                                                                                                                                                                                  |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `review.csv`                               | Original Human audit evidence, source sheet and row, stable IDs, and the decision columns the reviewer edits.                                                                                                         |
| `snapshot.html`                            | The full Benchmark snapshot used to judge testability and coverage.                                                                                                                                                   |
| `normalized-llm-findings.json`             | LLM findings with `finding_id` values for `review.csv`, read as described above. An Unreadable response can appear in `artifacts/raw-llm-responses.json` without producing a finding here.                            |
| `normalized-programmatic-findings.json`    | Checker results converted to findings with `finding_id` values for `review.csv`.                                                                                                                                      |
| `run.json`                                 | Configuration, snapshot checksum, prompt list, completion status, format failures, token usage, and estimated cost. `complete: true` does not imply that every response parsed successfully; check `format_failures`. |
| `report.html`                              | Self-contained Evaluation report generated after successful reporting; a Full evaluation parent embeds all page matching evidence.                                                                                                                                                                  |
| `artifacts/evaluation-baseline.json`       | Approved decisions copied into baseline-backed runs, with an integrity checksum recorded in `run.json`; later shared edits do not rewrite historical interpretation. |
| `artifacts/human-findings.json`            | Canonical imported local and Global Human findings used to validate and score the review.                                                                                                                              |
| `artifacts/pricing.json`                   | The versioned public model rates and capture date used to estimate this run's cost from reported usage. Older runs retain their original price schedule.                                                              |
| `artifacts/raw-llm-responses.json`         | Live model replies, request outcomes, and reported token usage, including responses that could not be parsed into findings.                                                                                           |
| `artifacts/raw-programmatic-findings.json` | Original output from the Programmatic checks.                                                                                                                                                                         |
| `artifacts/prompts/*.json`                 | The exact `prompt_text` and filtered `payload_slice` prepared for each model request. These files do not hold model replies in an Evaluation run.                                                                     |
| `artifacts/payloads/cl01_payload.json`     | Extracted headings, links, landmarks, tables, and other semantic page structure.                                                                                                                                      |
| `artifacts/payloads/cl02_payload.json`     | Extracted forms, fields, and labels.                                                                                                                                                                                  |
| `artifacts/payloads/cl03_payload.json`     | Extracted images, SVGs, icons, and media.                                                                                                                                                                             |

The payload files show extracted page data before filtering. The prompt files
show what the model actually received after filtering and slicing. To review a
Human finding, compare its original evidence in `review.csv` with the two
normalized findings files and inspect `snapshot.html` for the full Benchmark
evidence. Check
`artifacts/raw-llm-responses.json` when an LLM finding is missing or malformed, and
check the file under `artifacts/prompts/` to see whether the model received the
relevant evidence.
Record decisions in `review.csv`; the `report` command reads that CSV and the
run evidence to write `report.html`. The pipeline briefly writes
`artifacts/manifest.json`, but the Evaluation command removes it and keeps the
relevant metadata in
`run.json`.

Earlier private experiments may also contain `preflight.json` with advance
token counts and a spending plan, `format-diagnostics.json` with an offline
inspection of malformed replies, and `review-validation.json` with checks on
the completed review. The standard `visionaid-evaluate run` command does not
create those files or perform those extra checks.

### Approved decisions for a single page

When present locally, an approved Evaluation baseline is automatically selected
by the SHA-256 of the Excel file. Model and snapshot identities do not select
the baseline. To select approved decisions for another audit explicitly, add
`--baseline path/to/approved-decisions.json` to `visionaid-evaluate run`.
Audits without a local baseline must supply an approved file created through
`baseline-prepare` and `baseline-approve`.
For an audit with a `URL list`, `--source-url` selects that page's local Human
findings and all Globals; an unlisted URL is rejected. Older audits without a
URL list retain the Home and Global selection.

Preparation fills `classification`, `classification_reason`,
`programmatic_finding_id`, and `programmatic_match_reason`. These are approved
fields: reporting rejects edits to them. Expected catches identify an existing
rule and relevant element or page evidence, then resolve to the actual finding
IDs in this run. Missing or non-unique evidence stops preparation or reporting
with the Human finding, page, rule, and evidence to investigate. A Programmatic
classification requires a complete expected catch; classification alone never
awards coverage. An empty expectations list records an explained absence,
including for LLM-eligible findings that have no Programmatic cross-catch.

Reviewers edit `llm_finding_id`, `match_reason` (LLM reasoning), and
`review_notes`. Practical semantic matching and complete-coverage requirements
still apply. Joint matches and cross-catches are supported; not-testable rows
cannot claim a catch. The report distinguishes approved Programmatic explanations
and baseline approval attribution from the per-run LLM review.

The run saves its approved source in `artifacts/evaluation-baseline.json` and
pins its checksum in `run.json`. Reporting uses that saved copy, so a later
baseline update does not change historical results. To change approved
responsibilities or expectations, prepare a new CSV review, approve it into a new
baseline file, and prepare new runs. Editing a run's CSV does not update shared
decisions. Programmatic rules are never changed or classifications inferred
automatically by this workflow.

The generated JSON records the audit checksum, reviewer attribution, and one
decision per original Human finding, with explicit Programmatic expectations or
absences for every applicable page. The CLI derives stable rule/evidence
selectors from the selected checker findings. Run preparation resolves those
expectations against its own evidence; missing or non-unique evidence fails
rather than manufacturing a catch. Changed-page-evidence policy and checker-rule
changes remain outside this workflow.

### Fill in `review.csv`

The CSV has one row for each applicable Human finding. The supplied Home page
has 16 Home or Global findings. Keep
the header, all rows, and their `human_finding_id` values. The columns from
`human_finding_id` through `comment` identify the Human finding and preserve its
original evidence. Use them to understand the defect, but do not edit them.
In particular, `source_sheet` and `source_row` point back to the Human audit,
`page_scope` says Home or Global, and `source_element` copies the Human audit's
`element name`. It is not an inferred location on the page.

Keep the populated `classification` and `classification_reason` unchanged.
During baseline CSV review, use these classifications:

| `classification` value | Use it when                                                                                                                                           |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `llm_eligible`         | The Benchmark snapshot contains enough evidence to judge the defect, and the issue calls for the LLM's judgment.                                      |
| `programmatic`         | A Programmatic check can establish the defect from the available evidence. Classification alone does not mean the checker found it.                   |
| `unavailable_evidence` | The snapshot lacks evidence needed to verify the defect, such as behavior that requires interaction or a browser or assistive technology observation. |
| `ambiguous`            | The Human finding is too unclear to decide fairly whether a finding covers it.                                                                        |

During baseline review, base classification on the Human finding and available
evidence, independently of model output. Explain the choice in
`classification_reason`, including missing or unclear evidence. In each run,
retain that approved explanation.

Then complete the remaining decision columns for that row:

| Column                    | What to enter                                                                                                                                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `llm_finding_id`          | Copy `finding_id` values from `$RUN_DIR/normalized-llm-findings.json` only when the selected LLM findings **jointly cover the whole Human finding**. Separate multiple IDs with semicolons (`;`). Otherwise leave blank.       |
| `programmatic_finding_id` | Keep the approved, automatically resolved value unchanged. |
| `match_reason`            | Explain how the selected LLM findings fully cover the Human defect. Keep Programmatic explanations in their approved separate column.                                      |
| `programmatic_match_reason` | Keep the approved explanation for the Programmatic match or deliberate absence unchanged. |
| `review_notes`            | Optional context, such as a more precise location or a finding that covers only part of the defect. Notes do not award coverage.                                                                                               |

You may use findings from both files for one row. Each finding ID must exist in
the named file and can be assigned to only one Human finding. Leave the LLM ID
cell blank when no LLM findings fully cover the row; that records a miss, even if
you describe partial evidence in `review_notes`. For `unavailable_evidence` and
`ambiguous` rows, leave both ID cells blank. The report command checks these
rules and requires a `match_reason` whenever you enter an LLM ID.

#### Using Codex or Claude Code for the review

If you use Codex or Claude Code to fill out `review.csv` and generate the
report, give it the following prompt to guide semantic matching and avoid
incorrectly rejecting valid matches:

```text
Review LLM matches in the latest run, fill out its LLM decision columns in `review.csv`, and generate the report. Keep approved classification and Programmatic fields unchanged. Use practical semantic matching.
Count a match when a finding identifies the same underlying accessibility problem in the same element or relevant section, even if its wording, certainty, examples, or recommended fix differ from the Human audit.
Treat examples in a Human finding as illustrations of the problem unless they clearly describe separate defects. A different remediation recommendation does not invalidate detection of the problem.
Conditional or tentative findings can count when they identify the reported defect and the Human audit supplies the context needed to support that interpretation. Use the saved HTML to confirm the location.
Allow multiple findings together to cover a Human finding. Reject matches that merely share a WCAG criterion, concern a different element, or leave a distinct part of the reported problem undetected.
Record qualifications in `review_notes` rather than automatically withholding credit. Apply this interpretation of full coverage consistently.
```

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
