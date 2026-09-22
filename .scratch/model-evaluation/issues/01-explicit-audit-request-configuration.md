# 01: Make audit request configuration explicit

**What to build:** Add a backward-compatible audit request seam that preserves current production behavior while allowing evaluation runs to specify model, reasoning effort, sampling omissions, output limit, and complete usage metadata.

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] Existing Anthropic, OpenAI, and Gemini production callers retain their current effective defaults.
- [x] An OpenAI evaluation caller can explicitly request GPT-5.6 Luna with medium reasoning and no temperature parameter.
- [x] The request result exposes the provider metadata, token categories, stop reason, duration, and failure information required by evaluation runs.
- [x] Network-free tests verify legacy defaults and the Luna request shape through fakes.

## Comments

- Implemented in `c371979` with review fixes in `c395efa`. Verified by four
  network-free audit-request tests and the production pipeline dry-run smoke
  test.


## Haiku retarget clarification (2026-09-22)

The Luna-specific target and credential details above are historical. They are
superseded by `.scratch/anthropic-evaluation-retarget/spec.md`; benchmark,
review, scoring, and safety requirements remain authoritative.
