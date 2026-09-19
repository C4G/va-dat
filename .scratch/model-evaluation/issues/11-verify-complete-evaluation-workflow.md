# 11: Verify the complete evaluation workflow

**What to build:** Connect preparation, audit, review, scoring, and reporting into one coherent workflow and prove the entire lifecycle with synthetic provider data before any real model run.

**Blocked by:** 05: Review and score a synthetic comparison; 06: Measure programmatic workbook coverage; 08: Execute and record an authorized live audit; 10: Generate and validate finding matches.

**Status:** ready-for-agent

- [ ] The CLI completes prepare, audit, review, and report workflows against a temporary private workspace using synthetic inputs.
- [ ] Ordinary comparisons reject mismatched snapshots, reference sets, prompts, parsers, eligibility decisions, or benchmark configurations.
- [ ] Run manifests contain content identity, code state, request configuration, retry policy, usage, pricing, timestamps, and run identity.
- [ ] Audit, evaluation, and total experiment costs remain separate, and only audit cost affects equal-recall ranking.
- [ ] End-to-end and per-request latency are reported but never ranked.
- [ ] JSON, CSV, and Markdown reports expose every in-scope workbook row and agree on scoring and coverage.
- [ ] CI runs the pytest suite without private workbook data, public network access, provider credentials, or spending.
- [ ] Documentation explains the private-data workflow, human approval gates, dry-run review, live authorization, and illustrative limits of the homepage benchmark.
