# Name raw and normalized audit artifacts explicitly

Status: resolved

## Problem Statement

An Evaluation run directory stores Programmatic findings under two explicit names, `raw-programmatic-findings.json` and `normalized-programmatic-findings.json`, but stores the AI audit's evidence as `raw-responses.json` and `audit-findings.json`. The two families do not read as parallel: nothing in the audit names says which file is the raw model evidence and which is the normalized set a reviewer copies `finding_id` values from. An evaluator filling in `review.csv` has to consult the README to know which file to open.

## Solution

Rename the audit artifacts so that both finding kinds follow the same `raw-…` / `normalized-…` convention, using the glossary term **Audit finding**:

- `raw-responses.json` becomes `raw-audit-responses.json`
- `audit-findings.json` becomes `normalized-audit-findings.json`

The raw file keeps the noun "responses" because it holds one entry per prompt, including failed requests, malformed replies, and usage, which are not findings. The normalized file keeps "findings" because it holds Audit findings with `finding_id` values.

This is a clean break, matching the earlier programmatic rename: new Evaluation runs write only the new names, and `report` reads only the new names. Existing local run directories are discarded rather than migrated.

## User Stories

1. As an evaluator, I want the normalized Audit findings file to be named `normalized-audit-findings.json`, so that I can tell at a glance it is the file to copy `audit_finding_id` values from.
2. As an evaluator, I want the raw model evidence file to be named `raw-audit-responses.json`, so that I can tell it holds the unprocessed model replies for the AI audit.
3. As an evaluator, I want the audit and programmatic artifacts to share a `raw-…` / `normalized-…` naming pattern, so that I can find the matching file for either finding kind without reading documentation.
4. As an evaluator, I want the raw audit file to still be called "responses", so that I am not misled into expecting findings for requests that failed or returned malformed output.
5. As an evaluator, I want `report` to read Audit findings from `normalized-audit-findings.json`, so that scoring uses the same file I reviewed.
6. As an evaluator, I want a live Evaluation run to stop writing `raw-responses.json` and `audit-findings.json`, so that a run directory never holds two competing copies of the same evidence.
7. As an evaluator, I want a run stopped by a request failure or the cost guardrail to still record its responses in `raw-audit-responses.json`, so that partial runs remain traceable.
8. As an evaluator, I want `raw-audit-responses.json` and `normalized-audit-findings.json` to be rewritten after every prompt, as the current files are, so that an interrupted run keeps the evidence gathered so far.
9. As an evaluator, I want the README's review instructions to name the new files, so that the steps I follow match what is on disk.
10. As an evaluator, I want the README's run-directory file table to list the raw and normalized files for each finding kind next to each other, so that the parallel structure is visible.
11. As an evaluator, I want the README's troubleshooting guidance to point to `raw-audit-responses.json` when an Audit finding is missing or malformed, so that I look in the right place.
12. As a maintainer, I want the `review.csv` column `audit_finding_id` to stay unchanged, so that the column keeps matching the glossary term Audit finding.
13. As a maintainer, I want the change marked as breaking in its commit, so that anyone holding an old run directory knows `report` will no longer read it.
14. As a maintainer, I want no fallback for the old filenames, so that the evaluator does not carry compatibility code for throwaway local output.
15. As a maintainer, I want the tests to fail if the old filenames are ever written again, so that the rename cannot silently regress.

## Implementation Decisions

- The audit execution step that iterates over prompts writes its per-prompt evidence to `raw-audit-responses.json` and its accumulated Audit findings to `normalized-audit-findings.json`. File contents and shapes are unchanged; only the names change.
- The `report` command loads Audit findings from `normalized-audit-findings.json`. Its existing failure when audit evidence is absent (for example, after a preview-only run) is unchanged.
- No compatibility layer: old names are neither read nor written.
- The `review.csv` column `audit_finding_id`, the `run.json` manifest fields (including `format_failures`), and the programmatic artifact names are unchanged.
- `CONTEXT.md` is unchanged. Filenames are an implementation detail, and "Audit finding" remains the correct term. No ADR is needed, since the rename is cheap to reverse.
- README updates cover the review-workflow step that names the finding files, the run-directory file table, the troubleshooting paragraph, the `audit_finding_id` column description, and the list of run artifacts.
- The commit uses the `refactor(evaluation)!:` prefix with a `BREAKING CHANGE:` footer stating that existing Evaluation run directories use unsupported artifact names, following the precedent of the earlier programmatic-findings rename.
- Existing local run directories under the gitignored `.model-evaluation/runs/` are deleted rather than migrated. The rest of `.model-evaluation/` (snapshots, plans) is kept.

## Testing Decisions

- Tests exercise external behavior only, through the evaluation CLI's `main` entry point with the audit request client replaced by a fake. That is the single seam, and it already exists. Tests assert on which files exist in the run directory and on `report`'s outcome, not on internal helpers.
- Live-run test: after a live run with a fake client, `raw-audit-responses.json` and `normalized-audit-findings.json` exist; `raw-responses.json` and `audit-findings.json` do not; and `report` succeeds when `review.csv` references `finding_id` values read from `normalized-audit-findings.json`.
- Failure or guardrail test: after a run that stops on the first prompt, `raw-audit-responses.json` holds exactly one response, and `report` still refuses the incomplete run.
- Preview test: unchanged. `report` still fails when no audit artifacts exist.
- Prior art: the existing CLI tests already assert that the old programmatic filenames are absent after a preview run. Mirror that pattern for the old audit filenames.
- No new unit tests at the audit-module level.

## Out of Scope

- Renaming the Audit finding concept (for example, to "LLM finding"), the `audit_finding_id` review column, or the `llm_eligible` classification.
- Changing the contents or schema of either audit artifact.
- Migrating or reading old run directories.
- Renaming prompt, payload, snapshot, reference, pricing, or manifest files.
- Any change to the shared pipeline output used by the web server or `run_pipeline.py`.

## Further Notes

- Considered and rejected: `raw-llm-responses.json` / `normalized-llm-responses.json`. The `llm` prefix would give one concept a third name alongside "Audit finding" and "AI Audit". The normalized file holds findings, not responses.
- Considered and rejected: `raw-audit-findings.json`. Failed and malformed replies recorded in the raw file contain no findings.

## Comments

Implemented in d4a87cf5. Verified with the evaluation CLI tests at the `main` seam: a live run writes `raw-audit-responses.json` and `normalized-audit-findings.json` but not the old names, `report` scores from the normalized file, and a stopped run records one response. Full suite: 36 passed. The two-axis review found no spec gaps. Existing local run directories were deleted.
