# 10: Generate and validate finding matches

**What to build:** Turn canonical audit findings and approved reference defects into an efficient, evidence-rich human match review whose accepted decisions can be scored deterministically.

**Blocked by:** 04: Generate and validate the homepage reference set; 09: Normalize every raw audit prompt response.

**Status:** resolved

- [x] Candidate generation removes only hard incompatibilities such as different pages or incompatible evidence categories.
- [x] Candidate generation never awards credit or makes a semantic match decision.
- [x] A private Matches workbook presents reference evidence, audit evidence, proposed disposition, rationale, confidence, approval, reviewer identity, timestamp, and notes side by side.
- [x] An accepted match requires compatible page or scope, the same underlying accessibility failure, and compatible location, element, or element group.
- [x] WCAG identifiers and remediation wording remain supporting evidence rather than exact-match requirements.
- [x] Approved decisions round-trip through the `MatchReviewer` interface and enforce one-to-one matching.
- [x] Conflicts, unresolved decisions, incomplete grouped evidence, and missing required sub-defects fail clearly rather than being resolved silently.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Candidate generation, workbook round-trip, evidence validation,
and conflict tests pass in the synthetic suite.
