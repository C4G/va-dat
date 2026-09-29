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

**Status:** ready-for-agent

- [ ] `report` fails without `--reviewer`; with it, the Summary shows "Review decisions by: <text>"
- [ ] The title is "LLM accessibility evaluation: <source URL>", and the Summary shows the model and run ID
- [ ] "How to read this report" says:
  - the benchmark is the Human audit;
  - the tool has two parts (the LLM and programmatic checks), each defined;
  - the tool saw only the saved HTML;
  - a reviewer set expectations and only full coverage counts;
  - the scope is the homepage only
- [ ] The LLM, Programmatic and Overall detection rates each appear as a sentence with the count, the denominator explained, and a percentage; zero eligible findings is stated in words
- [ ] The cost line shows dollars rounded to cents, input and output tokens, and the pricing-schedule publication date, and ends "The actual bill may differ slightly." Cached and cache-creation tokens appear only when non-zero
- [ ] A sentence names the LLM checks with malformed output out of the total prompt count, and is omitted when there are none
- [ ] The table has one row per Human finding in source order, with columns for the Issue Title, WCAG, expected part (LLM / Programmatic checks / Not testable), and ✓/✗ for each part; cross-catches are marked, and a footnote explains what the rates count
- [ ] Each caught Human finding lists its matched findings, labelled "LLM (<prompt in words> check)" or "Programmatic check <rule ID>", with the problem text and "Why this counts:" giving the match reason
- [ ] "Missed" lists every `llm_eligible` or `programmatic` Human finding with no match, even when the classification reason and review notes are both empty; "Why it was expected to be caught" and "Why it was missed" appear only when non-empty
- [ ] "Not testable from the page file" groups `unavailable_evidence` and `ambiguous` findings under one intro sentence, each with its classification reason
- [ ] The report contains no Human finding or finding IDs, `source_element`, CSS paths or JSON blocks, and free text stays escaped for Markdown (inline HTML and table pipes)
- [ ] Tests through the `main` seam cover each item above, including a cross-catch, a missed finding with no explanations, both not-testable classifications, and the zero-eligible wording
- [ ] The README's description of `report` and its output matches the new layout, including the `--reviewer` argument

## Comments
