# 08: Execute and record an authorized live audit

**What to build:** Add the guarded live-audit path that executes an explicitly authorized Luna run, preserves every raw outcome, and accounts for reliability, usage, cost, and latency.

**Blocked by:** 01: Make audit request configuration explicit; 07: Prepare a safe Luna dry run.

**Status:** ready-for-agent

- [ ] Live execution requires the explicit live flag, API key, maximum audit-cost limit, and the exact summarized benchmark configuration.
- [ ] Audit prompts run sequentially with medium reasoning, no temperature, disabled summaries, and the existing output limit.
- [ ] At most two additional attempts occur for timeouts, rate limits, and server errors using bounded exponential backoff.
- [ ] Authentication, invalid-request, parsing, and successful malformed-response failures are not retried.
- [ ] Every attempt records request identity, response metadata, usage, duration, stop reason, and failure classification without exposing secrets.
- [ ] Billed retry usage contributes to audit cost, and the runner stops before starting another request once the cost guardrail is exhausted.
- [ ] Exhausted transient failures mark the run incomplete and unranked; malformed successful responses remain recorded as model-format failures.
- [ ] Fake-provider tests exercise success, retry, budget, malformed response, and incomplete-run behavior without spending money.
