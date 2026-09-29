# 01: Rename to Human audit and LLM vocabulary (clean break)

**What to build:** An evaluator using the evaluation CLI works entirely in the glossary vocabulary (Human audit, Human finding, LLM finding, Programmatic finding). A new Evaluation run takes the benchmark spreadsheet via `--human-audit` and writes `human-findings.json`, `raw-llm-responses.json` and `normalized-llm-findings.json`. Its `review.csv` has `human_finding_id` and `llm_finding_id` columns, and its IDs carry `human-`, `llm-` and `programmatic-` prefixes. The run manifest records `human_audit_filename` and `human_audit_sha256`. CLI help and error messages and the README's evaluation sections use the glossary terms. `report` reads only the new names and still produces the current report layout; the layout is rewritten in ticket 02. There is no compatibility layer and no migration of old run directories. See the Rename decisions in `../spec.md`.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The `run` subcommand accepts `--human-audit` in place of `--workbook`, with the default-path constant renamed to match
- [ ] A run writes `human-findings.json`, `raw-llm-responses.json` and `normalized-llm-findings.json`, and never writes `references.json`, `raw-audit-responses.json` or `normalized-audit-findings.json` (asserted in tests)
- [ ] `review.csv` uses `human_finding_id` and `llm_finding_id` columns, and `report` validates against those columns
- [ ] Human finding IDs start with `human-`, LLM finding IDs with `llm-`, and Programmatic finding IDs with `programmatic-`; the hash part of each ID is unchanged
- [ ] LLM findings record `source` as `"llm"`
- [ ] The import module/function and records are renamed (`human_audit`, `import_homepage_human_findings`, `HumanFinding`, `HumanAudit` with `human_findings`)
- [ ] The LLM execution module is renamed `llm_audit`, and its request-client names are reviewed to match
- [ ] The manifest records `human_audit_filename` and `human_audit_sha256`, and `report` checks the Human audit checksum against them
- [ ] CLI help and error messages say "Human audit", "Human finding" and "LLM finding" instead of "Reference workbook", "Reference defect", "Excluded Reference" or "audit finding"
- [ ] The README's evaluation workflow, run-directory file table, review-column guide and troubleshooting text use the new names
- [ ] Classification values, the spreadsheet's sheet and column headers, and the programmatic artifact names are unchanged
- [ ] Evaluation CLI tests pass through the `main` seam with the fake LLM client, and the full test suite passes
- [ ] The commit is marked breaking (`!` and a `BREAKING CHANGE:` footer saying existing Evaluation run directories are unsupported)

## Comments
