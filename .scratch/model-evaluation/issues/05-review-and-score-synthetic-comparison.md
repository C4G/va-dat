# 05: Review and score a synthetic comparison

**What to build:** Demonstrate the complete deterministic review-to-report path with synthetic reference defects and findings, establishing the scoring seam before connecting real audit outputs.

**Blocked by:** 04: Generate and validate the homepage reference set.

**Status:** resolved

- [x] The `MatchReviewer` interface accepts human-reviewed decisions without coupling the scorer to Excel or future model adapters.
- [x] Match decisions support accepted, rejected, and needs-review states with reviewer provenance, rationale, confidence, and timestamp.
- [x] Validation enforces one-to-one matches and rejects conflicting accepted decisions.
- [x] Grouped rows receive one point when their grouped defect is matched, while rows with distinct required sub-defects require all parts.
- [x] The deterministic scorer calculates workbook-row recall, programmatic coverage, combined workbook coverage, unmatched findings, and parse failures from approved inputs.
- [x] Estimated audit cost is the sole ranking tie-breaker; latency, token usage, and evaluation cost remain informational.
- [x] JSON, CSV, and Markdown reports derive from one score object and agree on every total and row disposition.
- [x] Repeated scoring of identical inputs produces byte-equivalent structured results apart from deliberately excluded presentation timestamps.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Verified by deterministic scoring, matching, ranking, and
cross-format report tests within the 55-test passing suite.
