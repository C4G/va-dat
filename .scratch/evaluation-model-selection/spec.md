# Select a model for an Evaluation run

Status: resolved

Design decisions settled and implementation authorized on October 1, 2026.

## Settled decisions

- Support a hardcoded set of three models through Anthropic's direct API: Haiku 4.5, Opus 5.5, and Sonnet 5.5.
- Select one model per Evaluation run through `--model`; retain Haiku 4.5 as the default.
- Each Evaluation run holds its selected model fixed throughout. A command that evaluates several models is outside this feature.
- Accept only the three canonical API IDs below. Reject unsupported IDs, including convenience aliases, with an error listing the supported choices.
- Use fixed request presets with no operator overrides for thinking, effort, or output token limits.
- Preserve Haiku's existing thinking budget. Use adaptive thinking with explicit `medium` effort for both Opus and Sonnet.
- Keep the existing 24,192 output-token cap for all three models. This cap includes thinking and final text; adaptive thinking does not reserve a fixed number of final-text tokens.
- Preserve the positive cost guardrail checked between requests. A request underway can take the final Estimated run cost above the limit.
- Add versioned public prices for the new models, and show the selected model's settings and rates before Live-run approval.

This changes the Haiku-only scope in [the POC reduction spec](../poc-reduction/spec.md). Human review and scoring continue to follow [ADR 0001](../../docs/adr/0001-separate-review-from-scoring.md) and [ADR 0002](../../docs/adr/0002-rank-models-by-llm-detection-rate.md).

## Model presets

| Model | Accepted `--model` value | Thinking | Effort | Output-token cap |
| --- | --- | --- | --- | --- |
| Haiku 4.5, default | `claude-haiku-4-5-20251001` | Enabled, 16,000-token budget | Omitted | 24,192 |
| Opus 5.5 | `claude-opus-5-5` | Adaptive, no manual budget | `medium` | 24,192 |
| Sonnet 5.5 | `claude-sonnet-5-5` | Adaptive, no manual budget | `medium` | 24,192 |

All presets omit temperature, disable summaries, and use standard Anthropic Messages requests. These exact IDs identify fixed model snapshots. The dateless Opus and Sonnet IDs do not require invented date suffixes.

Example selection:

```bash
uv run visionaid-evaluate run \
  --html .model-evaluation/pristine-home.html \
  --source-url https://pristineai.com/ \
  --model claude-opus-5-5 \
  --max-cost-usd 1.00
```

This example prepares a preview. The existing `--live` and Live-run approval flow enables paid execution.

## Run behavior and evidence

- Resolve the selected preset once and use it consistently for prompt preparation, paid execution, normalization, cost estimates, and saved run metadata. Execution must not silently fall back to global Haiku settings.
- Record the canonical model ID, provider and endpoint, thinking mode, manual budget when applicable, effort when applicable, output cap, omitted temperature, and disabled summaries in `run.json`. Retain provider-returned model identity in raw response evidence.
- Display the selected preset, applicable token rates, versioned price-schedule identity, prompt count, and positive cost guardrail before asking for Live-run approval.
- Preserve key-free previews, no requests after declined approval, explicit authorization for paid execution, sequential requests, disabled retries, saved partial evidence, and stopping on request failure or accumulated cost exhaustion.
- A model that is unavailable to the operator's account fails with retained evidence under the existing request-failure behavior. Do not substitute another model.
- Continue to generate reports from saved run evidence, including previously completed Haiku runs whose metadata predates model selection. Human review and detection-rate scoring do not change.
- Preserve the current handling of malformed responses and output-limit stop reasons; changing completion semantics is outside this feature.

## Versioned pricing

Standard public rates checked October 1, 2026, in USD per million tokens:

| Model | Input | Output | Cache read | 5-minute cache write |
| --- | ---: | ---: | ---: | ---: |
| Haiku 4.5 | 1 | 5 | 0.10 | 1.25 |
| Opus 5.5 | 4 | 20 | 0.20 | 5 |
| Sonnet 5.5 | 2 | 10 | 0.20 | 2.50 |

Use exact rates from the recorded schedule, including Opus's cache-read rate rather than assuming a common multiplier. Keep the schedule copy and its content identity with each run. Existing run evidence retains its original schedule. Record the rate source and capture date accurately; a capture date is not necessarily the publisher's publication date.

This feature uses standard pricing and does not add fast mode, batch execution, residency options, or new caching behavior.

## Implementation constraints

- Keep model selection and the three-model restriction in the evaluator. The shared client remains usable by existing production callers with their current defaults.
- Add explicit support for adaptive thinking and Anthropic effort in the shared request configuration. For the new models, send adaptive thinking and `output_config` with `effort` set to `medium`; omit `budget_tokens`.
- Stream all three evaluation presets. The Anthropic Python SDK requires streaming above 21,333 output tokens, and all presets retain a 24,192 cap. Streaming must not depend only on the presence of a manual thinking budget.
- Continue extracting final text separately from thinking content and preserving reported usage and failures in raw evidence.
- No model-discovery or dynamic-pricing subsystem is required. Adding another model later requires an explicit preset and versioned prices.
- Update evaluator help and README instructions to describe selection, the default, settings, and the existing between-request cost limit.

## Acceptance criteria

- [x] Omitted `--model` selects the existing Haiku preset; each of the three exact IDs is accepted in preview and live paths.
- [x] An unsupported ID is rejected before creating a run or making provider requests, and the error lists supported choices.
- [x] Every selected model uses its prescribed request settings and appears consistently in run metadata, request evidence, LLM findings, cost calculations, and the final report.
- [x] Mock-provider tests verify the exact Haiku and adaptive request shapes, explicit `medium` effort for both new models, omitted temperature, streaming, and final-text extraction.
- [x] Cost tests verify each model's token categories, including Opus cache-read pricing, using saved versioned prices.
- [x] Preview, declined approval, failure, and cost exhaustion retain existing lifecycle behavior for selected models.
- [x] Previously completed Haiku evidence still produces a report.
- [x] Shared-client regression checks confirm existing production caller defaults remain intact.
- [x] CLI help and README show model selection and explain that the guardrail can be exceeded by a request underway.

Verification uses mocked providers and local fixtures; this feature does not require a paid verification run.

## Remaining design decisions

None.

## Starting code facts

- `vision_aid/evaluation/llm_audit.py` pins Haiku, its request settings, and the model used for normalization and cost estimation.
- `vision_aid/evaluation/cli.py` has no model selection option and uses those fixed settings for preparation, run metadata, and Live-run approval.
- The versioned price schedule contains only the pinned Haiku ID. Cost estimation requires an exact model match.
- The shared request client supports manual extended thinking but has no adaptive thinking or Anthropic effort settings.
- Reports already read the model from saved run metadata.

## Sources

- [Anthropic model overview](https://platform.claude.com/docs/en/models/overview), checked October 1, 2026.
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), checked October 1, 2026.
- [Anthropic thinking configuration and streaming constraints](https://platform.claude.com/docs/en/build-with-claude/thinking), checked October 1, 2026.
- [Anthropic effort configuration](https://platform.claude.com/docs/en/build-with-claude/effort), checked October 1, 2026.
- [Anthropic model IDs and versioning](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions), checked October 1, 2026.

Opus defaults to medium effort and Sonnet to high. Explicit medium effort for both is the agreed evaluation preset. Equal effort labels and output caps do not imply equal computation across models.

## Comments

Completed October 1, 2026, in implementation commit `bd1d9f68` and review-fix commit `896ccebe` on `feat/model-evaluation`.

Verification: `uv run pytest -q` passed all 69 tests after the review fix. `uvx ty check processing_scripts/llm_client/audit.py vision_aid/evaluation --output-format concise` passed. `git diff --check` passed. Provider tests used synthetic responses; no paid verification requests were made.

The independent Standards review had no findings. The Spec review found one missing CLI-help requirement, fixed in `896ccebe` and confirmed resolved by the reviewer. See [the review record](review.md).

On October 1, 2026, the operator requested medium effort for both Opus and Sonnet. Commit `f9e21865` updates both presets, CLI help, README, this spec, and request/evidence tests. All 69 tests and scoped typechecks passed. Independent Standards and Spec reviews found no issues in this follow-up.
