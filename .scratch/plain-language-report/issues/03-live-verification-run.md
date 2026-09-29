# 03: Live verification run with an agent reviewer

**What to build:** The operator sees the new report produced from real model output. One paid Evaluation run is made on the saved Pristine homepage snapshot. A sub-agent acting as the reviewer fills in every `review.csv` row, and the report is generated and read as an outsider would read it. The operator authorized this spend in the planning conversation; follow the spending controls in `.model-evaluation/live-run-plan.md` (sequential requests, no retries, stop on failure).

**Blocked by:** 02 (Plain-language report)

**Status:** ready-for-agent

- [ ] One live run on the saved Pristine homepage snapshot (`https://pristineai.com/`) with `--max-cost-usd 1.10` completes, or its stop reason is reported without a retry
- [ ] A sub-agent fills in every `review.csv` row. It classifies each Human finding against the snapshot before reading the LLM responses, then records Match decisions following the README's rules, with a reason for every classification and match
- [ ] `report` succeeds with `--reviewer "Codex agent (operator-directed)"`
- [ ] The generated report is read end to end, and any wording that still needs knowledge of the evaluator is reported to the operator
- [ ] The run's estimated cost and detection rates are recorded under Comments

## Comments

2026-09-29 verification:

- Operator corrections: attribute the available reviewer as Codex, and replace the saved homepage HTML before calculating its new checksum. The source spec and historical plan remain unchanged.
- Refreshed snapshot: 184,244 bytes, SHA-256 `a0b5f43b37ffa276b23d04da94e846c24ec2b2148ec9152ec448db7e68945c5a`. Human audit SHA-256 remains `f8e9c83d5de8155cd81c4d9c15180c6e38640a5aba7323d35040b81e39aa6c9a`.
- Report and reviewed CSV: `.model-evaluation/runs/20260929T215031-9f661935/{report.md,review.csv}`. All 16 rows reviewed by a fresh sub-agent; baseline frozen at 21:50:16 UTC before dispatch, SHA-256 `f7c1077a3e8441b1cf4e8b237145e0eb5cca550db6868a820d9b5a3d4c04ca19`.
- Independent classifications: 8 LLM-eligible, 4 programmatic, 4 unavailable, 0 ambiguous. Unlike the historical 6/6/4 plan, the complete heading-hierarchy defect and decorative text-link defect require contextual judgment. Classifications/reasons stayed frozen after dispatch; full matches require reasons and never reuse finding IDs.
- One live attempt used `--max-cost-usd 1.10`, fixed Haiku, 16,000 thinking tokens, 24,192 output cap, sequential requests and zero retries. Free counting found 7,421 input tokens; exact prepared prompts matched before paid dispatch. The private ledger reserved $1.50 for this attempt and accounted for $0.237422 of prior spending.
- All 8 requests succeeded with `end_turn`; none reached the output cap. SVG output contained valid fenced JSON followed by prose and was recorded as a format failure, without repair or retry. All raw replies and 16 LLM/29 Programmatic findings were inspected.
- Estimated cost: $0.104626 for 7,421 input and 19,441 output tokens, no cache usage, using the recorded 2026-09-22 prices reverified on 2026-09-29. Reconciled cumulative estimate $0.342048; remaining budget $4.657952.
- LLM detection 1/8 (12.5%); Programmatic detection 4/4 (100%); Overall detection 5/16 (31.25%, displayed 31.2%). Matches: Human audit findings 1, 2, 3, 7, 12; eligible misses 4, 5, 6, 8, 9, 10, 16; not testable 11, 13, 14, 15.
- `report --reviewer "Codex agent (operator-directed)"` succeeded. Reviewer, implementation agent and operator agent read it end to end; CSS selectors and internal review-phase wording were removed from live notes. Remaining reader limitations: "unreadable" means a parsing failure here; bundled findings include unrelated issues, repeat match reasons and make navigation credit unclear without knowing the no-reuse rule. Some frozen explanations retain accessibility/HTML terminology.
- Verification: `uv run pytest -q` (37 passed), `uv lock --check`, entry-point imports, and independent CSV/source/identity/rate/report checks passed. No production code or tests added. Snapshot, baseline, spending ledger and full run artifacts remain private and ignored.
