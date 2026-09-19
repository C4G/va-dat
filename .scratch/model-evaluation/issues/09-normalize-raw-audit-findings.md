# 09: Normalize every raw audit prompt response

**What to build:** Convert saved raw audit responses into lossless canonical audit findings without relying on the production CSV, suppression rules, or model-based deduplication.

**Blocked by:** 08: Execute and record an authorized live audit.

**Status:** resolved

- [x] Every active non-summary prompt has a fixed normalizer, including categories omitted by the production CSV.
- [x] Canonical audit findings retain run and model identity, prompt, checklist, page, problem family and statement, location evidence, WCAG evidence, raw source, and parse status.
- [x] Valid object, array, fenced JSON, empty, malformed, and unknown prompt responses produce explicit deterministic outcomes.
- [x] Successful malformed responses produce no usable findings and remain visible as format failures.
- [x] Normalization performs no model or network call and applies no heuristic suppression or deduplication.
- [x] Synthetic fixtures cover every prompt normalizer without copying private or live provider data.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Synthetic normalization tests cover the complete prompt registry
and all specified parse outcomes.
