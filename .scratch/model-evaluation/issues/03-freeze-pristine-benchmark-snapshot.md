# 03: Freeze a reproducible Pristine benchmark snapshot

**What to build:** Add a preparation workflow that captures the raw Pristine homepage once and turns it into an immutable benchmark snapshot with enough provenance to reuse across model runs.

**Blocked by:** 02: Bootstrap a private, safe evaluation workspace.

**Status:** ready-for-agent

- [ ] The preparation workflow saves the exact raw HTML consumed by the existing audit pipeline.
- [ ] Snapshot metadata records source URL, retrieval time, relevant HTTP metadata, SHA-256, and the stakeholder-supported temporal assumption.
- [ ] Reusing a snapshot does not refetch or silently overwrite it.
- [ ] The existing unrelated DAT Vision Aid fixture is rejected as a Pristine benchmark input.
- [ ] Tests use local HTTP fakes and verify content identity, provenance, hashing, and overwrite protection.
