# 05: Review and score a synthetic comparison

**What to build:** Demonstrate the complete deterministic review-to-report path with synthetic reference defects and findings, establishing the scoring seam before connecting real audit outputs.

**Blocked by:** 04: Generate and validate the homepage reference set.

**Status:** ready-for-agent

- [ ] The `MatchReviewer` interface accepts human-reviewed decisions without coupling the scorer to Excel or future model adapters.
- [ ] Match decisions support accepted, rejected, and needs-review states with reviewer provenance, rationale, confidence, and timestamp.
- [ ] Validation enforces one-to-one matches and rejects conflicting accepted decisions.
- [ ] Grouped rows receive one point when their grouped defect is matched, while rows with distinct required sub-defects require all parts.
- [ ] The deterministic scorer calculates workbook-row recall, programmatic coverage, combined workbook coverage, unmatched findings, and parse failures from approved inputs.
- [ ] Estimated audit cost is the sole ranking tie-breaker; latency, token usage, and evaluation cost remain informational.
- [ ] JSON, CSV, and Markdown reports derive from one score object and agree on every total and row disposition.
- [ ] Repeated scoring of identical inputs produces byte-equivalent structured results apart from deliberately excluded presentation timestamps.
