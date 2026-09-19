# 09: Normalize every raw audit prompt response

**What to build:** Convert saved raw audit responses into lossless canonical audit findings without relying on the production CSV, suppression rules, or model-based deduplication.

**Blocked by:** 08: Execute and record an authorized live audit.

**Status:** ready-for-agent

- [ ] Every active non-summary prompt has a fixed normalizer, including categories omitted by the production CSV.
- [ ] Canonical audit findings retain run and model identity, prompt, checklist, page, problem family and statement, location evidence, WCAG evidence, raw source, and parse status.
- [ ] Valid object, array, fenced JSON, empty, malformed, and unknown prompt responses produce explicit deterministic outcomes.
- [ ] Successful malformed responses produce no usable findings and remain visible as format failures.
- [ ] Normalization performs no model or network call and applies no heuristic suppression or deduplication.
- [ ] Synthetic fixtures cover every prompt normalizer without copying private or live provider data.
