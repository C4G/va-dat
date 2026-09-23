# Reduce the accessibility evaluation proof of concept

Status: ready-for-agent

## Problem Statement

The evaluation branch adds 8,764 lines and deletes 635 across 61 files relative to `main` at the time of review. It implements substantially more workflow, compatibility, validation, tests, and documentation than the immediate proof of concept needs. The maintainer needs a small, understandable experiment that works on the given Reference workbook and homepage, rather than a reusable evaluation framework.

The current generated review workbooks also label the source workbook's `element name` as `location`, implying precision the source does not provide. Eligibility and match review require too much machinery, and following an Evaluation run requires understanding file conventions and validation spread across several modules.

## Solution

Reduce the POC to one fixed Haiku evaluation using the given Reference workbook and an existing local HTML Benchmark snapshot. Provide a run, human review, report workflow: preview or explicitly approve paid execution, edit one CSV, then generate one Markdown report. Retain Workbook-row recall, programmatic coverage, Combined workbook coverage, Estimated run cost, and traceable evidence.

Target fewer than 3,000 added lines relative to `main`, counting code, tests, documentation, configuration, and other tracked changes. Reach that target by deleting unsupported scope and repeated coordination, not compressing code or weakening the meaning of the score.

## User Stories

1. As a maintainer, I want fewer than 3,000 added lines against `main`, so that I can review and understand the POC.
2. As an evaluator, I want one complete Haiku evaluation, so that I can demonstrate the measurement method without building model-comparison infrastructure.
3. As an evaluator, I want the importer to support the given Reference workbook directly, so that alternative workbook layouts do not complicate this experiment.
4. As an evaluator, I want every applicable Home and Global row retained, so that the denominator does not silently shrink.
5. As a reviewer, I want original defect text and source sheet and row preserved, so that I can trace each Reference defect to its evidence.
6. As a reviewer, I want the original element name displayed as `source_element`, so that it is not mistaken for an inferred precise location.
7. As a reviewer, I want optional `review_notes`, so that I can clarify location or partial coverage without rewriting source evidence.
8. As an evaluator, I want to supply local HTML and its source URL, so that the evaluator does not need a webpage-capture workflow.
9. As an evaluator, I want the snapshot copied into the Evaluation run with its checksum, so that the evaluated input remains identifiable.
10. As an operator, I want a no-cost preview, so that I can inspect the experiment before spending money.
11. As an operator, I want the fixed model configuration and positive cost guardrail displayed before Live-run approval, so that I understand what I am authorizing.
12. As an operator, I want credentials alone to be insufficient for execution, so that an available key cannot trigger accidental spending.
13. As an operator, I want a fresh directory for each Evaluation run, so that new execution does not overwrite earlier evidence.
14. As an operator, I want execution without a separately saved plan, so that I do not manage plan files or verification stages.
15. As an operator, I want failed requests to stop execution without automatic retries, so that failure behavior and additional spending remain simple.
16. As an evaluator, I want responses and reported usage retained when execution fails, so that unsuccessful work remains inspectable and its reported cost is accounted for.
17. As an evaluator, I want incomplete runs excluded from final scoring, so that partial execution cannot appear to be a complete result.
18. As an operator, I want the cost guardrail checked before each paid request, so that execution stops once accumulated reported cost reaches it.
19. As a reviewer, I want one CSV for eligibility and both finding kinds, so that I do not coordinate multiple review workbooks.
20. As a reviewer, I want to edit that CSV in Excel or a text editor, so that human review does not require a custom interface.
21. As a reviewer, I want classifications and Match decisions made by a human, so that the POC does not require an automated Comparison reviewer.
22. As a reviewer, I want to ask Codex to edit decisions on my behalf when needed, so that assistance uses the same review artifact without adding a reviewer subsystem.
23. As a reviewer, I want each row classified as LLM-eligible, programmatic, unavailable evidence, or ambiguous, so that the report distinguishes responsibility and evidence limitations.
24. As a reviewer, I want short reasons for classifications and matches, so that decisions remain explainable.
25. As a reviewer, I want separate audit and programmatic finding-ID columns, so that either or both finding kinds can cover the same Reference defect.
26. As a reviewer, I want stable finding IDs and inspectable finding evidence, so that I can enter defensible matches without candidate-generation machinery.
27. As a reviewer, I want to associate multiple findings with a row when necessary, so that jointly sufficient evidence is representable.
28. As a reviewer, I want to judge full-row coverage myself, so that the evaluator does not need a required-subdefect model.
29. As a reviewer, I want partial coverage documented in notes without automatically awarding credit, so that Workbook-row recall remains a full-row measure.
30. As an evaluator, I want invoking the report command to confirm completion of human review, so that per-row approval states and reviewer metadata are unnecessary.
31. As an evaluator, I want every row classified before reporting, so that unreviewed eligibility cannot change the denominator unnoticed.
32. As an evaluator, I want blank finding-ID cells to mean not caught when reporting, so that misses have a simple representation.
33. As an evaluator, I want invalid or conflicting finding IDs rejected, so that malformed review data cannot silently inflate coverage.
34. As an evaluator, I want deterministic Workbook-row recall over LLM-eligible rows, so that model efficacy is separate from programmatic coverage.
35. As an evaluator, I want programmatic coverage based on reviewed Programmatic findings, so that classification alone does not award credit.
36. As an evaluator, I want Combined workbook coverage to count each source row at most once, so that overlap between finding kinds does not inflate the result.
37. As an evaluator, I want unavailable and ambiguous rows visible in the report, so that exclusions and evidence limitations remain understandable.
38. As an evaluator, I want Estimated run cost derived from reported usage and recorded pricing, so that the experiment's cost is explainable.
39. As a reader, I want one Markdown report with metrics and row-level explanations, so that I can understand the outcome without reconciling report formats.
40. As an evaluator, I want the review CSV, exact prompts, configuration, raw responses, and pricing retained, so that the report has supporting evidence.
41. As an operator, I want existing private artifacts left untouched, so that simplifying the implementation does not destroy previous work.
42. As a maintainer, I want old-format compatibility removed, so that fresh POC runs do not carry historical workflow complexity.
43. As a maintainer, I want the public application's existing provider behavior preserved, so that reducing the evaluator does not regress unrelated functionality.
44. As a maintainer, I want focused tests and a synthetic run-to-report workflow, so that essential behavior is verified without duplicating the implementation.
45. As a maintainer, I want concise current documentation, so that superseded plans and progress narratives do not dominate the change.

## Implementation Decisions

- The supported experiment remains the pinned Haiku configuration already implemented: `claude-haiku-4-5-20251001`, 16,000 thinking tokens, 24,192 total output tokens, and omitted temperature. This reduction does not introduce model selection or change audit prompts, filtering, prompt ordering, or disabled summaries.
- Concentrate Evaluation run orchestration behind the existing CLI seam. Expose run and report operations, with no-cost preview and explicit Live-run approval before billable execution. Choose minimal flag spelling during implementation; obsolete workflow options need no compatibility aliases.
- The run operation imports the known Reference workbook, prepares the existing audit pipeline against the local Benchmark snapshot, performs approved execution, and produces evidence and the review CSV. Human review occurs by editing the CSV; reporting reads that run's evidence and decisions.
- Replace generalized workbook import with explicit mapping of the given sheets and columns. Remove header aliases and elaborate input-recovery messages. Ordinary input failures can fail plainly; retain small checks needed to prevent silently omitted or misidentified reference rows.
- Retain source sheet, row, original defect evidence, and the workbook's identity. Use `source_element` for the original element name and optional `review_notes` for reviewer clarification; do not infer locations automatically.
- Use one CSV row per Reference defect with eligibility, short classification and match reasons, and separate `audit_finding_id` and `programmatic_finding_id` fields. Permit multiple IDs within each finding field using one documented delimiter. Handle CSV quoting and multiline text with standard CSV support.
- Retain the four existing eligibility values: `llm_eligible`, `programmatic`, `unavailable_evidence`, and `ambiguous`. Human classifications are required. Codex assistance is an explicit human-directed edit, not an automated reviewer implementation.
- Remove generated Excel review workbooks, candidate-match generation, reviewer protocols for hypothetical future adapters, per-row approval states, reviewer identity, confidence, timestamps, and required-subdefect machinery. Preserve the substantive ADR-0001 decision: review produces decisions; a separate deterministic scorer consumes them.
- Entered finding IDs assert that the selected findings jointly provide full-row coverage. Partial coverage alone belongs in notes and does not earn credit. Reporting constitutes human confirmation that review is complete; blank finding fields then mean not caught.
- Retain validation of required classifications, row identity and completeness, finding existence and kind, and conflicting reuse of findings across reference rows. Allow multiple findings for one reference and allow both finding kinds to cover the same reference. Keep these checks focused on score correctness rather than general spreadsheet robustness.
- Preserve deterministic scoring semantics: Workbook-row recall measures audit coverage of LLM-eligible rows; programmatic classification alone does not count as coverage; Combined workbook coverage counts the union of covered in-scope rows once. Preserve the existing programmatic-coverage denominator and explicitly report unavailable and ambiguous rows. Remove multi-model ranking machinery without changing ADR-0002's ranking policy for future comparisons.
- Accept a local HTML Benchmark snapshot and source URL; copy the HTML into the fresh run directory and record its checksum. Remove evaluator-owned downloading, HTTP metadata validation, atomic snapshot-publication machinery, and capture recovery paths.
- Save workbook identity and imported reference evidence, copied HTML, exact prompts, actual configuration, raw responses, normalized findings, reported usage, pricing, and completion status. Preserve the existing normalization needed by the actual prompt and programmatic outputs; malformed model output must remain visible rather than silently disappearing.
- Remove separately persisted execution plans, plan reloading, repeated cross-module identity checks, compatibility with old artifact formats, workspace-initialization ceremonies, retries, and resume support. Retain basic run/evidence association needed for correct reporting; recorded provenance need not become a general tamper-verification framework.
- Live execution requires credentials, explicit approval of displayed intent, and a positive cost guardrail. Check accumulated reported cost before every request. This is a between-request guardrail, not a guarantee that an in-flight request cannot exceed the remaining amount.
- Stop on a failed paid request or exhausted cost guardrail; preserve evidence and reported usage obtained so far and mark unfinished runs incomplete. Do not automatically retry failed requests. Incomplete runs cannot produce a final coverage score.
- Keep Haiku usage and pricing handling truthful, including reported usage from interrupted streams and billed output used for thinking. Do not fabricate an unavailable reasoning-token breakdown or persist thinking content as audit evidence.
- Produce one Markdown report containing Workbook-row recall, programmatic coverage, Combined workbook coverage, Estimated run cost, execution/format limitations, and row-level explanations. The editable CSV and finding evidence remain supporting artifacts, not additional report projections.
- Preserve existing private artifacts without migrating, overwriting, or deleting them. The simplified workflow requires fresh runs. Keep private inputs and outputs excluded from version control.
- Preserve shared audit-client behavior required by the public application, including existing providers. Remove evaluator-only compatibility without redesigning or duplicating the shared client.
- Consolidate superseded specifications, progress narratives, and implementation records into concise current guidance where needed to meet the size target; earlier content remains in Git history. Preserve applicable agent instructions and existing ADR decisions.
- Measure added lines in the full branch diff from the merge-base with `main`, including deletions of branch-added material and all retained documentation. Do not game the target through minification, dense statements, hidden generated code, or removal of meaningful tests. If essential behavior prevents the target, report the measured gap and tradeoff.

## Testing Decisions

- Prefer the existing CLI seam as the primary test surface: exercise preview, run, edit CSV, and report through observable outputs and saved artifacts. No new public testing interface is required.
- Adapt the existing synthetic CLI lifecycle test to the smaller workflow, using a temporary directory, a synthetic workbook with the actual supported headers, local HTML, and the existing fake-provider seam. Verify exact report metrics and traceable row evidence without private data or paid requests.
- Assert externally visible behavior, not helper calls, internal ordering, private data structures, or exact incidental prose. Remove tests for deleted capabilities rather than keeping a second parallel workflow.
- Test source row inclusion and provenance, `source_element`, multiline CSV round-tripping, required eligibility, misses, multiple finding IDs, valid overlap between finding kinds, and rejected unknown or conflicting IDs. Include a case where an automatically populated blank classification cannot produce a report.
- Verify Workbook-row recall, programmatic coverage, and Combined workbook coverage against hand-calculated examples, preserving existing denominator behavior and handling an empty eligible denominator without inventing a score. Use the existing deterministic scoring tests as prior art; retain focused scorer tests only where they express distinct behavior more clearly than the CLI workflow.
- Verify preview and declined approval make no provider calls; credentials alone do not execute. Verify request failure and budget exhaustion retain available evidence and usage, make no automatic retries, and prevent final scoring of incomplete runs.
- Keep focused existing shared-client tests for thinking-stream final text, interrupted-stream usage, and non-evaluation provider behavior. These test an existing external-provider seam rather than creating another evaluator abstraction.
- Run the repository's applicable checks, verify no private evidence is staged, and report full added-line counts against `main`. Tests and specification publication do not authorize paid evaluation.

## Out of Scope

- Supporting arbitrary workbook layouts, extensive Excel validation or recovery, generated Excel review workbooks, or a review application.
- Automated AI eligibility or match reviewers, reviewer-adapter frameworks, and per-row approval/audit-trail metadata.
- Multiple-model comparison, ranking implementation, configurable providers for the evaluator, and changes to existing metric policy.
- Automatic location inference, automated full-row coverage judgment, required-subdefect modeling, and partial-credit scoring.
- Webpage capture, browser automation, HTTP provenance frameworks, persisted execution plans, automatic retries, and resumable execution.
- Migration or reporting compatibility for historical evaluation formats; deletion of existing private artifacts.
- Separate JSON or CSV report projections, unrelated public application changes, and changing the audit prompts to fit the evaluator.
- Performing a paid run as part of implementing or verifying this reduction.

## Further Notes

This specification supersedes earlier evaluation requirements only where they conflict with the agreed POC reduction. It retains review/scoring separation and Workbook-row recall policy from the existing ADRs; removing future reviewer machinery and ranking code does not replace those policies.

Inspection found 16 imported Reference defects in the current private artifacts. Their generated eligibility-workbook locations and approved-reference locations matched the imported values, which came from the source `element name` field. This motivates preserving the source label rather than generating a new location.

The agreed size target is fewer than 3,000 added lines for the whole branch change, not merely the evaluation implementation. The existing synthetic CLI workflow and fake-provider seam are the proposed highest practical test seam. Publication marks the work ready for implementation; this task changes the specification only and does not claim the reduction is implemented or verified.
