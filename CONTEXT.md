# Accessibility Audit Evaluation

This context names the evidence and measures for the homepage accessibility experiment.

## Language

**Reference workbook**:
The authorized human accessibility audit workbook that supplies source evidence.
_Avoid_: Ground-truth spreadsheet, generated review workbook.

**Reference defect**:
One source workbook defect retained with its original evidence and sheet and row provenance. Its `source_element` is the original element name, not a precise inferred location.
_Avoid_: Expected finding, inferred location.

**Benchmark snapshot**:
The identified HTML evidence for the page being audited, paired with its source URL and checksum.
_Avoid_: Live page.

**Evaluation run**:
One fixed-model audit and its evidence, human decisions, completion status, and report.
_Avoid_: Execution plan, report bundle.

**Audit finding**:
An accessibility problem reported by the AI audit model and retained with its source response.
_Avoid_: Reference defect, programmatic finding.

**Programmatic finding**:
An accessibility problem reported by a deterministic checker rather than the AI audit model.
_Avoid_: Audit finding.

**Eligibility classification**:
The human assignment of a Reference defect to `llm_eligible`, `programmatic`, `unavailable_evidence`, or `ambiguous`, with a reason.
_Avoid_: Automatic model score, exclusion without rationale.

**Match decision**:
A human judgment that selected findings jointly provide full-row coverage of one Reference defect. Partial evidence alone does not award credit.
_Avoid_: Candidate match, partial-credit score.

**Workbook-row recall**:
The proportion of LLM-eligible Reference defects fully covered by Audit findings.
_Avoid_: Precision, F1, aggregate quality score.

**Programmatic coverage**:
The proportion of programmatic Reference defects fully covered by Programmatic findings. Classification alone does not award coverage.

**Combined workbook coverage**:
The proportion of imported Reference defects fully covered by either finding kind, counting each row once.
_Avoid_: Workbook-row recall, model score.

**Estimated run cost**:
The cost calculated from reported usage and a recorded pricing schedule, rather than an invoice amount.

**Live-run approval**:
An operator's explicit authorization of a displayed fixed-model execution under a positive between-request cost guardrail.
_Avoid_: API-key presence.
