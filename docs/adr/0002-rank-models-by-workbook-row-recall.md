# Rank models by workbook-row recall

Models are ranked first by workbook-row recall over human-approved `llm_eligible` rows, with estimated audit-run cost as the only tie-breaker; latency, token usage, unmatched findings, programmatic coverage, and combined workbook coverage are reported but do not change rank. This keeps the mandated defect workbook as the principal measure while preventing model-independent programmatic findings or an arbitrary composite formula from obscuring the model comparison.
