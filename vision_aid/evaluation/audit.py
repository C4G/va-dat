"""Fixed Haiku request configuration and sequential paid execution."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from processing_scripts.llm_client.audit import AuditRequestClient, AuditRequestConfig
from vision_aid.evaluation.normalization import normalize_prompt_response
from vision_aid.evaluation.pricing import PriceSchedule

MODEL = "claude-haiku-4-5-20251001"
REQUEST_CONFIG = AuditRequestConfig(
    model=MODEL, thinking_budget_tokens=16000,
    max_output_tokens=24192, temperature=None,
)
CONFIGURATION = {
    "model": MODEL, "provider": "anthropic", "endpoint": "messages",
    "thinking_budget_tokens": 16000, "max_output_tokens": 24192,
    "temperature": "omitted", "summaries": "disabled",
}
USAGE_KEYS = (
    "input_tokens", "cached_input_tokens", "cache_creation_input_tokens",
    "output_tokens",
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")


def positive_cost(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except Exception as error:
        raise ValueError("Cost guardrail must be a positive decimal") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Cost guardrail must be a positive decimal")
    return amount


def execute(run: Path, manifest: dict[str, Any], api_key: str) -> bool:
    """Make each paid request once, saving reported usage and responses as received."""
    schedule = PriceSchedule.load(run / "pricing.json")
    client = AuditRequestClient(api_key=api_key, request_config=REQUEST_CONFIG)
    usage: dict[str, int] = {key: 0 for key in USAGE_KEYS}
    responses: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    format_failures: list[str] = []
    complete = True
    reason = None
    for prompt in manifest["prompts"]:
        if Decimal(schedule.estimate(MODEL, usage)) >= Decimal(manifest["max_cost_usd"]):
            complete, reason = False, "cost guardrail exhausted"
            break
        name = prompt["name"]
        prompt_text = json.loads((run / "prompts" / f"{name}.json").read_text())["prompt_text"]
        result: dict[str, Any]
        try:
            result = client.call(prompt_text)
        except Exception as error:
            result = {"success": False, "response": None, "usage": {},
                      "error": str(error)}
        reported: dict[str, Any] = result.get("usage") or {}
        for key in USAGE_KEYS:
            usage[key] += int(reported.get(key) or 0)
        responses.append({"prompt": name, "result": result})
        if result.get("success"):
            normalized = normalize_prompt_response(
                name, str(result.get("response") or ""), run_id=manifest["run_id"],
                model=MODEL, page_url=manifest["source_url"],
            )
            findings.extend(asdict(finding) for finding in normalized.findings)
            if normalized.parse_status == "malformed":
                format_failures.append(name)
        else:
            complete, reason = False, str(result.get("error") or "request failed")
        manifest.update(usage=usage, estimated_cost_usd=schedule.estimate(MODEL, usage),
                        complete=False, incomplete_reason=reason,
                        format_failures=format_failures)
        write_json(run / "raw-responses.json", responses)
        write_json(run / "audit-findings.json", findings)
        write_json(run / "run.json", manifest)
        if not complete:
            break
    manifest.update(complete=complete, incomplete_reason=reason,
                    estimated_cost_usd=schedule.estimate(MODEL, usage))
    write_json(run / "run.json", manifest)
    return complete
