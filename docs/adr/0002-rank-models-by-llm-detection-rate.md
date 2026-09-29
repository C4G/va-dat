# Rank models by LLM detection rate

Models are ranked first by LLM detection rate over human-approved `llm_eligible` Human findings, with estimated run cost as the only tie-breaker; latency, token usage, unmatched findings, programmatic detection rate, and overall detection rate are reported but do not change rank. This keeps the Human audit as the principal measure while preventing model-independent programmatic findings or an arbitrary composite formula from obscuring the model comparison.
