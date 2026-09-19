Status: ready-for-agent

## Problem Statement

The project needs a trustworthy way to compare how effectively different AI models perform the repository's accessibility-auditing role, especially whether smaller, less expensive models find nearly as many known accessibility problems as larger models. The mandated source of reference problems is the Pristine Accessibility Defect Report workbook, whose prose, locations, and recommendations are not standardized enough for direct automated scoring. The current audit pipeline also combines deterministic checks with AI judgment, filters some programmatically detectable defects out of model inputs, emits heterogeneous prompt responses, and produces a final CSV that drops some active prompt categories and applies extra filtering. Without a separate evaluation framework, a model comparison would conflate model performance with deterministic findings, missing evidence, post-processing, page drift, and subjective matching.

The immediate goal is not to prove that a small model is equivalent to a large model. It is to prove that the evaluation method can import the required workbook, identify which reference defects the AI model is responsible for finding, normalize raw audit findings without losing data, support reviewable one-to-one matching, calculate an exact repeatable score, and report efficacy and cost transparently. The first proof of concept will use GPT-5.6 Luna at medium reasoning against a frozen Pristine homepage snapshot.

## Solution

Build a private, CLI-only model-evaluation framework around the existing audit pipeline. The framework will preserve the workbook as the required source of truth while transforming its homepage rows into human-reviewed reference defects with explicit eligibility classifications. It will freeze and hash a Pristine homepage benchmark snapshot, run the existing programmatic and AI audit paths without changing prompts, normalize raw prompt responses into canonical audit findings, generate reviewable candidate matches, and calculate workbook-row recall from approved match decisions.

The deterministic scorer will remain separate from review. Human-reviewed files will initially implement the eligibility and match reviewer interfaces; future Astra-backed adapters can produce the same decisions without changing import, scoring, or reporting. Models will be ranked first by workbook-row recall over approved LLM-eligible rows and, only when recall is equal, by estimated audit cost. Programmatic coverage, combined workbook coverage, latency, token usage, malformed output, and unmatched findings will remain visible but will not alter model rank.

Private inputs and generated artifacts will stay outside version control. The committed repository will contain only the framework, schemas, documentation, versioned public pricing configuration, and synthetic tests. Live API execution will be impossible without an explicit live flag, a planned positive cost limit, an available key, and point-of-use live-run approval after the complete execution summary.

## User Stories

1. As an accessibility-audit researcher, I want to compare models against the mandated defect workbook, so that results satisfy the project's external reference-data requirement.
2. As an accessibility-audit researcher, I want the first proof of concept to validate the measurement method, so that a weak or strong Luna result is not confused with evaluator quality.
3. As a project lead, I want every scored result to trace back to a workbook source row, so that I can explain the benchmark to stakeholders.
4. As a benchmark curator, I want the workbook checksum recorded, so that an updated or substituted workbook cannot silently change results.
5. As a contributor, I want a clear error when the private workbook is absent, so that I know to obtain it from an authorized project source.
6. As a contributor, I want to override the default workbook location explicitly, so that local workflows are not tied to one machine layout.
7. As a data owner, I want the workbook excluded from version control, so that employer-provided information is not published without approval.
8. As a data owner, I want workbook-derived references, reviews, snapshots, runs, and reports excluded from version control, so that derived private information is protected too.
9. As a benchmark curator, I want each workbook row imported without semantic rewriting, so that the original evidence remains intact.
10. As a benchmark curator, I want each reference defect to retain its source sheet and row, so that normalization is auditable.
11. As a benchmark curator, I want each homepage and applicable Global row classified, so that no workbook row silently disappears.
12. As a benchmark curator, I want the allowed eligibility classifications validated, so that references consistently distinguish AI responsibility, programmatic responsibility, unavailable evidence, and ambiguity.
13. As an evaluator, I want LLM-eligible reference defects clearly separated from programmatic defects, so that models are scored only on work assigned to them.
14. As a project lead, I want unavailable-evidence rows reported with reasons, so that pipeline blind spots remain visible.
15. As a project lead, I want ambiguous rows excluded from the scoring denominator until approved, so that unresolved interpretation does not arbitrarily help or hurt a model.
16. As a comparison reviewer, I want eligibility proposals presented with workbook and pipeline evidence, so that I can approve classifications efficiently.
17. As a comparison reviewer, I want a private Excel review workbook, so that multiline evidence and decisions can be reviewed side by side.
18. As a comparison reviewer, I want accepted, rejected, and needs-review decisions, so that uncertainty is explicit.
19. As a comparison reviewer, I want reviewer identity, rationale, confidence, and timestamp retained, so that decisions have provenance.
20. As a future automation maintainer, I want human and model reviewers to satisfy the same interfaces, so that Astra can replace tedious review without changing the scorer.
21. As a future automation maintainer, I want eligibility review and match review to be separate interfaces, so that benchmark curation and per-run adjudication can evolve independently.
22. As a data owner, I want future Astra review to use the authorized API project without publishing inputs, so that automation does not weaken data privacy.
23. As an evaluator, I want a benchmark snapshot captured once from the Pristine homepage, so that every model sees identical page content.
24. As an evaluator, I want the snapshot URL, capture time, HTTP metadata, and SHA-256 recorded, so that the tested page state is identifiable.
25. As a project lead, I want the stakeholder assertion that Pristine has not changed since the workbook audit recorded with the snapshot, so that the temporal assumption is explicit.
26. As an evaluator, I want Global rows scored only for their homepage manifestation in this proof of concept, so that homepage evidence is not inflated into a site-wide claim.
27. As an evaluator, I want the existing programmatic audit run against the benchmark snapshot, so that deterministic workbook coverage and checker gaps are measured.
28. As an evaluator, I want programmatic findings excluded from the AI model score, so that model-independent results do not inflate similarity between models.
29. As a project lead, I want programmatic coverage reported separately, so that the value and gaps of deterministic checks are visible.
30. As a project lead, I want combined workbook coverage reported separately, so that I can see what the complete two-pass pipeline catches.
31. As an evaluator, I want the current prompts, filters, prompt order, and summary setting frozen, so that the proof of concept measures the current audit role rather than a redesigned prompt system.
32. As an evaluator, I want GPT-5.6 Luna called with medium reasoning and without inherited temperature sampling, so that the requested model configuration is explicit.
33. As an evaluator, I want all raw prompt responses saved, so that normalization and scoring can be audited later.
34. As an evaluator, I want every active prompt response normalized directly, so that categories omitted by the production CSV remain available for evaluation.
35. As an evaluator, I want malformed successful responses recorded rather than selectively retried, so that structured-output reliability is part of the observed run.
36. As an evaluator, I want each canonical audit finding to preserve its raw source, prompt, checklist, page, problem, location evidence, WCAG evidence, and parse status, so that comparison is explainable.
37. As a comparison reviewer, I want impossible finding/reference pairs removed deterministically, so that I do not review obviously incompatible matches.
38. As a comparison reviewer, I want plausible candidate pairs shown with evidence from both sides, so that matching decisions are efficient and defensible.
39. As an evaluator, I want a match to require compatible page scope, underlying accessibility failure, and location or element-group evidence, so that superficial wording similarity cannot earn credit.
40. As an evaluator, I want WCAG identifiers and fix recommendations treated as supporting evidence rather than exact-match requirements, so that equivalent findings with different labels can match.
41. As an evaluator, I want one-to-one matching enforced, so that one vague audit finding cannot claim several unrelated workbook rows.
42. As an evaluator, I want multi-element workbook rows treated as one scoring unit when they describe one grouped problem, so that the stakeholder-facing score remains row based.
43. As an evaluator, I want a row containing genuinely different required sub-defects credited only when all required parts match, so that partial detection is not overstated.
44. As an evaluator, I want identical approved normalized inputs to produce exactly the same score, so that scoring is deterministic.
45. As a project lead, I want workbook-row recall shown as caught rows, denominator, and percentage, so that model efficacy is easy to interpret.
46. As a project lead, I want estimated audit cost to be the only ranking tie-breaker, so that cheaper models win only when workbook-row recall is equal.
47. As a project lead, I want latency and token usage recorded but excluded from ranking, so that operational information does not override the agreed efficacy measure.
48. As a project lead, I want unmatched audit findings and structured-output failures reported without changing rank, so that model behavior remains visible without replacing the mandated metric.
49. As a budget owner, I want audit-model cost separated from evaluation-model cost, so that a future Astra reviewer does not distort the model-under-test comparison.
50. As a budget owner, I want total experiment cost reported separately, so that the full research expense remains visible.
51. As a budget owner, I want costs computed from API-reported token categories and a versioned price schedule, so that estimates can be reproduced after prices change.
52. As a budget owner, I want the unrounded estimated audit cost used for ties, so that display rounding cannot change rank.
53. As an operator, I want dry-run behavior by default even when an API key exists, so that environment configuration alone cannot spend money.
54. As an operator, I want live execution to require an explicit flag, so that spending is intentional.
55. As an operator, I want each summarized proof-of-concept run explicitly approved at execution time, so that approval covers a known model, snapshot, request set, configuration, and cost guardrail.
56. As an operator, I want a required maximum audit-cost guardrail, so that a live run stops before starting another request after exhausting its budget.
57. As an operator, I want bounded retries only for transient failures, so that recoverable provider errors do not automatically invalidate a run.
58. As an operator, I want every retry and any billed usage recorded, so that cost and reliability reports are complete.
59. As an evaluator, I want an exhausted transient failure to mark the run incomplete and unranked, so that infrastructure failure is not scored as model ignorance.
60. As an evaluator, I want successful malformed output to produce no usable findings for that prompt, so that model-format failure is represented honestly.
61. As an evaluator, I want end-to-end wall time and per-request duration recorded, so that latency can be analyzed without affecting rank.
62. As an evaluator, I want run manifests to contain content, configuration, code, prompt, parser, and pricing identities, so that only comparable runs are ranked together.
63. As an evaluator, I want incompatible benchmark versions rejected from ordinary comparison, so that changed inputs are not presented as model differences.
64. As a contributor, I want one CLI with prepare, audit, review, and report workflows, so that the evaluation lifecycle is discoverable.
65. As a contributor, I want the evaluation framework to reuse the production audit pipeline through an adapter, so that audit logic is not duplicated.
66. As a contributor, I want the scorer isolated from network and model dependencies, so that it is fast and deterministic to test.
67. As a reviewer, I want reports in JSON, CSV, and Markdown derived from one score object, so that machine, spreadsheet, and human views cannot disagree.
68. As a project lead, I want the homepage result labeled illustrative, so that three provisionally eligible rows are not used to claim broad model equivalence.
69. As a researcher, I want later benchmark expansion organized by page and template family, so that repetitive job pages do not overstate generalization.
70. As a maintainer, I want synthetic fixtures used in committed tests, so that CI never requires private workbook content.
71. As a maintainer, I want ordinary tests and CI to make no live provider calls, so that validation is free, safe, and repeatable.
72. As a maintainer, I want concise errors for missing approvals, incomplete runs, invalid decisions, checksum drift, and match conflicts, so that unsafe states cannot silently produce scores.

## Implementation Decisions

- The proof of concept is CLI-only. It will not add controls to the public website or audit API.
- A dedicated model-evaluation module will contain workbook import, benchmark preparation, canonical schemas, audit adaptation, normalization, review, matching, scoring, pricing, and reporting. A single evaluation entry point will expose `prepare`, `audit`, `review`, and `report` subcommands.
- The existing production pipeline remains the audit implementation. The evaluation module will call it through an adapter rather than copying audit logic.
- The external testing seam is the deterministic scorer: approved reference defects, canonical findings, programmatic findings, match decisions, and run metadata enter; one complete score object exits. All reports are projections of that object.
- Two new reviewer seams are required because two adapters are known: human-reviewed local files initially and model-backed review later. `EligibilityReviewer` handles benchmark eligibility decisions; `MatchReviewer` handles per-run match decisions. The scorer does not know which adapter produced an approved decision.
- Human review will use a private Excel workbook with separate Eligibility and Matches sheets. Reviewer adapters emit validated decisions with `accepted`, `rejected`, or `needs_review` state plus identity, rationale, confidence, and timestamp.
- The future Astra adapters will use the same reviewer interfaces and an internal shared OpenAI client. They are designed but disabled for the proof of concept. Workbook-derived data may be sent through the authorized API project, but may not be committed publicly without approval.
- The private source workbook remains at the repository root under its current name by default and is ignored by exact filename. A command-line override permits another local location. The importer validates a recorded SHA-256 and fails clearly on absence or drift.
- All private derived artifacts live under one ignored evaluation workspace partitioned into references, reviews, snapshots, runs, and reports. Only code, schemas, documentation, synthetic fixtures, and public pricing data are committed.
- `openpyxl` is added as a runtime dependency for workbook import and private review workbooks. `pytest` is added as a development dependency.
- The Pristine homepage is captured as raw HTML because that is the production pipeline's input. The capture is immutable and accompanied by source URL, retrieval time, HTTP metadata, SHA-256, and a note that stakeholders report no change since the workbook audit.
- The existing DAT Vision Aid HTML fixture is unrelated to the workbook and is never used for workbook-based scoring.
- The proof of concept includes workbook rows scoped as Home and Global on the Pristine homepage. Global rows are labeled as global claims supported by homepage evidence and are not multiplied across pages.
- Every source row becomes one reviewed reference record. Raw text and provenance are retained. Normalized fields include the canonical problem, location or element group, WCAG evidence, eligibility classification, rationale, approval state, and any required sub-defects.
- Eligibility classifications are exactly `llm_eligible`, `programmatic`, `unavailable_evidence`, and `ambiguous`. Only approved `llm_eligible` rows enter workbook-row recall. All classifications remain present in coverage reports.
- The programmatic audit runs first. Its findings are normalized and matched to reference defects through the same evidence-based review process. A programmatic classification does not imply that the checker succeeded; uncovered checker responsibilities are reported as gaps.
- The AI audit preserves current filtering, prompt order, sequential execution, disabled summary prompts, and the 8,192-token output limit. The proof of concept uses GPT-5.6 Luna with medium reasoning, Chat Completions, and no temperature parameter.
- Current audit prompts are unchanged and versioned by content hash. Structured-output enforcement is not enabled in the proof of concept because it would change the audited conditions.
- Raw prompt outputs, request metadata, usage, durations, stop reasons, and failures are saved before normalization.
- Canonical audit findings are built directly from raw prompt responses using fixed per-prompt parsers. The production final CSV, heuristic false-positive suppression, and model-based deduplication are not scoring inputs.
- A canonical audit finding preserves run and model identity, prompt and checklist, page, problem family and statement, element and location evidence, WCAG evidence, raw source finding, and parse status.
- Candidate generation may remove only hard incompatibilities such as different pages or incompatible evidence categories. It does not award matches.
- An approved match requires compatible page or declared scope, the same underlying accessibility failure, and compatible location, element, or element group. WCAG identifiers and remediation wording are supporting evidence.
- Matching is one-to-one at the normalized defect level. Conflicting accepted decisions fail validation rather than being resolved silently.
- One workbook source row remains one headline scoring point. A grouped row is caught when the same grouped defect is identified at the compatible location. A row with distinct required sub-defects is caught only when all required parts are approved as matched.
- The scorer is deterministic and performs no model or network call. Identical normalized inputs and approved decisions produce an identical score object.
- The primary ranking metric is workbook-row recall over approved LLM-eligible rows. Estimated audit cost is the only tie-breaker. No weighted composite score is produced.
- Programmatic coverage, combined workbook coverage, unmatched findings, parse failures, token usage, and latency are reported separately and do not affect model rank.
- Cost reporting separates audit cost, evaluation cost, and total experiment cost. Only audit cost affects ties. Costs use API-reported token categories and a versioned public price schedule; estimates are not represented as invoice totals.
- Latency reporting includes end-to-end audit wall time, per-request durations, and their sum. Latency never affects ranking.
- Evaluation execution is dry by default. An API key in the environment is insufficient to trigger a request. Live execution requires an explicit live flag and a maximum audit-cost limit.
- The proof-of-concept runner permits at most two additional attempts for timeouts, rate limits, and server errors, using bounded exponential backoff. Authentication, invalid-request, parsing, and successful malformed-response failures are not retried.
- Every attempt is recorded. Transient failures exhausted after retries make the run incomplete and unranked. A successful malformed response remains part of the run, contributes no usable findings for that prompt, and is reported as a format failure.
- A run manifest records workbook and snapshot hashes, reference-set version, source-control commit and dirty state, prompt and parser hashes, filters, summaries, model, reasoning effort, endpoint, output limit, retry policy, usage, price-schedule version, timestamps, and run ID.
- Ordinary comparison rejects runs whose snapshot, reference set, prompts, or eligibility set differ. Cross-version analysis must be requested explicitly and labeled accordingly.
- Reports are emitted as JSON, CSV, and Markdown from one score object. The row-level view exposes eligibility, rationale, programmatic outcome, model match, evidence, and final disposition for every in-scope workbook row.
- The proof of concept proceeds through gates: implementation and tests; snapshot and reference preparation; human eligibility approval; evaluation-run planning; point-of-use live-run approval; Luna audit; human match approval; final report.
- One live-run approval covers the complete displayed execution summary, including policy-compliant automatic retries. A materially different configuration or separate rerun requires a newly planned evaluation run and new approval.
- The homepage result is illustrative because the provisional inventory contains only three clearly LLM-eligible rows out of sixteen in-scope rows. Benchmark expansion is required before any small-versus-large model claim.

## Testing Decisions

- Tests assert external behavior at module interfaces, not private helper functions or implementation order. The principal scoring seam is the deterministic scorer's structured inputs and returned score object because it exercises eligibility, one-to-one matching, ranking data, coverage, and report inputs at the highest stable seam; the complete operator lifecycle is exercised through the evaluation CLI.
- Workbook-import tests use synthetic Excel fixtures and assert provenance retention, homepage filtering, source-row identity, checksum validation, exact allowed eligibility states, and useful missing-file or drift errors.
- Snapshot tests use local HTTP fakes or saved synthetic responses and assert immutable content, provenance fields, and hashing without accessing the live Pristine site.
- Audit-adapter tests replace the production pipeline with a fake at its existing callable seam. They assert frozen configuration, raw-result preservation, manifest metadata, dry-run safety, live-flag requirements, cost-limit behavior, and retry classification without provider calls.
- Per-prompt normalization is tested through the normalization module's public interface using synthetic raw responses for every active non-summary prompt. Tests include valid arrays and objects, fenced JSON, empty results, malformed successful output, unknown prompt types, and all six categories omitted by the production CSV.
- Reviewer-contract tests run the same decision examples through human-file and fake-model adapters. They assert identical validated outputs, required provenance, allowed states, and rejection of incomplete decisions.
- Candidate and match tests assert that hard incompatibilities are removed, plausible pairs remain reviewable, one-to-one conflicts fail validation, grouped rows receive one point, and distinct required sub-defects require complete coverage.
- Scorer tests assert exact repeatability, correct denominators, binary row credit, separation of programmatic and AI coverage, exclusion of ambiguous and unavailable rows from LLM recall, and cost-only tie-breaking.
- Cost tests use fixed synthetic usage and price schedules. They assert input, cached-input, output, retry, audit, evaluation, and total experiment calculations without depending on current external pricing.
- Failure-policy tests distinguish transient transport failures, exhausted retries, authentication errors, invalid requests, and malformed successful responses. They assert that incomplete runs cannot be ranked.
- Reporting tests construct one score object and assert that JSON, CSV, and Markdown totals and row dispositions agree.
- CLI tests exercise prepare, audit, review, and report workflows against a temporary private workspace with fake adapters. They assert safe defaults, explicit live requirements, and actionable errors.
- Regression fixtures contain no employer workbook text, Pristine content, secrets, or provider responses copied from live runs.
- No ordinary test or CI task may require an API key, access the public internet, or spend money.
- Prior art is the repository's network-free API regression style and CI dry-run smoke path; the evaluation suite extends that philosophy with pytest and synthetic fixtures.

## Out of Scope

- Claiming that GPT-5.6 Luna performs as well as a larger model based on the homepage proof of concept.
- Ranking multiple models during the initial no-spend implementation and eligibility-review stage.
- Repeated audit runs, statistical variance analysis, confidence intervals, or stability scoring.
- Using precision, F1, latency, token count, or unmatched-finding count to rank models.
- Automatically accepting Astra eligibility or match decisions during the proof of concept.
- Calling Astra as a reviewer before the human-reviewed process has supplied calibration examples.
- Publishing the source workbook, normalized private reference data, Pristine snapshot, review decisions, raw runs, or reports to Git.
- Redesigning production prompts, filters, payload extractors, programmatic rules, final CSV generation, false-positive suppression, or deduplication.
- Enforcing a new unified structured-output schema on the audit model during the proof of concept.
- Adding evaluation features to the public website or HTTP API.
- Browser rendering, JavaScript execution, screenshots, interactive-state testing, or Chrome-plus-JAWS automation.
- Treating a current live capture as independently proven byte-identical to the September audit state; the benchmark instead records the stakeholder-supported assumption.
- Treating Global rows as verified on every site page.
- Expanding immediately to all seventeen workbook URLs or using repeated job-page rows to claim generalization.
- Computing an exact invoiced dollar amount or accounting for private contractual discounts unavailable from API usage metadata.
- Making a live provider request before eligibility approval, evaluation-run planning, point-of-use approval, and a positive cost limit.

## Further Notes

- The provisional homepage inventory contains sixteen workbook rows: five programmatic, three LLM-eligible, six unavailable to the current pipeline, and two ambiguous. These are draft classifications for human review, not accepted benchmark truth.
- Provisional LLM-eligible examples include decorative-image alt judgment and heading-quality problems. Programmatic examples include missing landmarks, missing skip navigation, actionable empty alt, and multiple H1 elements. Unavailable-evidence examples include visual list semantics, styled text that should be headings, carousel controls, Lottie animation, decorative literal glyphs, and media operability. Ambiguities include fragmented adjacent links and a workbook alt-text claim that may conflict with the page.
- The existing committed HTML fixture represents DAT Vision Aid, not Pristine, and cannot be used for this benchmark.
- The workbook is the mandatory provenance source, but approved normalization may mark rows unavailable or ambiguous and may represent distinct required sub-defects. These transformations must remain traceable and reviewable.
- The first implementation milestone ends at the eligibility-review gate and incurs no API cost. The cost limit for the first live Luna run will be selected while planning the evaluation run, whose summary exposes the request set and estimated usage.
- Future benchmark expansion should sample distinct pages and template families rather than random rows because repeated job-page patterns dominate the workbook.
