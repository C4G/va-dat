"""Fixed evaluation model presets and sequential paid execution."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from processing_scripts.llm_client.audit import (
    AuditRequestClient as LLMRequestClient,
)
from processing_scripts.llm_client.audit import (
    AuditRequestConfig as LLMRequestConfig,
)
from vision_aid.evaluation.normalization import normalize_prompt_response
from vision_aid.evaluation.pricing import PriceSchedule

DEFAULT_MODEL = "claude-haiku-5-5"
OPENAI_MODELS = ("gpt-6-luna", "gpt-6.1-sol")
MODEL_PRESETS = {
    **{
        model: LLMRequestConfig(
            model=model,
            adaptive_thinking=True,
            reasoning_effort="medium",
            max_output_tokens=24192,
            temperature=None,
        )
        for model in (DEFAULT_MODEL, "claude-opus-5-5", "claude-sonnet-5-5")
    },
    **{
        model: LLMRequestConfig(
            model=model,
            reasoning_effort="medium",
            max_output_tokens=24192,
            temperature=None,
        )
        for model in OPENAI_MODELS
    },
}
USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_creation_input_tokens",
    "output_tokens",
)


def evaluation_configuration(config: LLMRequestConfig) -> dict[str, Any]:
    """Record the selected preset and evaluation-only request settings."""
    provider = "openai" if config.model in OPENAI_MODELS else "anthropic"
    metadata = config.as_metadata()
    return {
        "model": config.model,
        "provider": provider,
        "endpoint": "chat.completions" if provider == "openai" else "messages",
        **({"thinking": metadata["thinking"]} if "thinking" in metadata else {}),
        "thinking_budget_tokens": config.thinking_budget_tokens,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "temperature": "omitted",
        "summaries": "disabled",
    }


def write_json(path: Path, value: object) -> None:
    """Save one readable private evidence artifact."""
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def positive_cost(value: str) -> Decimal:
    """Parse a strictly positive cost guardrail."""
    try:
        amount = Decimal(value)
    except Exception as error:
        raise ValueError("Cost guardrail must be a positive decimal") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Cost guardrail must be a positive decimal")
    return amount


def billable_usage(model: str, reported: dict[str, Any]) -> dict[str, int]:
    """Separate OpenAI cached subsets without changing reported evidence."""
    usage = {key: int(reported.get(key) or 0) for key in USAGE_KEYS}
    if model in OPENAI_MODELS:
        raw = reported.get("provider_usage") or {}
        details = raw.get("prompt_tokens_details") or {}
        usage["cached_input_tokens"] = int(details.get("cached_tokens") or 0)
        usage["cache_creation_input_tokens"] = int(details.get("cache_write_tokens") or 0)
        usage["input_tokens"] -= (
            usage["cached_input_tokens"] + usage["cache_creation_input_tokens"]
        )
    return usage


def execute(
    run: Path, manifest: dict[str, Any], api_key: str,
    request_config: LLMRequestConfig,
) -> bool:
    """Make each paid request once, saving reported usage and responses as received."""
    artifacts = run / "artifacts"
    schedule = PriceSchedule.load(artifacts / "pricing.json")
    client = LLMRequestClient(
        api_key=api_key,
        request_config=request_config,
        max_retries=0,
    )
    usage: dict[str, int] = {key: 0 for key in USAGE_KEYS}
    estimated_cost = Decimal(0)
    responses: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    format_failures: list[str] = []
    complete = True
    reason = None
    for prompt in manifest["prompts"]:
        if estimated_cost >= Decimal(manifest["max_cost_usd"]):
            complete, reason = False, "cost guardrail exhausted"
            break
        name = prompt["name"]
        prompt_text = json.loads((artifacts / "prompts" / f"{name}.json").read_text())[
            "prompt_text"
        ]
        result: dict[str, Any]
        try:
            result = client.call(prompt_text)
        except Exception as error:  # noqa: BLE001
            # Retain an unexpected request failure as run evidence.
            result = {
                "success": False,
                "response": None,
                "usage": {},
                "error": str(error),
            }
        reported: dict[str, Any] = result.get("usage") or {}
        for key in USAGE_KEYS:
            usage[key] += int(reported.get(key) or 0)
        billable = billable_usage(request_config.model, reported)
        request_cost = schedule.estimate(request_config.model, billable)
        estimated_cost += Decimal(request_cost)
        responses.append({
            "prompt": name, "result": result, "billable_usage": billable,
            "estimated_cost_usd": request_cost,
        })
        if result.get("success"):
            normalized = normalize_prompt_response(
                name,
                str(result.get("response") or ""),
                run_id=manifest["run_id"],
                model=request_config.model,
                page_url=manifest["source_url"],
            )
            findings.extend(asdict(finding) for finding in normalized.findings)
            if normalized.parse_status == "malformed":
                format_failures.append(name)
        else:
            complete, reason = False, str(result.get("error") or "request failed")
        manifest.update(
            usage=usage,
            estimated_cost_usd=format(estimated_cost.normalize(), "f"),
            complete=False,
            incomplete_reason=reason,
            format_failures=format_failures,
        )
        write_json(artifacts / "raw-llm-responses.json", responses)
        write_json(run / "normalized-llm-findings.json", findings)
        write_json(run / "run.json", manifest)
        if not complete:
            break
    manifest.update(
        complete=complete,
        incomplete_reason=reason,
        estimated_cost_usd=format(estimated_cost.normalize(), "f"),
    )
    write_json(run / "run.json", manifest)
    return complete
