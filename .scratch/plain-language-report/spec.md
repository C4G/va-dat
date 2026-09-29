# Plain-language evaluation report and Human audit naming

Status: ready-for-agent

## Problem Statement

A reader of an Evaluation run's final report has to know how the evaluator works before the report makes sense. It uses undefined jargon: "Workbook-row recall", "Combined workbook coverage", "Reference defect", "Audit findings", and raw classification values such as `llm_eligible` and `unavailable_evidence`. Most of its length is spent on material the reader does not need, such as reference and finding IDs, the `source_element` field, CSS paths and location JSON, raw token-usage JSON, and a collapsible raw-evidence JSON block for every row. It never plainly says which defects the human testers reported, which of those the tool caught, which part of the tool caught each one, and which were missed. The report does not define "unavailable evidence" or "ambiguous", so a reader cannot tell why some defects were left out of the scores.

The same jargon runs through the evaluator's code, artifact files, review CSV columns, CLI flags and README. "Workbook" names the file format of the benchmark rather than what it is: an audit performed by humans. "Audit finding" is ambiguous, because the human testers also produced an audit.

## Solution

The report is rewritten for a reader who knows nothing about the evaluator. It opens with a short "How to read this report" section and gives the headline numbers as plain sentences with their denominators explained. A single table then shows every Human finding and whether the LLM, the Programmatic checks, or neither caught it. For each catch the report shows what the tool said and the reviewer's reason the catch counts. Every miss is listed with background on why it was expected to be caught and why it was missed. Findings that could not be tested from the saved page are grouped under one plain heading, "Not testable from the page file", each with its reason. The estimated cost is explained as token counts multiplied by published prices. The report states who made the review decisions, so agent-made decisions are never mistaken for human adjudication.

The evaluator adopts the glossary in `CONTEXT.md` everywhere, including code, artifact files, CSV columns, CLI flags, error messages and the README. The terms are Human audit, Human finding, LLM, LLM finding, Programmatic checks, Programmatic finding, LLM detection rate, Programmatic detection rate, Overall detection rate, and Not testable from the page file. The rename is a clean break with no migration of old run directories.

## User Stories

1. As a report reader with no knowledge of the evaluator, I want a short "How to read this report" section at the top, so that I understand what is being measured before I see any numbers.
2. As a report reader, I want the benchmark called the "Human audit" and each of its defects a "Human finding", so that I know the comparison is against human testers and not a spreadsheet artifact.
3. As a report reader, I want the two parts of the tool named "the LLM" and "programmatic checks", each defined in one sentence, so that I can tell AI judgment from fixed rules.
4. As a report reader, I want to be told that the tool saw only a saved copy of the page's HTML, not a live browser or screen reader, so that I understand why some human findings could not be tested.
5. As a report reader, I want to be told that a catch counts only when the tool's findings cover the whole Human finding, so that I don't read partial matches as successes.
6. As a report reader, I want to be told the evaluation covers the homepage only, so that I don't generalise the numbers to the whole site.
7. As a report reader, I want the LLM detection rate written as a sentence ("Of the 8 Human findings the LLM could be expected to detect from the page's HTML, it caught 3 (37.5%)"), so that I know what the percentage is out of.
8. As a report reader, I want the Programmatic detection rate written the same way, so that I can compare the two parts of the tool on equal terms.
9. As a report reader, I want an Overall detection rate saying how many of all Human findings were caught by either part, so that I see the tool's total reach.
10. As a report reader, I want a rate with zero eligible findings stated in words and not as a division by zero, so that the summary never shows a meaningless percentage.
11. As a report reader, I want to see the model and run ID in the summary, so that I know which configuration produced these results.
12. As a report reader, I want the estimated cost in dollars and cents with the token counts and the price-list date it came from, so that I understand it is an estimate and how it was calculated.
13. As a report reader, I want cached-token counts mentioned only when they are non-zero, so that the cost line stays short in the common case.
14. As a report reader, I want a plain sentence naming any LLM checks that returned unreadable output, so that I know some LLM misses were caused by broken responses and not poor judgment.
15. As a report reader, I want that sentence left out when every LLM check returned readable output, so that I'm not distracted by a "none" line.
16. As a report reader, I want a table with one row per Human finding showing its title, WCAG criterion, which part of the tool it was expected from, and ✓/✗ for each part, so that I see the whole outcome at a glance.
17. As a report reader, I want the table to mark every catch even when the part of the tool that was not expected to catch a finding caught it, so that I see everything the tool actually found.
18. As a report reader, I want a footnote explaining that the detection rates count only catches by the expected part of the tool, so that a cross-catch ✓ that doesn't change a rate doesn't confuse me.
19. As a report reader, I want each caught Human finding to list the matched findings, labelled by source ("LLM (link clarity check)" or "Programmatic check LAND_001") with the tool's problem text, so that I can see what the tool actually said.
20. As a report reader, I want the reviewer's reason for each catch shown as "Why this counts", so that I can judge whether the ✓ is deserved.
21. As a report reader, I want the source labels to make the rule names cited in match reasons understandable, so that a reason like "LAND_001 reports exactly this" makes sense.
22. As a report reader, I want a "Missed" section listing every counted Human finding that nothing caught, so that the tool's gaps are explicit.
23. As a report reader, I want each missed finding to show why it was expected to be caught, so that I believe it was a real miss and not an impossible task.
24. As a report reader, I want each missed finding to show why it was missed when the reviewer recorded a reason, so that I understand the failure.
25. As a report reader, I want a missed finding listed even when neither explanation was recorded, so that no miss is silently hidden.
26. As a report reader, I want findings classified as unavailable evidence or ambiguous grouped under "Not testable from the page file", with one sentence saying they are left out of every detection rate, so that I don't need to learn two internal categories.
27. As a report reader, I want each not-testable finding shown with the reviewer's specific reason, so that I know why it couldn't be tested.
28. As a report reader, I want the report to say who made the review decisions, so that I know whether a human or an agent judged the matches.
29. As a report reader, I want no IDs, CSS paths, location JSON, raw evidence JSON or raw usage JSON in the report, so that the document stays readable.
30. As a report reader, I want Human findings shown in the Human audit's original order, so that I can cross-reference the original spreadsheet.
31. As an evaluator, I want `report` to require a reviewer description, so that I can't publish a report that hides who made the decisions.
32. As an evaluator, I want the CLI flag for the benchmark spreadsheet called `--human-audit`, so that the command reads in the project's vocabulary.
33. As an evaluator, I want the imported Human findings saved as `human-findings.json`, so that the artifact name says what it holds.
34. As an evaluator, I want the review CSV columns called `human_finding_id` and `llm_finding_id`, so that I know which ID goes in which column.
35. As an evaluator, I want LLM artifacts called `raw-llm-responses.json` and `normalized-llm-findings.json`, so that they sit alongside the programmatic `raw-…`/`normalized-…` files under matching names.
36. As an evaluator, I want IDs prefixed `human-`, `llm-` and `programmatic-`, so that I can tell at a glance what kind of item an ID refers to when filling in the review CSV.
37. As an evaluator, I want CLI help and error messages to use the glossary terms ("Human finding", "LLM finding"), so that errors match the vocabulary in the CSV and README.
38. As an evaluator, I want the run manifest to record `human_audit_filename` and `human_audit_sha256`, so that its provenance fields use the same name as the concept.
39. As an evaluator, I want the README's evaluation workflow, file table, review-column guide and report description updated to the new names and layout, so that the instructions match what's on disk.
40. As an evaluator, I want the classification values (`llm_eligible`, `programmatic`, `unavailable_evidence`, `ambiguous`) unchanged in the CSV, so that the reviewer still records the finer distinction even though the report combines two of them.
41. As a maintainer, I want the rename to be a clean break with no compatibility code, so that the evaluator doesn't carry fallbacks for throwaway local output.
42. As a maintainer, I want the change marked as breaking in its commit, so that anyone holding an old run directory knows `report` will no longer read it.
43. As a maintainer, I want tests that fail if old artifact names are written again, so that the rename can't silently regress.
44. As a maintainer, I want scoring rules unchanged, so that the new report's rates equal the old metrics under new names.
45. As the operator, I want the change verified with a real paid run reviewed by an agent acting as the reviewer, so that I can judge the new report against real model output before relying on it.

## Implementation Decisions

- **Glossary.** `CONTEXT.md` already holds the resolved terms, and ADR 0002 has been reworded to "LLM detection rate" and renamed accordingly. The ranking decision itself is unchanged. This spec supersedes the "Out of Scope" decision in the `rename-audit-artifacts` spec that kept the name "Audit finding".
- **Report module.** The report writer in the review module is rewritten. Its inputs are the same (the manifest, reviewed rows, and LLM and Programmatic findings) plus the reviewer description and the pricing-schedule date. It emits these sections in order:
  1. title "LLM accessibility evaluation: <source URL>";
  2. How to read this report;
  3. Summary;
  4. Human findings table;
  5. What each part of the tool caught;
  6. Missed;
  7. Not testable from the page file.
- **Scoring semantics unchanged.**
  - LLM detection rate: `llm_eligible` rows with at least one matched LLM finding, out of all `llm_eligible` rows.
  - Programmatic detection rate: `programmatic` rows with at least one matched Programmatic finding, out of all `programmatic` rows.
  - Overall detection rate: rows with any match, out of all imported Human findings, so not-testable findings stay in that denominator.
  - Review validation rules are unchanged, including that not-testable rows cannot claim matches.
- **"Expected to be caught by" mapping.** `llm_eligible` shows as "LLM", `programmatic` as "Programmatic checks", and `unavailable_evidence`/`ambiguous` as "Not testable".
- **Missed definition.** A missed finding is an `llm_eligible` or `programmatic` Human finding with no matched finding of either kind. It is always listed. "Why it was expected to be caught" (the classification reason) and "Why it was missed" (the review notes) appear only when non-empty.
- **Finding source labels.** LLM findings are labelled "LLM (<prompt name with underscores turned into spaces> check)". Programmatic findings are labelled "Programmatic check <rule ID>". Both come from the finding's recorded prompt field.
- **Cost line.**
  - The dollar amount is the run's estimated cost rounded to cents; the exact figure stays in the manifest.
  - Input and output token counts are always shown. Cached and cache-creation counts are shown only when non-zero.
  - The price date is the recorded pricing schedule's publication date, and the line ends "The actual bill may differ slightly."
- **Malformed-output sentence.** It names the LLM checks listed as format failures in the manifest, in words, out of the total prompt count, and is omitted when there are none.
- **Markdown safety.** Free text from the Human audit, review CSV and findings is still escaped for inline Markdown, including raw HTML and table pipes.
- **Reviewer attribution.** The `report` subcommand gains a required `--reviewer` text argument, printed in the summary as "Review decisions by: <text>".
- **Rename (clean break, no migration or compatibility layer):**
  - CLI flag `--workbook` → `--human-audit`, and the default path constant renamed to match.
  - Artifact `references.json` → `human-findings.json`.
  - Human audit import module and function renamed to `human_audit` / `import_homepage_human_findings`.
  - Records `ReferenceDefect` → `HumanFinding` and `ReferenceSet` → `HumanAudit`; its collection field becomes `human_findings`.
  - Field and CSV column `reference_id` → `human_finding_id`; CSV column `audit_finding_id` → `llm_finding_id`.
  - Manifest and HumanAudit fields `workbook_filename`/`workbook_sha256` → `human_audit_filename`/`human_audit_sha256`.
  - Artifacts `raw-audit-responses.json` → `raw-llm-responses.json` and `normalized-audit-findings.json` → `normalized-llm-findings.json`.
  - Finding `source` value `"audit"` → `"llm"`.
  - The LLM execution module is renamed `llm_audit`, and its request-client names are reviewed to match.
  - ID prefixes `ref-` → `human-` and `finding-` → `llm-`; `programmatic-` is unchanged. The hash portion of each ID is unchanged.
  - User-facing CLI help text and error messages use the glossary terms.
  - README evaluation sections are updated to the new names and report layout.
- **Unchanged:** the classification values, the Human audit's sheet name and column headers (source data), the programmatic artifact names, the prompt/payload/snapshot/pricing artifacts, and the shared pipeline used by the web server.
- **Commit** as `refactor(evaluation)!:`/`feat(evaluation)!:` with a `BREAKING CHANGE:` footer saying existing Evaluation run directories are unsupported.

## Testing Decisions

- A good test drives the evaluator only through its external seam: the evaluation CLI's `main` entry point, with the LLM request client replaced by the existing fake. Tests assert on the files in the run directory and the text of `report.md`, never on internal helpers. This is the single seam, and it already exists.
- Prior art: the existing evaluation CLI tests already build a small Human audit spreadsheet and HTML input, run live with a fake client, edit `review.csv`, and assert on `report.md`. They also assert that old artifact names are absent after a run.
- Update the existing report assertions to the new rate sentences and names, e.g. LLM detection rate 1/1, Programmatic detection rate 1/1, Overall detection rate 2/3, and the zero-eligible wording.
- New assertions through the same seam:
  - The table marks a cross-catch: a `programmatic`-classified finding matched by an LLM finding shows ✓ under LLM without changing the LLM detection rate.
  - A missed finding with empty classification reason and review notes is still listed under "Missed".
  - Both `unavailable_evidence` and `ambiguous` findings appear under "Not testable from the page file" with their reasons.
  - Matched findings show their source label, problem text and "Why this counts".
  - The report contains no Human finding IDs, finding IDs, CSS paths or JSON evidence blocks.
  - `report` fails without `--reviewer`, and prints it when given.
  - The cost line shows cents and the pricing date, and the malformed-output sentence appears only when there are format failures.
  - Inline HTML in free text is still escaped.
  - After a run, the new artifact names exist and the old ones (`references.json`, `raw-audit-responses.json`, `normalized-audit-findings.json`) do not; review CSV columns use the new names; IDs use the new prefixes.
- No new unit tests below the CLI seam.
- **Live verification (operator-requested, paid):**
  1. After the tests pass, execute one live Evaluation run on the saved Pristine homepage snapshot (`https://pristineai.com/`) with a between-request cost guardrail of $1.10. Previous identical runs cost about $0.11.
  2. A sub-agent acting as the reviewer fills in every `review.csv` row. It classifies against the snapshot independently of the LLM responses, then records Match decisions using the README's rules.
  3. Generate the report with `--reviewer "Claude agent (operator-directed)"` and read it as an outsider would.

## Out of Scope

- Changing classification values, scoring rules, review validation rules, or the model ranking decision.
- Migrating, reading or deleting existing local run directories.
- Renaming the Human audit spreadsheet's sheet or columns.
- Changes to the shared pipeline, the web server, or `run_pipeline.py`.
- Precision or other metrics beyond the three detection rates.

## Further Notes

- Considered and rejected: showing "unavailable evidence" and "ambiguous" as two report categories. Readers need to know why each finding wasn't counted, and the per-row reasons say that better than category names. The CSV keeps the distinction.
- Considered and rejected: showing ✓/✗ without the tool's text. A ✓ is only believable if the reader can see what the tool said and why it counts.
- Considered and rejected: a migration script or a compatibility layer for old runs. The operator no longer needs them.
- The estimated cost is not an invoice: token counts are exact as reported by the provider, but dollar amounts depend on the recorded public price schedule.

## Comments
