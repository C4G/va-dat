# 04: Generate and validate the homepage reference set

**What to build:** Transform the mandated workbook's Home and applicable Global rows into a traceable, human-reviewed reference set and generate the private Eligibility review needed to reach the no-spend approval gate.

**Blocked by:** 02: Bootstrap a private, safe evaluation workspace; 03: Freeze a reproducible Pristine benchmark snapshot.

**Status:** resolved

- [x] Workbook absence and SHA-256 drift fail with clear acquisition or validation guidance.
- [x] Imported records retain workbook filename, sheet, source row, raw evidence, canonical URL, page scope, and WCAG evidence without semantic rewriting.
- [x] The reference set includes every homepage and applicable Global row exactly once.
- [x] Eligibility is limited to `llm_eligible`, `programmatic`, `unavailable_evidence`, or `ambiguous`, with rationale and approval state required.
- [x] Global rows are represented as global claims with homepage evidence rather than multiplied across pages.
- [x] A private Eligibility workbook presents source evidence, proposed classification, rationale, approval, reviewer identity, confidence, timestamp, and notes.
- [x] Human-reviewed decisions round-trip into a validated, versioned reference set through the `EligibilityReviewer` interface.
- [x] Synthetic workbook tests cover provenance, filtering, review import, invalid decisions, and checksum validation.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Verified by the synthetic reference-set and CLI tests within the
55-test passing suite.
