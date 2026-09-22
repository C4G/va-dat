# Streamline the Private Evaluation CLI Workflow

Status: resolved

## Problem Statement

The private model-evaluation framework has the required safety and reproducibility controls, but its operator workflow is harder than necessary. A live run currently requires copying an authorization digest from a dry run into a later command even though the digest does not establish identity or provide meaningful consent. Match-review imports for audit findings and programmatic findings overwrite the same decision file, and final reporting requires manually constructing a report-bundle JSON document. The resulting walkthrough includes file renames and raw Python that should not be part of an ordinary evaluation run.

The framework must remain dry by default, preserve its cost guardrail, verify that planned evidence has not drifted, and obtain explicit live-run approval. Those protections should be expressed through a clear point-of-use confirmation and one run-oriented CLI workflow rather than opaque copy-and-paste tokens.

## Solution

Make the evaluation run the operator-facing unit of work. Planning creates a unique run directory, records the maximum audit cost, freezes the approved reference set, and prints the billable intent. Live execution receives that run directory, revalidates its internal identities, prints the complete execution summary, and asks an interactive operator to type `yes`. Automation may deliberately replace the prompt with `--auto-approve`, but it receives the same summary and all other spending gates remain mandatory.

Use the run identifier to organize separate audit and programmatic match-review artifacts. Let reporting discover its verified inputs from the run directory and associated run-scoped reviews. Remove the authorization-digest, plan-path, and report-bundle interfaces so the normal workflow requires neither manual renaming nor custom Python.

## User Stories

1. As an evaluation operator, I want a dry run to remain the default, so that an available API key cannot spend money by itself.
2. As an evaluation operator, I want live execution to retain an explicit `--live` flag, so that billable intent is visible in the command.
3. As a budget owner, I want every evaluation run planned with a positive maximum audit cost, so that spending has a defined upper guardrail.
4. As a budget owner, I want the planned cost guardrail frozen with the evaluation run, so that it cannot drift at execution time.
5. As an evaluation operator, I want the live command to reuse the saved cost guardrail, so that I do not need to repeat matching values across commands.
6. As an evaluation operator, I want the complete live execution summary shown immediately before approval, so that I understand what will run and what it may cost.
7. As an evaluation operator, I want the summary to identify the model, endpoint, and reasoning effort, so that model configuration is visible before spending.
8. As an evaluation operator, I want the summary to identify the benchmark snapshot and approved reference set, so that I know which evidence will be evaluated.
9. As an evaluation operator, I want the summary to list the prompt request set and request count, so that approval covers known work.
10. As an evaluation operator, I want the summary to show estimated input usage, retry policy, maximum audit cost, and destination, so that operational consequences are explicit.
11. As an evaluation operator, I want to approve a live run by typing `yes`, so that approval is understandable without interpreting a digest.
12. As an evaluation operator, I want any response other than an exact case-insensitive `yes` to abort, so that ambiguous input cannot start a provider request.
13. As an evaluation operator, I want end-of-input to abort before a provider client is created, so that a missing response cannot be treated as consent.
14. As an evaluation operator, I want interactive approval to require a terminal, so that scripts cannot silently pipe confirmation into the prompt.
15. As an automation author, I want an explicit `--auto-approve` option, so that deliberate non-interactive execution is supported.
16. As an automation author, I want `--auto-approve` accepted only for live execution, so that the option has one clear meaning.
17. As an automation author, I want the full execution summary printed even when approval is automatic, so that logs retain the approved intent.
18. As an auditor, I want the live manifest to record whether approval was interactive or automatic and when it occurred, so that approval provenance is visible without claiming a person's identity.
19. As an evaluation operator, I want live execution to require an API key in addition to approval, so that confirmation alone cannot create a request.
20. As a maintainer, I want internal plan and evidence identities retained, so that modified snapshots, prompts, pricing, eligibility decisions, or configurations still fail closed.
21. As an evaluation operator, I do not want to copy an authorization digest between commands, so that the workflow reflects meaningful consent rather than token matching.
22. As an evaluation operator, I want every planned evaluation run to receive a unique run directory, so that repeated experiments do not collide.
23. As an auditor, I want each evaluation run to freeze the approved reference set it used, so that later curation cannot make old evidence unreportable.
24. As an auditor, I want an evaluation run to retain its immutable model, benchmark, prompt, parser, pricing, and reference identities, so that reports remain reproducible.
25. As an evaluation operator, I want execution to refuse an occupied live-output destination, so that earlier evidence is never overwritten.
26. As an evaluation operator, I want a rerun to require a fresh evaluation run, so that each approval and result remain independently traceable.
27. As a comparison reviewer, I want audit findings and programmatic findings reviewed as distinct kinds, so that their match decisions cannot overwrite one another.
28. As a comparison reviewer, I want match workbooks and validated match decisions scoped by run identifier, so that reviews from different evaluations cannot collide.
29. As a comparison reviewer, I want the review command to infer conventional inputs and outputs from a run directory and review kind, so that ordinary review does not require repeated paths.
30. As a comparison reviewer, I want explicit input and output overrides retained for unusual review cases, so that the simplified workflow does not prevent expert recovery or investigation.
31. As an evaluation operator, I want the report command to accept one run directory, so that I do not manually enumerate scoring inputs.
32. As an evaluation operator, I want reporting to discover the frozen reference set, audit findings, programmatic findings, both match-decision sets, and live manifest, so that the correct evidence is assembled consistently.
33. As an evaluation operator, I want format failures read from the live manifest automatically, so that I do not duplicate run metadata in another document.
34. As an evaluation operator, I want missing or unresolved review artifacts reported with an actionable next command, so that the workflow explains how to proceed.
35. As an evaluation operator, I want JSON, CSV, and Markdown reports produced without a report bundle, so that no raw Python is required.
36. As a maintainer, I want obsolete authorization, plan-path, and report-bundle options removed immediately, so that the pre-proof-of-concept CLI has one supported workflow.
37. As a maintainer, I want the broader evaluation documentation updated to use live-run approval terminology, so that the design no longer implies that a digest authenticates an operator.
38. As a maintainer, I want the synthetic workflow to cover both audit and programmatic review decisions, so that the tested lifecycle matches the real reporting requirements.
39. As a project lead, I want these ergonomics changes kept separate from the actual Luna proof of concept, so that improving the CLI does not falsely mark the live evaluation complete.

## Implementation Decisions

- An evaluation run is the primary CLI concept joining one saved audit plan with its live evidence, reviewed match decisions, and reports.
- Dry audit planning automatically creates a unique run directory and prints its location for subsequent commands.
- The maximum audit-cost guardrail is mandatory during planning, validated as a positive decimal, and saved as part of the immutable plan.
- Live execution accepts the run directory rather than a separate plan path. It reads the saved guardrail and does not accept a replacement live value.
- Live execution continues to require the explicit live flag and an available OpenAI API key.
- The user-facing authorization digest, authorization option, one-use authorization receipt, authorized-plan duplicate field, and authorization-digest manifest field are removed.
- Internal content identities remain. Live execution revalidates the plan itself, frozen configuration, benchmark snapshot, approved eligibility decisions, prompt content, parser identity, pricing identity, and cost guardrail before any provider request.
- The complete billable-intent summary is rendered at live invocation before client construction. It includes model configuration, benchmark and reference identities, prompt names and count, estimated input tokens, retry policy, maximum audit cost, run directory, and approval mode.
- Interactive approval accepts only trimmed, case-insensitive `yes`. Any other response, end-of-input, or unavailable interactive terminal exits nonzero without constructing the provider client or making a request.
- Automatic approval is enabled only by an explicit `--auto-approve` option used together with live execution. It skips input but not summary rendering or any other gate.
- The live manifest records approval mode as `interactive` or `auto` plus an approval timestamp. It does not represent API-key presence as approval and does not claim a reviewer identity.
- Planning freezes a private copy of the approved reference set as run evidence. Scoring and reporting use that copy instead of the mutable current reference set.
- Live output paths are write-once. Existing live evidence causes an actionable failure that directs the operator to create a new evaluation run.
- Run-scoped match review distinguishes exactly two finding kinds: audit and programmatic. Each kind has a distinct workbook and validated match-decision artifact under a review partition keyed by run identifier.
- The review workflow accepts a run directory and finding kind, infers the conventional frozen reference set, findings input, review workbook, and match-decision output, and retains explicit overrides for exceptional workflows.
- Import mode continues to validate reviewer provenance, decision states, compatible evidence, required sub-defects, and one-to-one matching before writing decisions.
- Reporting accepts a run directory as its ordinary and only operator-facing input selector. It discovers all score inputs and obtains format failures directly from the live manifest.
- The report-bundle input and bundle-file format are removed from the CLI rather than retained as an advanced compatibility path. Tests and unconventional integrations can call the deterministic scorer interface directly.
- The obsolete plan-path option is removed because the plan has a conventional location within its evaluation run.
- Report formats, scoring rules, retry policy, prompt content, model configuration, normalization, matching semantics, and ranking behavior do not change.
- Documentation and the parent model-evaluation specification are revised to replace authorization-digest instructions with live-run approval and the run-oriented commands.
- Existing resolved implementation tickets remain resolved after their acceptance criteria and comments are made accurate. The operational Luna proof-of-concept ticket remains open until its private preparation, live execution, reviews, and final reports are actually completed.
- The domain glossary defines evaluation run and live-run approval. No architecture decision record is required because this pre-proof-of-concept interface change is straightforward to reverse and is not an architectural lock-in.

## Testing Decisions

- Tests assert externally visible behavior rather than private confirmation helpers, naming functions, or filesystem implementation order.
- The primary test seam is the evaluation CLI entry point exercised through a complete synthetic lifecycle in a temporary private workspace with a fake provider.
- The end-to-end CLI test plans a uniquely identified evaluation run, verifies the frozen reference set and saved cost limit, executes it with controlled approval, reviews audit findings, reviews programmatic findings, and generates all three reports without a report bundle.
- Focused CLI tests verify interactive acceptance, case and whitespace handling, rejection, end-of-input, unavailable terminal behavior, and automatic approval.
- Approval failure tests assert that no provider client is constructed, no request is made, and no live artifacts are created.
- Safety tests verify that the live flag, API key, saved positive cost guardrail, exact plan integrity, and frozen identities remain mandatory.
- Overwrite tests execute against occupied live destinations and assert that existing bytes remain unchanged and the command directs the operator to create a fresh evaluation run.
- Review tests prove that audit and programmatic decision outputs are distinct, run-scoped, validated, discoverable, and both required for final reporting.
- Reporting tests invoke only the run-directory workflow and verify automatic discovery of the frozen reference set, both findings collections, both match-decision sets, manifest metadata, and format failures.
- Parser tests verify that obsolete authorization, plan-path, and report-bundle options are rejected rather than silently ignored.
- Lower-level audit-executor tests remain for retry classification, cost accumulation, exhausted budgets, malformed successful responses, and immediate attempt persistence where those behaviors are clearer below the CLI seam.
- Existing synthetic evaluation CLI tests are the prior art. They will be reshaped around the run-oriented lifecycle rather than supplemented with a second parallel workflow.
- No test uses the private workbook, live Pristine content, a real API key, public network access, or billable provider calls.

## Out of Scope

- Performing the real Luna homepage proof of concept or checking off its operational acceptance criteria.
- Changing the GPT-5.6 Luna model, medium reasoning effort, endpoint, output limit, prompt order, filters, summaries, or retry policy.
- Changing eligibility classifications, match semantics, scoring rules, ranking metrics, report contents, or the illustrative-result limitation.
- Adding Astra-backed eligibility or match reviewers.
- Adding a web interface or public API for evaluation runs.
- Supporting report bundles as a hidden, deprecated, or advanced CLI feature.
- Authenticating the human who types `yes` or treating live-run approval as a cryptographic signature.
- Allowing approval to bypass API credentials, integrity checks, the cost guardrail, or overwrite protection.
- Migrating previously completed private evaluation artifacts; no real live proof-of-concept run exists yet.

## Further Notes

- The authorization digest was a confirmation checksum, not an identity proof. Point-of-use approval provides clearer operator intent while internal hashes continue to provide drift detection.
- A provider API key is a credential, not live-run approval. Its presence never triggers spending without the live flag and approval.
- A separate invocation, including one using automatic approval, constitutes a new live-run approval. A materially different configuration requires a newly planned evaluation run.
- The run directory is the operator's handle for live execution, review, and reporting even though private artifacts may remain partitioned by responsibility within the evaluation workspace.
- The existing private workbook and its SHA-256 remain unchanged by this feature.

## Comments

Implemented in `2448042` and review-hardened in `6a1e6c0`. Verified by the
synthetic CLI lifecycle, focused approval and identity-drift tests, lower-level
retry and cost tests, compilation, and the full network-free pytest suite. The
operational Luna proof of concept remains open and no provider request was made.


## Haiku retarget clarification (2026-09-22)

The Luna-specific target and credential details above are historical. They are
superseded by `.scratch/anthropic-evaluation-retarget/spec.md`; benchmark,
review, scoring, and safety requirements remain authoritative.
