# 03: Live verification run with an agent reviewer

**What to build:** The operator sees the new report produced from real model output. One paid Evaluation run is made on the saved Pristine homepage snapshot. A sub-agent acting as the reviewer fills in every `review.csv` row, and the report is generated and read as an outsider would read it. The operator authorized this spend in the planning conversation; follow the spending controls in `.model-evaluation/live-run-plan.md` (sequential requests, no retries, stop on failure).

**Blocked by:** 02 (Plain-language report)

**Status:** ready-for-agent

- [ ] One live run on the saved Pristine homepage snapshot (`https://pristineai.com/`) with `--max-cost-usd 1.10` completes, or its stop reason is reported without a retry
- [ ] A sub-agent fills in every `review.csv` row. It classifies each Human finding against the snapshot before reading the LLM responses, then records Match decisions following the README's rules, with a reason for every classification and match
- [ ] `report` succeeds with `--reviewer "Claude agent (operator-directed)"`
- [ ] The generated report is read end to end, and any wording that still needs knowledge of the evaluator is reported to the operator
- [ ] The run's estimated cost and detection rates are recorded under Comments

## Comments
