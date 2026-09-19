# 02: Bootstrap a private, safe evaluation workspace

**What to build:** Provide the CLI shell and private workspace conventions needed to prepare, run, review, and report evaluations without exposing employer data or accidentally spending money.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The evaluation CLI exposes discoverable prepare, audit, review, and report workflows.
- [ ] The source workbook is ignored by exact filename, and all generated references, reviews, snapshots, runs, and reports are ignored under one private workspace.
- [ ] Missing private inputs produce actionable instructions rather than downloads or silent substitutions.
- [ ] Dry-run behavior is the default even when an API key is present.
- [ ] Excel support is added as a runtime dependency and pytest as a development dependency, with lock and generated dependency artifacts kept consistent.
- [ ] Synthetic CLI tests prove workspace initialization and safe defaults without private data or network access.
