# Separate review from deterministic scoring

A human records eligibility classifications and full-row Match decisions in the review CSV; a separate deterministic scorer consumes those decisions. This keeps the meaning of coverage under human control while making the same reviewed evidence reproducible without an automated reviewer subsystem.

ADR-0005 revises where classifications and Programmatic Match decisions are recorded. They now belong to the Human audit's shared Evaluation baseline; per-run reviewers continue to record LLM Match decisions. The separation between review and deterministic scoring remains.
