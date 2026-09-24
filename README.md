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

### Get a final report with the supplied Reference workbook

Run these commands from the repository root. The supplied
`Pristine Accessibility Defect Report.xlsx` is the default Reference workbook;
you do not need to pass `--workbook`. The existing Benchmark snapshot is
`.model-evaluation/snapshots/pristine-homepage/source.html`, and its recorded
source URL is `https://pristineai.com/`. The importer selects its 16 Home and
Global Reference defects.

1. **Set up live access and choose a limit.** Set `ANTHROPIC_API_KEY` in your
   environment or in the repository-root `.env` file (which Git ignores).
   Choose a positive USD amount that you approve for this experiment and set
   it as `MAX_COST_USD`. The limit is checked before each paid request. A
   request already in progress can put the final cost above the limit.

2. **Start a live Evaluation run.** Run this command in a terminal:

   ```bash
   MAX_COST_USD=1.00  # Example; replace with the amount you approve.
   uv run visionaid-evaluate run \
     --html .model-evaluation/snapshots/pristine-homepage/source.html \
     --source-url https://pristineai.com/ \
     --max-cost-usd "$MAX_COST_USD" \
     --live
   ```

   The command shows the fixed Haiku model, 16,000 thinking tokens, 24,192
   total output tokens, prompt count, pricing, Benchmark snapshot checksum,
   and cost limit. Type `yes` when asked for Live-run approval. The key alone
   does not approve spending. The command copies the Benchmark snapshot,
   imports the Reference defects, runs programmatic checks, sends the audit
   requests, and saves the responses and reported usage. It creates a **new**
   directory under `.model-evaluation/runs/`; write down the printed path.
   `--approve-live` is available for deliberate noninteractive approval.

3. **Check completion and review the findings.** Set `RUN_DIR` to the path
   printed by the live command. For example, replace the value below with
   your actual path:

   ```bash
   RUN_DIR='.model-evaluation/runs/<RUN_ID>'
   ```

   Open `$RUN_DIR/run.json` and confirm `"complete": true`. If it is `false`,
   the report command will reject the run. Failed requests are not retried;
   start a new live run after you address the failure or cost limit. Do not
   reuse the incomplete run. Inspect `$RUN_DIR/audit-findings.json` and
   `$RUN_DIR/programmatic-findings.json` for finding IDs, problems, locations,
   and raw evidence. `$RUN_DIR/raw-responses.json` has the model responses.

4. **Make the human decisions in one CSV.** Open `$RUN_DIR/review.csv` in
   Excel or a text editor. Keep its header, source fields, and one row per
   Reference defect. For **all 16 rows**, enter one `classification` value:
   `llm_eligible`, `programmatic`, `unavailable_evidence`, or `ambiguous`.
   Enter a short `classification_reason` for every row. `source_element`
   repeats the workbook's original `element name`; it is not a precise
   inferred location.

   When findings jointly cover a **whole** Reference defect, enter their IDs
   in `audit_finding_id` and/or `programmatic_finding_id`. Separate multiple
   IDs in one cell with semicolons (`;`). Enter a short `match_reason` when
   you enter any ID. Leave both ID cells blank for a miss. Use `review_notes`
   to explain partial coverage or location details; notes do not award
   partial credit. Do not assign findings to `unavailable_evidence` or
   `ambiguous` rows. Save the file as CSV.

5. **Generate the final report.** Running `report` confirms that human review
   is complete:

   ```bash
   uv run visionaid-evaluate report --run-dir "$RUN_DIR"
   ```

   Open `$RUN_DIR/report.md`. It contains Workbook-row recall, programmatic
   coverage, Combined workbook coverage, Estimated run cost, limitations,
   and a source-row explanation for each Reference defect. Reporting rejects
   an incomplete run, missing classifications or reasons, and unknown,
   wrong-kind, or reused finding IDs.

The run directory and supplied workbook are excluded from version control.
This one-homepage result is illustrative; it does not establish broad model
equivalence. Historical private runs remain untouched.

### Check the inputs without a paid request

Omit `--live` from step 2 to prepare a separate, incomplete Evaluation run.
It copies the Benchmark snapshot, imports the Reference defects, runs
programmatic checks, and saves the exact audit prompts. It does not contact
Haiku or produce Audit findings. It cannot produce a final report. To get a
report, follow steps 1–5 with a **new** live Evaluation run.

To use a new Benchmark snapshot, save its HTML as a new local file and pass
that file to `--html`. Set `--source-url` to the URL that the HTML represents.
Use the same saved HTML file for input checks and the live run so their input
is identical. The evaluator copies the file and records its checksum; it does
not capture a webpage.

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
- the complete synthetic pytest suite, with no private data or provider calls
- a full pipeline dry run, asserting prompts generated, findings found, and zero tokens consumed
- `index.html`'s inline JavaScript parses
- the Docker image builds, becomes healthy, serves the site, and returns a valid NDJSON audit

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
