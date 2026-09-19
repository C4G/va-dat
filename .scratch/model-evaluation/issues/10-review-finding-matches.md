# 10: Generate and validate finding matches

**What to build:** Turn canonical audit findings and approved reference defects into an efficient, evidence-rich human match review whose accepted decisions can be scored deterministically.

**Blocked by:** 04: Generate and validate the homepage reference set; 09: Normalize every raw audit prompt response.

**Status:** ready-for-agent

- [ ] Candidate generation removes only hard incompatibilities such as different pages or incompatible evidence categories.
- [ ] Candidate generation never awards credit or makes a semantic match decision.
- [ ] A private Matches workbook presents reference evidence, audit evidence, proposed disposition, rationale, confidence, approval, reviewer identity, timestamp, and notes side by side.
- [ ] An accepted match requires compatible page or scope, the same underlying accessibility failure, and compatible location, element, or element group.
- [ ] WCAG identifiers and remediation wording remain supporting evidence rather than exact-match requirements.
- [ ] Approved decisions round-trip through the `MatchReviewer` interface and enforce one-to-one matching.
- [ ] Conflicts, unresolved decisions, incomplete grouped evidence, and missing required sub-defects fail clearly rather than being resolved silently.
