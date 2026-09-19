# 03: Freeze a reproducible Pristine benchmark snapshot

**What to build:** Add a preparation workflow that captures the raw Pristine homepage once and turns it into an immutable benchmark snapshot with enough provenance to reuse across model runs.

**Blocked by:** 02: Bootstrap a private, safe evaluation workspace.

**Status:** resolved

- [x] The preparation workflow saves the exact raw HTML consumed by the existing audit pipeline.
- [x] Snapshot metadata records source URL, retrieval time, relevant HTTP metadata, SHA-256, and the stakeholder-supported temporal assumption.
- [x] Reusing a snapshot does not refetch or silently overwrite it.
- [x] The existing unrelated DAT Vision Aid fixture is rejected as a Pristine benchmark input.
- [x] Tests use local HTTP fakes and verify content identity, provenance, hashing, and overwrite protection.

## Comments

- Implemented in `0bd719c` with review hardening in `fc630cb`. Verified by
  local-HTTP snapshot tests covering byte identity, provenance, SHA-256,
  no-refetch reuse, UTF-8 compatibility, atomic publication, fixture rejection,
  and overwrite protection; the full suite passes with 17 tests.
