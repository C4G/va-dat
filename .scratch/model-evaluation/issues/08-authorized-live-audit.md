# 08: Execute and record an approved live audit

**What to build:** Add the guarded live-audit path that executes a point-of-use approved Luna run, preserves every raw outcome, and accounts for reliability, usage, cost, and latency.

**Blocked by:** 01: Make audit request configuration explicit; 07: Prepare a safe Luna dry run.

**Status:** resolved

- [x] Live execution requires the explicit live flag, API key, saved maximum audit-cost limit, exact summarized benchmark configuration, and interactive or automatic approval.
- [x] Audit prompts run sequentially with medium reasoning, no temperature, disabled summaries, and the existing output limit.
- [x] At most two additional attempts occur for timeouts, rate limits, and server errors using bounded exponential backoff.
- [x] Authentication, invalid-request, parsing, and successful malformed-response failures are not retried.
- [x] Every attempt records request identity, response metadata, usage, duration, stop reason, and failure classification without exposing secrets.
- [x] Billed retry usage contributes to audit cost, and the runner stops before starting another request once the cost guardrail is exhausted.
- [x] Exhausted transient failures mark the run incomplete and unranked; malformed successful responses remain recorded as model-format failures.
- [x] The live manifest records approval mode and timestamp without claiming operator identity.
- [x] Existing live evidence is never overwritten; another execution requires a newly planned evaluation run.
- [x] Fake-provider tests exercise success, retry, budget, malformed response, and incomplete-run behavior without spending money.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Point-of-use approval and write-once run
execution were implemented in `2448042` and copy/rerun isolation was hardened
in `6a1e6c0`. Fake-provider tests verify approval, retry, checkpoint, budget,
malformed-response, and incomplete-run policies without spending.
