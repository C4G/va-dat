# 02: Plain-language report

**What to build:** A reader with no knowledge of the evaluator opens `report.md` and learns, in plain language, which Human findings the LLM and the Programmatic checks caught, what the tool said, why each catch counts, what was missed, and what could not be tested. `report` requires `--reviewer`. The report follows the layout in `../spec.md`, in this order:

1. title;
2. How to read this report;
3. Summary;
4. Human findings table;
5. What each part of the tool caught;
6. Missed;
7. Not testable from the page file.

It contains no IDs, CSS paths, location JSON, raw evidence JSON or raw usage JSON. Scoring semantics are unchanged.

**Blocked by:** 01 (Rename to Human audit and LLM vocabulary)

**Status:** resolved

- [x] `report` fails without `--reviewer`; with it, the Summary shows "Review decisions by: <text>"
- [x] The title is "LLM accessibility evaluation: <source URL>", and the Summary shows the model and run ID
- [x] "How to read this report" says:
  - the benchmark is the Human audit;
  - the tool has two parts (the LLM and programmatic checks), each defined;
  - the tool saw only the saved HTML;
  - a reviewer set expectations and only full coverage counts;
  - the scope is the homepage only
- [x] The LLM, Programmatic and Overall detection rates each appear as a sentence with the count, the denominator explained, and a percentage; zero eligible findings is stated in words
- [x] The cost line shows dollars rounded to cents, input and output tokens, and the pricing-schedule publication date, and ends "The actual bill may differ slightly." Cached and cache-creation tokens appear only when non-zero
- [x] A sentence names the LLM checks with malformed output out of the total prompt count, and is omitted when there are none
- [x] The table has one row per Human finding in source order, with columns for the Issue Title, WCAG, expected part (LLM / Programmatic checks / Not testable), and ✓/✗ for each part; cross-catches are marked, and a footnote explains what the rates count
- [x] Each caught Human finding lists its matched findings, labelled "LLM (<prompt in words> check)" or "Programmatic check <rule ID>", with the problem text and "Why this counts:" giving the match reason
- [x] "Missed" lists every `llm_eligible` or `programmatic` Human finding with no match, even when the classification reason and review notes are both empty; "Why it was expected to be caught" and "Why it was missed" appear only when non-empty
- [x] "Not testable from the page file" groups `unavailable_evidence` and `ambiguous` findings under one intro sentence, each with its classification reason
- [x] The report contains no Human finding or finding IDs, `source_element`, CSS paths or JSON blocks, and free text stays escaped for Markdown (inline HTML and table pipes)
- [x] Tests through the `main` seam cover each item above, including a cross-catch, a missed finding with no explanations, both not-testable classifications, and the zero-eligible wording
- [x] The README's description of `report` and its output matches the new layout, including the `--reviewer` argument

## Comments

- Operator correction: allow empty `classification_reason` values. A valid
  classification is still required for every Human finding, and a match reason
  is still required whenever a catch is claimed. The CLI test includes a missed
  finding with both classification reason and review notes blank. The source
  spec remains unchanged.
- Implemented in `be15c06e50b07e4033e278c4ac79cfd8248c51ba`.
  `report` requires a nonblank reviewer description and emits the seven specified
  sections with source-order table rows, cross-catches, matched problem text and
  reasons, all misses, and the combined not-testable group. It omits detailed IDs,
  source elements, locations, and raw JSON, while escaping free text. The README
  documents the layout and optional classification reasons.
- Scoring clarification: the spec's explicit unchanged scoring rule takes
  precedence over its contradictory exclusion prose. Not-testable findings stay
  outside the LLM and Programmatic rates and remain in the Overall denominator;
  the report and README say so.
- Verification: `uv run pytest -q` passed all 37 tests. The existing CLI suite
  covers reviewer requirement and attribution; explanatory prose and section
  order; 1/1 LLM, 1/1 Programmatic, and 2/3 Overall rates; both zero-eligible
  sentences; shuffled CSV source ordering; matched source labels and reasons;
  cross-catches; blank and explained misses; both not-testable classifications;
  inline HTML and table-pipe escaping; omitted evidence and location fields;
  nonzero cost rounded to cents, pricing date, cache counts present and absent;
  and unreadable-output wording present and absent. Existing classification,
  finding-ID, and required match-reason validation remain covered.
  `uv run python -m compileall -q vision_aid/evaluation tests/test_evaluation_cli.py`
  and `git diff --check` passed. No repository typechecker is configured; an
  isolated targeted mypy check also passed for the two changed production files.
- Parallel code review against `61ac26c01fefdfc9abd5bf5ad19f981a728acfd9`:
  Standards found no documented violations and one optional, low-severity
  Primitive Obsession observation about two local section-title comparisons.
  Kept the small renderer without added abstraction. Spec found zero findings;
  the independent reviewer also reran the CLI suite, with 8 tests passing.
- Python additions against main: 1,585 production lines and 2,593 including
  tests, versus the original 1,562 / 2,534 baseline. The report replaces old
  verbosity and reuses existing CLI fixtures and tests. No paid calls made in
  this ticket; live verification belongs to ticket 03.
