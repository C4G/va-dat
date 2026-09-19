# 07: Prepare a safe Luna dry run

**What to build:** Produce a no-cost Luna audit plan against the approved benchmark configuration, with complete provenance and an explicit summary suitable for spending authorization.

**Blocked by:** 01: Make audit request configuration explicit; 02: Bootstrap a private, safe evaluation workspace; 03: Freeze a reproducible Pristine benchmark snapshot; 04: Generate and validate the homepage reference set.

**Status:** resolved

- [x] The dry run uses the frozen prompts, filters, prompt order, disabled summaries, sequential execution, and existing output limit.
- [x] The planned configuration records GPT-5.6 Luna, medium reasoning, Chat Completions, and omitted temperature.
- [x] Prompt payloads, request count, estimated input tokens, prompt hashes, parser hashes, and repository state are saved without making a provider call.
- [x] The manifest records workbook, snapshot, reference-set, benchmark, configuration, and pricing identities.
- [x] The command refuses live execution when the live flag, API key, approved reference set, or maximum audit-cost limit is absent.
- [x] Tests prove that an environment key alone cannot trigger spending.

## Comments

Implemented in `472500c`, hardened in `8bfe6af`, style-reviewed in `1cb479a`,
and identity-verified in `2129616`. Verified by dry-run manifest and no-spend gate tests; no provider
call is made by the test suite.
