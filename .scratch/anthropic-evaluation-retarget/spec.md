Status: ready-for-agent

## Problem Statement

The private accessibility-audit evaluation workflow assumes that its API credential is an OpenAI key and freezes GPT-5.6 Luna at medium reasoning into every planned evaluation run. The available credential is instead an Anthropic key. As a result, the evaluator cannot execute the intended proof of concept even though the repository's shared audit path already supports Anthropic and the public application already defaults to Claude Haiku 4.5.

The evaluator must be retargeted without turning this focused proof of concept into a general provider-selection system. The replacement must preserve the existing benchmark snapshot, audit prompts, review workflow, deterministic scoring, workbook-row recall ranking, cost reporting, write-once evaluation artifacts, and live-run approval protections. Historical Luna evaluation runs must remain immutable and readable.

## Solution

Retarget the private evaluation workflow from GPT-5.6 Luna to the pinned Anthropic model `claude-haiku-4-5-20251001`. Configure every audit request with manual extended thinking capped at 16,000 tokens and a total output cap of 24,192 tokens, leaving up to the existing 8,192-token allowance for the final audit JSON when the full thinking budget is used. Omit temperature and use Anthropic's Messages API.

Extend the existing shared audit-client boundary only as much as required to send this fixed thinking configuration and consume the streaming response required by the larger output cap. Return the same normalized final-text and usage contract that the evaluator already consumes. Thinking and redacted-thinking blocks will not become evaluation evidence or be persisted; aggregate provider usage will still be retained and priced.

The evaluation CLI will resolve `ANTHROPIC_API_KEY`, display the exact pinned model, thinking budget, total output cap, endpoint, pricing identity, and cost guardrail in its plan and approval summaries, and continue to be dry by default. The implementation will generate a fresh dry-run plan under a new evaluation run identity. It will not execute a paid live audit.

## User Stories

1. As an evaluation operator, I want the private evaluator to use my Anthropic credential, so that I can continue the proof of concept with the credential I was actually issued.
2. As an evaluation operator, I want a missing credential error to name `ANTHROPIC_API_KEY`, so that setup instructions do not send me toward the wrong provider.
3. As an evaluator, I want the audit model pinned to `claude-haiku-4-5-20251001`, so that a moving provider alias cannot silently change an evaluation run.
4. As an evaluator, I want the provider recorded as Anthropic, so that the run manifest accurately identifies the service that generated each audit finding.
5. As an evaluator, I want the endpoint recorded as Anthropic Messages, so that the request protocol is reproducible.
6. As an evaluator, I want Haiku extended thinking enabled, so that the low-cost model has additional reasoning capacity for accessibility judgments.
7. As an evaluator, I want the thinking budget fixed at 16,000 tokens, so that every request in the evaluation run has the same reproducible ceiling.
8. As an evaluator, I want the total output cap fixed at 24,192 tokens, so that a request can use its thinking budget without reducing the prior 8,192-token final-response allowance.
9. As an evaluator, I want temperature omitted while thinking is enabled, so that the request satisfies Anthropic's supported contract.
10. As an evaluation operator, I want the exact thinking and output ceilings shown before execution, so that the potential billed usage is visible.
11. As a budget owner, I want Haiku input and output usage priced from a versioned public price schedule, so that estimated run cost remains reproducible.
12. As a budget owner, I want all billed output tokens included in estimated run cost, including tokens used for thinking, so that cost is not understated.
13. As a budget owner, I want aggregate Anthropic usage preserved without inventing a reasoning-token breakdown that the response does not supply, so that reports distinguish measured values from unavailable detail.
14. As an evaluation operator, I want streaming handled internally by the audit client, so that I receive the same final audit result contract as before.
15. As an evaluator, I want streamed text blocks assembled in provider order, so that the final audit JSON can be normalized correctly.
16. As an evaluator, I want provider stop reasons and aggregate usage retained after streaming, so that format failures, truncation, and cost remain reviewable.
17. As a data owner, I want thinking and redacted-thinking blocks discarded rather than stored, so that internal reasoning does not become benchmark evidence or a new private artifact class.
18. As a comparison reviewer, I want only the model's final audit text normalized into canonical audit findings, so that the review contract remains unchanged.
19. As a comparison reviewer, I want malformed or missing final text handled by the existing normalization policy, so that thinking support does not conceal structured-output failure.
20. As an evaluator, I want the benchmark snapshot, prompts, filters, prompt order, and disabled summaries preserved, so that the provider retarget is the material experimental change.
21. As an evaluator, I want workbook-row recall to remain the primary ranking metric, so that changing providers does not change the definition of model performance.
22. As an evaluator, I want estimated run cost to remain only the tie-breaker, so that the higher per-token price of Haiku does not silently redefine model quality.
23. As an operator, I want the evaluation to remain dry by default even when `ANTHROPIC_API_KEY` exists, so that environment configuration alone cannot spend money.
24. As an operator, I want live execution to retain its explicit flag, positive cost guardrail, and point-of-use live-run approval, so that the provider change cannot bypass spending controls.
25. As an operator, I want this change to create a fresh evaluation run plan, so that its provider, model, thinking, output, and pricing identities are internally consistent.
26. As an operator, I want the fresh plan to remain unexecuted, so that I can review it before authorizing a paid run.
27. As an evaluator, I want the earlier failed Luna run preserved, so that the historical authentication failure remains auditable.
28. As an evaluator, I want the prepared but unexecuted Luna replacement plan preserved and marked as superseded or abandoned, so that immutable run history is not rewritten.
29. As an evaluator, I want old Luna artifacts to remain loadable for reporting and review where supported, so that current configuration changes do not corrupt historical evidence.
30. As an evaluator, I want an old Luna plan rejected for new live execution after the retarget, so that a stale plan cannot run under Haiku credentials or pricing.
31. As a maintainer, I want the public web application and HTTP API left unchanged, so that an evaluator-only retarget does not disturb existing multi-provider behavior.
32. As a maintainer, I want the existing audit-client interface extended rather than duplicated, so that Anthropic request and usage handling remain centralized.
33. As a maintainer, I want thinking support represented explicitly rather than disguised as OpenAI `reasoning_effort`, so that provider-specific semantics remain truthful.
34. As a maintainer, I want streaming enabled only where the configured Anthropic request requires it, so that unrelated audit calls retain their current behavior.
35. As a maintainer, I want existing non-thinking Anthropic calls to keep working, so that the focused evaluator change does not regress production audits.
36. As a maintainer, I want existing OpenAI and Gemini client behavior to remain unchanged, so that this retarget has a narrow regression surface.
37. As a maintainer, I want tests to use fake provider responses, so that verification never requires a credential, network access, or paid tokens.
38. As a maintainer, I want documentation to identify Haiku as the current proof-of-concept target, so that operators do not follow obsolete Luna instructions.
39. As a maintainer, I want historical Luna implementation records retained with supersession notes rather than rewritten, so that the issue tracker remains truthful.
40. As a future evaluator, I want the model identifier and pricing isolated in the existing frozen configuration and price schedule, so that a later retirement can be handled without redesigning the framework.

## Implementation Decisions

- This is a fixed-target retarget of the private evaluation workflow, not a general provider-selection feature.
- The pinned model is `claude-haiku-4-5-20251001`; the moving `claude-haiku-4-5` alias will not be used for an evaluation run.
- The request protocol is Anthropic Messages and the credential environment variable is `ANTHROPIC_API_KEY`.
- Manual extended thinking is enabled with `budget_tokens` set to 16,000. Haiku does not support adaptive thinking or an OpenAI-style `medium` reasoning setting.
- The request's `max_tokens` value is 24,192. Thinking and final text share this provider limit; the selected value preserves up to 8,192 tokens for final text when the full thinking budget is consumed.
- Temperature, `top_k`, and `top_p` are omitted from thinking-enabled requests.
- Thinking configuration is modeled explicitly in the shared audit request configuration. It will not overload the OpenAI-specific `reasoning_effort` field.
- The shared audit client gains the minimum streaming behavior required for this Anthropic configuration. It assembles final text, captures the terminal stop reason and usage, and returns the existing provider-neutral audit result.
- Streaming is not introduced as a new public evaluation abstraction. It remains an internal transport detail selected by the Anthropic request requirements.
- Only final text blocks enter normalization. Thinking, signatures, and redacted-thinking blocks are neither returned as audit text nor persisted as raw evaluation evidence.
- Aggregate provider output usage is authoritative for billing. The implementation will not estimate or fabricate a separate Anthropic reasoning-token count.
- Existing usage and reporting schemas will be changed only where needed to avoid presenting unavailable Anthropic reasoning detail as a measured zero.
- Haiku pricing is added to the versioned price schedule using the official direct-API input and output rates current when the schedule is updated. Pricing source and effective date remain recorded.
- Prompt caching and Batch API discounts are not enabled. Their prices may be represented only if the existing schedule requires complete model metadata.
- The frozen evaluation configuration, pricing identity, and resulting benchmark identity change. A new evaluation run is therefore mandatory.
- Previous run directories are immutable. The failed Luna run and the unexecuted Luna replacement plan will not be edited, deleted, or repurposed.
- The approved reference set and benchmark snapshot may be reused because the provider retarget does not change their content.
- Programmatic match decisions may be carried into the fresh run only through the existing row-for-row semantic verification process because run-scoped identifiers change.
- The operator log will append the model-selection rationale, final request configuration, superseded Luna plan status, and fresh dry-run identifier. Historical entries will remain intact.
- Normative evaluation documentation and the currently open operational ticket will be updated for Haiku. Resolved Luna tickets and superseded specifications will receive historical clarification rather than retroactive rewriting.
- Public application behavior is unchanged because it already supports Anthropic and already defaults to the pinned Haiku model.
- The implementation ends after generating and verifying a fresh dry-run plan. It must not make a live Anthropic request.
- No new domain glossary term or ADR is required. The existing concepts of evaluation run, estimated run cost, live-run approval, audit finding, and benchmark snapshot cover the change, while the fixed model target remains a reversible specification decision.

## Testing Decisions

- Tests will assert observable request, result, plan, and safety behavior rather than private helper structure.
- Two existing high-level seams are sufficient: the shared audit client's public request/result boundary and the evaluation CLI's dry-run plan boundary. No new test-only seam will be introduced.
- At the audit-client seam, a fake Anthropic stream will verify the pinned model, Messages request shape, 16,000-token thinking budget, 24,192-token total cap, omission of sampling parameters, ordered final-text assembly, terminal stop reason, and aggregate usage.
- At the same seam, mixed thinking and text blocks will verify that only final text is exposed as audit output, while thinking-only or truncated responses produce the existing empty or malformed final-output behavior.
- Existing plain Anthropic tests will remain and prove that non-thinking requests do not accidentally acquire thinking or streaming behavior.
- Existing OpenAI and Gemini request-shape tests will remain unchanged and serve as regression coverage for the provider-specific branch.
- At the evaluation CLI seam, a dry-run test will verify that the manifest and human-readable summary contain the Anthropic provider, pinned model, Messages endpoint, enabled thinking budget, total output cap, omitted temperature, and new pricing identity.
- CLI tests will verify that `ANTHROPIC_API_KEY` is required only for live execution, that an OpenAI-named key is not accepted as the required Anthropic credential, and that dry-run planning requires no credential.
- Safety tests will verify that the explicit live flag, positive cost guardrail, and live-run approval remain mandatory and that no fake or real provider call occurs during the requested dry run.
- Historical-plan tests will verify that an old Luna plan remains readable where historical loading permits but is rejected for execution under the new frozen configuration.
- Pricing tests will calculate Haiku input and aggregate output costs from fixed synthetic usage, including output usage attributable to thinking, without depending on live provider pricing.
- Reporting tests will verify that unavailable provider-specific reasoning detail is not mislabeled as an API-reported zero while total billed output remains correct.
- Normalization and scoring tests should remain provider-neutral. Existing tests for canonical audit findings, malformed responses, deterministic workbook-row recall, and cost-only tie-breaking are prior art and should pass without behavioral changes.
- The complete focused regression suite will cover audit requests, evaluation audit planning/execution policy, evaluation CLI behavior, pricing, reporting, and normalization. No test may access the internet or spend money.
- A good acceptance test demonstrates the complete dry-run behavior through the CLI with fake provider boundaries: it produces a fresh Haiku plan with the exact frozen configuration and no network call.

## Out of Scope

- Supporting runtime selection between OpenAI, Anthropic, Gemini, or arbitrary providers in the private evaluator.
- Changing the public website, public HTTP API, or their existing Haiku default.
- Claiming that Claude Haiku 4.5 is officially equivalent to GPT-5.6 Luna at medium reasoning.
- Mapping Anthropic thinking budgets to OpenAI reasoning-effort labels.
- Adaptive thinking, dynamic thinking budgets, per-prompt budgets, retries at a stronger model, or automatic provider fallback.
- Generalizing streaming as a user-selectable mode or changing unrelated non-streaming calls.
- Persisting thinking summaries, encrypted thinking signatures, redacted-thinking blocks, or raw chain-of-thought.
- Changing audit prompts, filters, prompt order, summary behavior, canonical audit-finding normalization, matching rules, or deterministic scoring.
- Enabling prompt caching, Batch API execution, tool use, browser tools, code execution, or computer use.
- Optimizing estimated run cost beyond accurately pricing reported usage.
- Deleting, mutating, or reusing prior Luna evaluation runs.
- Reclassifying reference defects or changing approved match decisions except for the established run-ID carry-forward procedure.
- Executing the paid Haiku audit or granting live-run approval.
- Adding a new domain glossary term or architectural decision record for the provider retarget.

## Further Notes

- Claude Haiku 4.5 is the closest current Anthropic cost-first analogue to GPT-5.6 Luna, but this is a product-positioning inference rather than an official cross-provider equivalence.
- At the time of specification, direct Claude API pricing is $1 per million input tokens and $5 per million output tokens. The implementation must verify and record the official price source when updating the versioned schedule.
- Haiku's thinking budget is a ceiling and the model may stop thinking earlier. The provider bills thinking within aggregate output usage.
- The larger total output cap requires streaming under the current Anthropic SDK guidance. This is why a small shared-client change is necessary even though ordinary Anthropic Messages requests are already supported.
- The existing prepared Luna replacement plan cannot be converted in place because model, provider, endpoint, reasoning configuration, and pricing participate in immutable run identity and point-of-use verification.
- Model lifecycle should be checked again before a future paid run. The pinned identifier is active at specification time, but a dated model can eventually be deprecated or retired.
- This spec supersedes only the Luna-specific target and execution details of the broader model-evaluation proof of concept. Its domain model, benchmark methodology, review separation, scoring rules, and privacy boundaries remain authoritative.
