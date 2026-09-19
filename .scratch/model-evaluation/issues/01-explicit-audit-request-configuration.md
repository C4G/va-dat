# 01: Make audit request configuration explicit

**What to build:** Add a backward-compatible audit request seam that preserves current production behavior while allowing evaluation runs to specify model, reasoning effort, sampling omissions, output limit, and complete usage metadata.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Existing Anthropic, OpenAI, and Gemini production callers retain their current effective defaults.
- [ ] An OpenAI evaluation caller can explicitly request GPT-5.6 Luna with medium reasoning and no temperature parameter.
- [ ] The request result exposes the provider metadata, token categories, stop reason, duration, and failure information required by evaluation runs.
- [ ] Network-free tests verify legacy defaults and the Luna request shape through fakes.
