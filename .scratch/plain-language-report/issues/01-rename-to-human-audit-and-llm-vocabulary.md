# 01: Rename to Human audit and LLM vocabulary (clean break)

**What to build:** An evaluator using the evaluation CLI works entirely in the glossary vocabulary (Human audit, Human finding, LLM finding, Programmatic finding). A new Evaluation run takes the benchmark spreadsheet via `--human-audit` and writes `human-findings.json`, `raw-llm-responses.json` and `normalized-llm-findings.json`. Its `review.csv` has `human_finding_id` and `llm_finding_id` columns, and its IDs carry `human-`, `llm-` and `programmatic-` prefixes. The run manifest records `human_audit_filename` and `human_audit_sha256`. CLI help and error messages and the README's evaluation sections use the glossary terms. `report` reads only the new names and still produces the current report layout; the layout is rewritten in ticket 02. There is no compatibility layer and no migration of old run directories. See the Rename decisions in `../spec.md`.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] The `run` subcommand accepts `--human-audit` in place of `--workbook`, with the default-path constant renamed to match
- [x] A run writes `human-findings.json`, `raw-llm-responses.json` and `normalized-llm-findings.json`, and never writes `references.json`, `raw-audit-responses.json` or `normalized-audit-findings.json` (asserted in tests)
- [x] `review.csv` uses `human_finding_id` and `llm_finding_id` columns, and `report` validates against those columns
- [x] Human finding IDs start with `human-`, LLM finding IDs with `llm-`, and Programmatic finding IDs with `programmatic-`; the hash part of each ID is unchanged
- [x] LLM findings record `source` as `"llm"`
- [x] The import module/function and records are renamed (`human_audit`, `import_homepage_human_findings`, `HumanFinding`, `HumanAudit` with `human_findings`)
- [x] The LLM execution module is renamed `llm_audit`, and its request-client names are reviewed to match
- [x] The manifest records `human_audit_filename` and `human_audit_sha256`, and `report` checks the Human audit checksum against them
- [x] CLI help and error messages say "Human audit", "Human finding" and "LLM finding" instead of "Reference workbook", "Reference defect", "Excluded Reference" or "audit finding"
- [x] The README's evaluation workflow, run-directory file table, review-column guide and troubleshooting text use the new names
- [x] Classification values, the spreadsheet's sheet and column headers, and the programmatic artifact names are unchanged
- [x] Evaluation CLI tests pass through the `main` seam with the fake LLM client, and the full test suite passes
- [x] The commit is marked breaking (`!` and a `BREAKING CHANGE:` footer saying existing Evaluation run directories are unsupported)

## Comments

### Completed 2026-09-29

Implementation: `401822c9a4a60ac4e196f0bef53e07432990aed5` (`refactor(evaluation)!: adopt Human audit and LLM vocabulary`).

Verification: `uv run pytest -q tests/test_evaluation_cli.py` passed all 8 cases; `uv run pytest -q` passed all 37 tests. `uv run python -m compileall -q vision_aid/evaluation tests/test_evaluation_cli.py` and `git diff --check` passed. No dedicated typechecker is configured. Existing CLI main-seam cases verify the new Human audit flag, artifact names and legacy artifact absence, CSV columns, finding prefixes/source values, manifest provenance, legacy flag/CSV rejection, and Human audit checksum mismatch rejection using fake LLM clients. No paid requests were made.

Review: independent Standards and Spec agents reviewed the diff from `12c17ab311ae30e62e208f08784760c5a4449c12`; both reported zero findings. Spec review confirmed unchanged ID hash construction, classification values, source sheet/headers, Programmatic artifact names, report layout, scoring, and shared pipeline. Shared request classes are imported under LLM names only within the evaluator. The implementation commit carries `!` and the required `BREAKING CHANGE:` footer.

Size: production Python additions against main are 1,567 versus 1,562 before this ticket; all Python including tests is 2,565 versus 2,534.
