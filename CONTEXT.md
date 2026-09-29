# Accessibility Audit Evaluation

This context names the evidence and measures for the homepage accessibility experiment.

## Language

**Human audit**:
The authorized accessibility audit performed by human testers and delivered as an Excel spreadsheet. It supplies the source evidence the tool is measured against.
_Avoid_: Reference workbook, workbook, ground-truth spreadsheet, generated review workbook.

**Human finding**:
One accessibility defect from the Human audit, kept with its original evidence and with the sheet and row it came from. Its `source_element` is the element name the testers wrote, not a precise inferred location.
_Avoid_: Reference defect, workbook row, expected finding, inferred location.

**Benchmark snapshot**:
The saved HTML of the audited page, identified by its source URL and checksum.
_Avoid_: Live page.

**Evaluation run**:
One audit with a fixed model, together with its evidence, the human decisions, its completion status, and its report.
_Avoid_: Execution plan, report bundle.

**LLM**:
The part of the tool that asks a large language model to judge the page for accessibility problems.
_Avoid_: Audit model, AI audit.

**Programmatic checks**:
The part of the tool that applies fixed rules to the page's HTML. It uses no AI and gives the same answer every time.
_Avoid_: Deterministic checker.

**LLM finding**:
An accessibility problem reported by the LLM, kept with the response it came from.
_Avoid_: Audit finding, Human finding, Programmatic finding.

**Programmatic finding**:
An accessibility problem reported by the Programmatic checks.
_Avoid_: Audit finding, LLM finding.

**Eligibility classification**:
A reviewer's decision about which part of the tool should be expected to catch a Human finding, recorded with a reason. The values are `llm_eligible`, `programmatic`, `unavailable_evidence` (the Benchmark snapshot cannot show the problem), and `ambiguous` (the Human finding is too unclear to judge).
_Avoid_: Automatic model score, exclusion without rationale.

**Not testable from the page file**:
The reader-facing group for Human findings classified `unavailable_evidence` or `ambiguous`. They are left out of every detection rate, and each one is reported with its reason.
_Avoid_: Excluded, unavailable, ambiguous (in reports).

**Match decision**:
A reviewer's judgment that the selected findings together fully cover one Human finding. Partial evidence alone earns no credit.
_Avoid_: Candidate match, partial-credit score.

**LLM detection rate**:
The proportion of `llm_eligible` Human findings that LLM findings fully cover.
_Avoid_: Workbook-row recall, precision, F1, aggregate quality score.

**Programmatic detection rate**:
The proportion of `programmatic` Human findings that Programmatic findings fully cover. A classification on its own earns no coverage.
_Avoid_: Programmatic coverage.

**Overall detection rate**:
The proportion of all imported Human findings that either kind of finding fully covers, counting each Human finding once.
_Avoid_: Combined workbook coverage, LLM detection rate, model score.

**Estimated run cost**:
The token counts the provider reported, multiplied by a recorded public price schedule. It is not an invoice amount.

**Live-run approval**:
An operator's explicit authorization to run a displayed fixed-model execution, given with a positive cost guardrail that is checked between requests.
_Avoid_: API-key presence.
