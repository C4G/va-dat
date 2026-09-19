# Accessibility Audit Evaluation

This context describes the language used to evaluate AI-generated accessibility audit results against a human-reviewed reference.

## Language

**Reference defect**:
A human-reviewed accessibility problem derived from the mandated defect-report workbook and retained as benchmark evidence with traceable source provenance.
_Avoid_: Ground-truth row, Excel issue, expected finding

**Audit finding**:
An accessibility problem reported by the AI audit model under evaluation. Programmatic checker output is not an audit finding for the primary model-efficacy score.
_Avoid_: Reference defect, programmatic finding, model response

**Workbook-row recall**:
The count and proportion of scorable workbook source rows caught by correctly matched audit findings. It is the primary model-ranking metric; cost is the only tie-breaker.
_Avoid_: Precision, F1, aggregate quality score

**LLM-eligible reference defect**:
A reference defect for which the AI audit model receives enough evidence and responsibility to make the relevant accessibility judgment. Defects intentionally handled only by programmatic checks are not LLM-eligible.
_Avoid_: Every workbook row, programmatic defect

**Benchmark snapshot**:
An immutable capture of the audited webpage used as the common input for every evaluated model, with its source and capture identity recorded.
_Avoid_: Live page, test URL

**Evaluation run**:
One planned model evaluation and its resulting audit evidence, reviewed match decisions, and reports, identified together for reproducibility.
_Avoid_: Dry-run folder, report bundle

**Eligibility classification**:
The reviewed assignment explaining whether a reference defect belongs to the AI model's responsibility, a programmatic check, unavailable audit evidence, or unresolved ambiguity.
_Avoid_: Model score, exclusion without rationale

**Programmatic finding**:
An accessibility problem reported by a deterministic checker rather than an AI audit model. It contributes to combined workbook coverage but not to model ranking.
_Avoid_: Audit finding, LLM-eligible reference defect

**Combined workbook coverage**:
The count and proportion of in-scope workbook rows caught by either programmatic findings or audit findings, with unavailable and ambiguous rows still reported explicitly.
_Avoid_: Workbook-row recall, model score

**Canonical audit finding**:
A lossless, structured representation of one raw audit finding used for comparison across prompts and models.
_Avoid_: Production report row, raw model response

**Match decision**:
An approved determination that one canonical audit finding does or does not correspond to one reference defect, with supporting evidence and rationale.
_Avoid_: Candidate match, similarity score

**Estimated run cost**:
The calculated cost of one audit run using API-reported token usage and a recorded model-price schedule. It is the sole tie-breaker when workbook-row recall is equal.
_Avoid_: Invoice amount, latency score

**Live-run approval**:
An operator's explicit confirmation to execute a displayed audit plan under a maximum audit-cost guardrail.
_Avoid_: Authorization digest, API-key presence

**Comparison reviewer**:
A human or model that proposes eligibility classifications or match decisions through the same review process. A comparison reviewer does not calculate the final score.
_Avoid_: Scorer, audit model
