# 11: Verify the complete evaluation workflow

**What to build:** Connect preparation, audit, review, scoring, and reporting into one coherent workflow and prove the entire lifecycle with synthetic provider data before any real model run.

**Blocked by:** 05: Review and score a synthetic comparison; 06: Measure programmatic workbook coverage; 08: Execute and record an approved live audit; 10: Generate and validate finding matches.

**Status:** resolved

- [x] The CLI completes prepare, audit, review, and report workflows against a temporary private workspace using synthetic inputs.
- [x] Ordinary comparisons reject mismatched snapshots, reference sets, prompts, parsers, eligibility decisions, or benchmark configurations.
- [x] Run manifests contain content identity, code state, request configuration, retry policy, usage, pricing, timestamps, and run identity.
- [x] Audit, evaluation, and total experiment costs remain separate, and only audit cost affects equal-recall ranking.
- [x] End-to-end and per-request latency are reported but never ranked.
- [x] JSON, CSV, and Markdown reports expose every in-scope workbook row and agree on scoring and coverage.
- [x] CI runs the pytest suite without private workbook data, public network access, provider credentials, or spending.
- [x] Documentation explains the private-data workflow, evaluation-run planning, point-of-use live-run approval, run-scoped reviews, discovered reporting inputs, and illustrative limits of the homepage benchmark.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. The run-oriented synthetic lifecycle and
documentation were implemented in `2448042` and review-hardened in `6a1e6c0`.
The suite proves both review kinds, discovered reporting, approval failure
paths, immutable identities, and write-once execution without provider access.
