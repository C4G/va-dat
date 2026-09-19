# 04: Generate and validate the homepage reference set

**What to build:** Transform the mandated workbook's Home and applicable Global rows into a traceable, human-reviewed reference set and generate the private Eligibility review needed to reach the no-spend approval gate.

**Blocked by:** 02: Bootstrap a private, safe evaluation workspace; 03: Freeze a reproducible Pristine benchmark snapshot.

**Status:** ready-for-agent

- [ ] Workbook absence and SHA-256 drift fail with clear acquisition or validation guidance.
- [ ] Imported records retain workbook filename, sheet, source row, raw evidence, canonical URL, page scope, and WCAG evidence without semantic rewriting.
- [ ] The reference set includes every homepage and applicable Global row exactly once.
- [ ] Eligibility is limited to `llm_eligible`, `programmatic`, `unavailable_evidence`, or `ambiguous`, with rationale and approval state required.
- [ ] Global rows are represented as global claims with homepage evidence rather than multiplied across pages.
- [ ] A private Eligibility workbook presents source evidence, proposed classification, rationale, approval, reviewer identity, confidence, timestamp, and notes.
- [ ] Human-reviewed decisions round-trip into a validated, versioned reference set through the `EligibilityReviewer` interface.
- [ ] Synthetic workbook tests cover provenance, filtering, review import, invalid decisions, and checksum validation.
