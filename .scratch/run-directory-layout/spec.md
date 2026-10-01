# Organize the Evaluation run directory for review and results

Status: ready-for-agent

## Problem Statement

A human completing `review.csv` must sift through an Evaluation run directory that mixes review evidence with raw outputs, extracted payloads, prompts, pricing, and canonical Human finding data. Most of those supporting artifacts are unnecessary for ordinary Eligibility classifications and Match decisions. The separate Human finding JSON duplicates evidence already included in the CSV, while the files the reviewer needs are scattered among internal artifacts.

The same root directory should remain useful after review, when the human reads the scored report. Clearing the root must also preserve access to run completion and malformed-response details, which currently appear in the run manifest and can affect how the reviewer interprets the findings.

## Solution

Keep the Evaluation run root focused on review and scored results. Leave the editable CSV, full Benchmark snapshot, both normalized finding lists, and the run manifest at the root. Generate the scored Markdown report there after successful review and reporting. Move supporting artifacts together into one `artifacts/` subdirectory, preserving their filenames.

The directory contract is:

| Artifact | Location | Purpose |
| --- | --- | --- |
| `review.csv` | Run root | Original Human finding evidence and editable human decisions |
| `snapshot.html` | Run root | Full Benchmark snapshot used to judge testability and coverage |
| `normalized-llm-findings.json` | Run root | LLM findings with copyable finding IDs |
| `normalized-programmatic-findings.json` | Run root | Programmatic findings with copyable finding IDs |
| `run.json` | Run root | Completion, malformed-response details, configuration, and provenance |
| `report.md` | Run root, after successful reporting | Scored results for the human reader |
| `human-findings.json` | `artifacts/` | Canonical imported Human findings for validation and scoring |
| `pricing.json` | `artifacts/` | Recorded price schedule for Estimated run cost |
| `raw-llm-responses.json` | `artifacts/` | Original LLM replies, usage, and request failures |
| `raw-programmatic-findings.json` | `artifacts/` | Original Programmatic check output |
| `prompts/` | Inside `artifacts/` | Saved prompts used by LLM execution |
| `payloads/` | Inside `artifacts/` | Extracted content used to prepare prompts |

A complete live run has exactly five files and the supporting directory at its root before reporting. Successful reporting adds the Markdown report. Preview and interrupted runs keep their existing artifact availability and completion semantics, with the same location rules for the artifacts they produce.

This is a clean break. New runs use only the new layout, and the updated report command reads only that layout. Existing run directories remain untouched and require manual reorganization before the updated report command can read them.

## User Stories

1. As a reviewer, I want the Evaluation run root to contain the files needed for review, so that I can identify my working evidence without sorting through internal artifacts.
2. As a reviewer, I want the review CSV to remain at the root, so that I can immediately find the file I must edit.
3. As a reviewer, I want the original Human finding evidence to remain in the CSV, so that I can review each finding without opening a duplicate JSON file.
4. As a reviewer, I want the Human audit's source sheet and row to remain in the CSV, so that I can trace the source evidence.
5. As a reviewer, I want the full Benchmark snapshot at the root, so that I can judge what the saved page can show.
6. As a reviewer, I want the normalized LLM findings at the root, so that I can inspect their evidence when making Match decisions.
7. As a reviewer, I want the normalized Programmatic findings at the root, so that I can inspect the fixed-rule evidence when making Match decisions.
8. As a reviewer, I want finding IDs to remain available in both normalized lists, so that I can copy valid IDs into the review CSV.
9. As a reviewer, I want existing artifact filenames preserved, so that the reorganization does not also require learning new names.
10. As a reviewer, I want the run manifest at the root, so that I can inspect run status before interpreting the findings.
11. As a reviewer, I want incomplete-run reasons preserved, so that I can understand why a run stopped.
12. As a reviewer, I want malformed-response details preserved, so that an empty finding list is not mistaken for evidence that a check found no problems.
13. As a reviewer, I want the scored report at the root after successful reporting, so that I can read the results where I performed the review.
14. As a report reader, I want the report's content unchanged, so that reorganizing files does not change the explanation of the results.
15. As a reviewer, I want supporting artifacts together in one subdirectory, so that they remain discoverable without crowding the root.
16. As a reviewer investigating a result, I want access to the original LLM replies, so that I can inspect missing or malformed output.
17. As a reviewer investigating a result, I want access to raw Programmatic findings, so that I can inspect the original check output.
18. As a reviewer investigating a result, I want access to saved prompts, so that I can see the evidence and instructions sent to the LLM.
19. As a reviewer investigating a result, I want access to extracted payloads, so that I can investigate preprocessing differences from the full Benchmark snapshot.
20. As an evaluator, I want canonical Human finding data retained under supporting artifacts, so that report validation remains reproducible without duplicating everyday reviewer context at the root.
21. As an evaluator, I want the saved price schedule retained under supporting artifacts, so that Estimated run cost remains traceable to its recorded prices.
22. As an operator, I want preview runs to use the new layout, so that file placement is consistent before and after live execution.
23. As an operator, I want preview runs to retain their existing restriction on paid requests, so that reorganizing files does not change Live-run approval.
24. As an operator, I want declined live execution to retain its existing preview evidence and status, so that I can inspect the prepared run.
25. As an operator, I want stopped runs to retain responses and usage in the new locations, so that request failures and exhausted cost guardrails remain inspectable.
26. As an operator, I want evidence saved after each attempted prompt as before, so that an interruption does not lose evidence already gathered.
27. As an evaluator, I want the run's identity to remain the root directory's name, so that the supporting directory is never mistaken for an Evaluation run.
28. As an evaluator, I want normalized findings to retain the correct run identity and source URL, so that evidence validation continues to reject unrelated findings.
29. As an evaluator, I want reporting to read supporting data from its new location, so that I can score reviews of newly generated runs.
30. As an evaluator, I want Eligibility classification and Match decision validation unchanged, so that moving evidence does not alter what counts as coverage.
31. As an evaluator, I want all detection rates unchanged for the same reviewed evidence, so that results remain comparable.
32. As an operator, I want existing run directories left untouched, so that this change does not move, overwrite, or delete prior evidence.
33. As a maintainer, I want the report command to read only the new layout, so that there is one supported artifact contract.
34. As an operator, I want the clean break documented, so that I know an old run needs manual reorganization before reporting.
35. As a maintainer, I want the shared pipeline's output layout outside evaluation preserved, so that the reviewer-focused change does not affect other pipeline users.
36. As a reviewer, I want review and troubleshooting instructions to use the new locations, so that the documented workflow matches generated runs.
37. As a maintainer, I want lifecycle tests to verify the root contents and supporting directory, so that internal artifacts cannot silently reappear at the root.
38. As a maintainer, I want verification through the existing CLI with a fake provider, so that the layout and scoring can be checked without paid execution or new testing interfaces.

## Implementation Decisions

- Modify the evaluation CLI's preparation and reporting behavior and the LLM execution module's artifact reads and writes. Retain the existing command arguments and run-directory interface.
- Use the directory contract in the Solution as the externally visible artifact layout. Preserve existing filenames, artifact schemas, CSV columns, finding ID formats, and report content.
- Create the supporting directory before writing or copying artifacts into it. Keep prompts and payloads nested inside that directory.
- Direct the evaluation use of the shared pipeline to the supporting directory for its outputs. Keep the full Benchmark snapshot and normalized Programmatic findings at the root, and preserve the existing cleanup of temporary pipeline output.
- Keep the Evaluation run root distinct from the pipeline output directory. Run manifests and normalized findings must retain the root directory's identity, not the name of the supporting directory.
- LLM execution reads the moved pricing and saved prompts, writes raw responses under supporting artifacts, and continues writing normalized LLM findings and the run manifest at the root.
- Preserve existing per-prompt persistence, response normalization, provider configuration, usage accounting, cost guardrails, and completion behavior. Malformed successful replies retain their current recorded status and normalized-finding behavior.
- Reporting reads canonical Human findings and pricing from supporting artifacts while reading the review CSV, normalized findings, and manifest from the root. Successful reporting writes the report at the root.
- Preserve Human audit identity checks, run identity checks, finding-source checks, source URL checks, review validation, and deterministic scoring.
- Apply the location rules to preview, declined execution, complete execution, and incomplete execution without creating artifacts earlier than their existing lifecycle stage.
- New generation and reporting support only the new layout. Add no old-layout fallback, migration command, or automatic changes to existing runs.
- Update the README's evaluation workflow, artifact table, review instructions, and troubleshooting locations. Explain that existing runs require manual reorganization before the updated report command can read them.
- Preserve the shared pipeline's usual output layout for callers outside evaluation.

## Testing Decisions

- Use one existing highest-level seam: the evaluation CLI's `main` entry point, with the existing LLM request client replaced by a fake for live-execution cases. The operator confirmed this lifecycle-testing approach with the complete plan.
- Good tests exercise generated files, retained evidence, CLI outcomes, and report results. They do not assert on internal path helpers, directory-creation call order, or implementation-specific module structure. No new test seam is needed.
- Prior art is the existing evaluation CLI lifecycle suite: it builds a small Human audit and Benchmark snapshot, runs preview or fake live execution, edits the generated CSV, and invokes reporting. It already checks hand-calculated detection rates, review validation, source evidence, run location, and request-failure and cost-guardrail behavior.
- Extend the preview test to check the new locations, preserved source evidence, retained root manifest and normalized Programmatic findings, absent live-only artifacts, no provider calls, and continued refusal to report an incomplete run.
- Extend the successful fake-live lifecycle test to assert the exact pre-report root entries, all supporting entries in their selected locations, and absence of duplicate supporting files at the root. Edit the root CSV using IDs from the root normalized findings, report successfully, and assert that only the report is added to the root.
- Preserve existing report and review-validation assertions, including reviewer attribution and hand-calculated LLM, Programmatic, and Overall detection rates. These verify that reporting can read the moved canonical evidence and price schedule without changing scoring.
- Verify that manifest and finding run IDs still match the run root's name and that existing checks reject evidence belonging to another run. Preserve the existing test for invocation from a worktree subdirectory.
- Extend stopped-run cases to verify raw responses and usage remain available in the selected locations, the root manifest retains the incomplete reason, normalized evidence is retained, and final reporting remains refused.
- Verify malformed successful replies retain their recorded format-failure details at the root and raw responses under supporting artifacts without changing completion semantics or inventing normalized matches.
- Verify per-prompt persistence through the fake provider boundary: before a subsequent request, evidence from the preceding request is already readable at the selected locations. Retain final saved evidence when execution stops.
- Verify reporting has no fallback to old root-level supporting files, using disposable test evidence rather than changing private run directories. Existing directories must not be automatically reorganized.
- Run the evaluation CLI lifecycle suite and the repository's applicable existing checks. Reuse existing shared-pipeline checks to confirm its ordinary output contract remains unchanged.
- No paid live verification is part of this spec.

## Out of Scope

- Generated reviewer guides, readable finding references, or replacement review interfaces.
- New status summaries, CLI warning behavior, filename changes, or artifact schema changes.
- Changes to Eligibility classifications, Match decisions, review validation, detection rates, model ranking, or report content.
- Changes to preprocessing, prompt content, provider configuration, pricing rules, cost guardrails, or Live-run approval.
- Migration commands, compatibility fallbacks, deletion, or automatic reorganization of existing runs.
- Relocating extra files created by historical one-off experiments.
- Changes to the shared pipeline's output layout outside evaluation.
- Paid live execution and implementation of the feature during spec publication.

## Further Notes

The CSV already contains the original Human audit evidence; its canonical JSON remains necessary for scorer validation but need not occupy the review-focused root. Normalized findings retain source evidence, while raw replies remain useful for diagnosing malformed LLM output.

The run manifest deliberately stays visible even though it also contains internal metadata. Moving it would require another way to expose completion and malformed-response status, and the agreed scope is reorganizing existing files.

Reviewers must continue judging Eligibility classifications against the full Benchmark snapshot. Content omitted from extracted payloads or prompts is not made unavailable merely by that omission. The reorganization does not change this rule.

The plan preserves the existing decisions to separate human review from deterministic scoring and to rank models by LLM detection rate with Estimated run cost as the tie-breaker. Artifact placement is cheap to reverse and does not warrant an additional ADR or glossary term.

## Comments

- Q1: The operator chose to support both review and scored results at the root.
- Q2: The operator chose to reorganize existing files only.
- Q3: The operator chose to keep the run manifest at the root.
- Q4: The operator chose one supporting artifact directory with existing filenames.
- Q5: The operator chose the new layout only, leaving existing directories untouched.
- Q6: The operator confirmed the complete plan and requested publication through the to-spec skill.
