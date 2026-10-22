---
status: accepted
---

# Share classifications and Programmatic expectations by Human audit

Independent reviewers assigned different classifications and Programmatic matches to identical evidence, changing detection rates between model runs. Use a shared Evaluation baseline for each Human audit Excel file, containing agreed Eligibility classifications and expected Programmatic matches, with Programmatic responsibility limited to existing rules. Establish those decisions by reviewing all 86 original Human findings afresh, rather than adopting one model run's review.

The baseline belongs to the Human audit alone. Changes to Programmatic rules require deliberately updating the approved decisions; classifications do not change automatically. Handling changed page evidence is deferred.

This revises ADR-0001's placement of classification and Programmatic review decisions in each run: establish those decisions once for reuse, while reviewers continue to judge LLM matches and scoring remains deterministic. Select approved decisions by the Human audit checksum and stable Human finding identities. Each run saves the decisions it used, resolves Programmatic expectations against its own rule and element evidence, and rejects edits to fixed decisions during reporting. Missing or non-unique expected evidence prevents a successful report.

Rule changes require deliberate review of the approved decisions. Apply the shared decisions to the saved Haiku and Luna evaluations only after preserving previous reviews and reports, retaining compatible LLM judgments and surfacing incompatible ones for explicit review. Regenerate individual and combined reports using existing evidence, without new model requests. Global pooling, source-specific denominators, and the Overall denominator remain as recorded in ADR-0003.
