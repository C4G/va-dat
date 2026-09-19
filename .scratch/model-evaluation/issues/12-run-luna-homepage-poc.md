# 12: Run the gated Luna homepage proof of concept

**What to build:** Execute the approved operational workflow on the private Pristine benchmark and produce the first illustrative Luna evaluation report without bypassing any human or spending gate.

**Blocked by:** 11: Verify the complete evaluation workflow.

**Status:** ready-for-agent

- [ ] The private workbook checksum, snapshot, reference set, and eligibility classifications are reviewed and approved before the audit proceeds.
- [ ] A no-cost evaluation-run summary presents the exact Luna configuration, request set, estimated usage, and planned cost limit.
- [ ] The live run begins only after point-of-use approval covering the displayed configuration and saved cost guardrail.
- [ ] The approved Luna run preserves all raw responses, attempts, usage, cost, latency, failures, and provenance.
- [ ] Canonical findings and candidate matches are generated without production CSV filtering or model-based deduplication.
- [ ] Ambiguous match decisions receive human approval before scoring.
- [ ] The final reports show Luna workbook-row recall, programmatic coverage, combined workbook coverage, estimated audit cost, tokens, latency, unmatched findings, and format failures.
- [ ] The result is labeled illustrative and makes no small-versus-large model claim from the homepage's limited eligible denominator.

## Comments

The run-oriented CLI ergonomics were implemented in `2448042` and hardened in
`6a1e6c0`. This operational ticket remains open: no private preparation, live
Luna request, human match review, or final proof-of-concept report was performed.
