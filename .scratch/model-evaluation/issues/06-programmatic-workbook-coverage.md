# 06: Measure programmatic workbook coverage

**What to build:** Run the existing deterministic accessibility checks against the benchmark snapshot and show which workbook rows they actually cover, separately from model efficacy.

**Blocked by:** 04: Generate and validate the homepage reference set; 05: Review and score a synthetic comparison.

**Status:** ready-for-agent

- [ ] Existing semantic, form, and non-text programmatic checks run against the frozen snapshot without duplicated audit logic.
- [ ] Programmatic findings are normalized with stable page and location evidence while retaining their raw source.
- [ ] Reference matches are reviewable and use the same accepted-decision validation as other matches.
- [ ] A `programmatic` eligibility classification does not automatically award credit when the checker misses the row.
- [ ] Reports identify covered programmatic rows, uncovered checker responsibilities, unavailable evidence, and ambiguity.
- [ ] Programmatic results contribute to combined workbook coverage but never to model ranking.
- [ ] Tests exercise the complete programmatic path with synthetic HTML and approved match decisions.
