"""Production-pipeline adapter and guarded evaluation audit execution."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from processing_scripts.llm_client.audit import AuditRequestClient, AuditRequestConfig
from vision_aid.evaluation.normalization import (
    normalize_programmatic_findings,
    normalize_prompt_response,
)
from vision_aid.evaluation.pricing import PriceSchedule

MODEL = "gpt-5.6-luna"
REQUEST_CONFIG = AuditRequestConfig(
    model=MODEL,
    reasoning_effort="medium",
    temperature=None,
    max_output_tokens=8192,
)
RETRYABLE_FAILURES = ("timeout", "rate_limit", "server_error")
BACKOFF_SECONDS = (1, 2)
RETRY_POLICY = {
    "maximum_additional_attempts": 2,
    "backoff_seconds": list(BACKOFF_SECONDS),
    "retryable": list(RETRYABLE_FAILURES),
}


class AuditExecutionError(ValueError):
    """An audit gate, identity check, or execution policy failed."""


class RequestClient(Protocol):
    def call(self, prompt: str) -> dict[str, Any]:
        """Call one prompt and return the production client result shape."""


Pipeline = Callable[..., dict[str, Any]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _repository_state(repository: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return {"commit": commit, "dirty": bool(status.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def build_audit_plan(
    snapshot_path: Path,
    output_directory: Path,
    *,
    workbook_sha256: str,
    snapshot_sha256: str,
    reference_set_version: str,
    eligibility_identity: str,
    homepage_url: str = "benchmark-homepage",
    pipeline: Pipeline | None = None,
    repository: Path | None = None,
    schedule: PriceSchedule | None = None,
) -> dict[str, Any]:
    """Run the existing pipeline dry and freeze an authorization summary."""
    if _sha256(snapshot_path) != snapshot_sha256:
        raise AuditExecutionError(
            "Benchmark snapshot checksum drift detected before audit planning."
        )
    if pipeline is None:
        from entry_points.run_pipeline import run_pipeline

        pipeline = run_pipeline
    output_directory.mkdir(parents=True, exist_ok=True)
    production_manifest = pipeline(
        html_path=str(snapshot_path),
        output_dir=output_directory,
        api_key=None,
        model=MODEL,
        dry_run=True,
        include_summaries=False,
        request_config=REQUEST_CONFIG,
    )
    prompt_entries = production_manifest.get("prompts_dry_run", [])
    prompts = []
    prompt_hashes: dict[str, str] = {}
    for entry in prompt_entries:
        name = str(entry["name"])
        prompt_path = output_directory / "prompts" / f"{name}.json"
        prompt_data = json.loads(prompt_path.read_text(encoding="utf-8"))
        prompt_text = str(prompt_data["prompt_text"])
        prompt_hashes[name] = hashlib.sha256(prompt_text.encode()).hexdigest()
        prompts.append(
            {
                "name": name,
                "checklist": entry["checklist"],
                "wcag_criteria": entry.get("wcag_criteria", []),
                "estimated_input_tokens": int(entry["prompt_tokens_est"]),
                "path": str(prompt_path.relative_to(output_directory)),
            }
        )
    price_schedule = schedule or PriceSchedule.default()
    parser_path = Path(__file__).with_name("normalization.py")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    run_id = "dry-" + _json_digest([snapshot_sha256, now])[:16]
    raw_programmatic_path = output_directory / "programmatic_findings.json"
    raw_programmatic = json.loads(raw_programmatic_path.read_text(encoding="utf-8"))
    canonical_programmatic = normalize_programmatic_findings(
        raw_programmatic,
        run_id=run_id,
        page_url=homepage_url,
    )
    canonical_programmatic_path = output_directory / "canonical-programmatic.json"
    canonical_programmatic_path.write_text(
        json.dumps(
            [asdict(item) for item in canonical_programmatic],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan: dict[str, Any] = {
        "kind": "model-evaluation-audit-plan",
        "created_at": now,
        "run_id": run_id,
        "homepage_url": homepage_url,
        "workbook_sha256": workbook_sha256,
        "snapshot_sha256": snapshot_sha256,
        "reference_set_version": reference_set_version,
        "eligibility_identity": eligibility_identity,
        "configuration": {
            "model": MODEL,
            "reasoning_effort": "medium",
            "endpoint": "chat.completions",
            "temperature": None,
            "max_output_tokens": 8192,
            "include_summaries": False,
            "execution": "sequential",
        },
        "filters": production_manifest.get("pass1_filters_active", []),
        "skipped_prompts": production_manifest.get("prompts_skipped", []),
        "request_count": len(prompts),
        "estimated_input_tokens": sum(
            item["estimated_input_tokens"] for item in prompts
        ),
        "prompts": prompts,
        "prompt_hashes": prompt_hashes,
        "parser_hash": _sha256(parser_path),
        "pricing_version": price_schedule.version,
        "pricing_identity": price_schedule.identity,
        "retry_policy": RETRY_POLICY,
        "repository": _repository_state(repository or Path.cwd()),
        "programmatic_findings": {
            "count": len(canonical_programmatic),
            "path": str(canonical_programmatic_path.relative_to(output_directory)),
            "sha256": _sha256(canonical_programmatic_path),
        },
    }
    plan["benchmark_identity"] = _json_digest(
        {
            key: plan[key]
            for key in (
                "workbook_sha256",
                "snapshot_sha256",
                "reference_set_version",
                "eligibility_identity",
                "configuration",
                "filters",
                "prompt_hashes",
                "parser_hash",
                "pricing_identity",
            )
        }
    )
    plan["authorization_digest"] = _json_digest(plan)
    (output_directory / "evaluation-manifest.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan


def _failure_classification(result: dict[str, Any]) -> str:
    failure = result.get("failure") or {}
    status = failure.get("status_code")
    failure_type = str(failure.get("type") or "").casefold()
    if status == 429 or "ratelimit" in failure_type:
        return "rate_limit"
    if (
        status in {408, 409}
        or "timeout" in failure_type
        or "connection" in failure_type
    ):
        return "timeout"
    if isinstance(status, int) and status >= 500:
        return "server_error"
    if status in {401, 403} or "auth" in failure_type or "permission" in failure_type:
        return "authentication"
    if isinstance(status, int) and 400 <= status < 500:
        return "invalid_request"
    return "permanent"


def _empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
    }


def _add_usage(total: dict[str, int], result: dict[str, Any]) -> None:
    usage = result.get("usage") or {}
    for key in total:
        total[key] += int(usage.get(key, 0) or 0)


def execute_authorized_audit(
    plan_path: Path,
    *,
    live: bool = False,
    authorization: str | None,
    api_key: str | None,
    max_audit_cost_usd: str | None,
    client: RequestClient | None = None,
    schedule: PriceSchedule | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute the exact reviewed plan only after every spending gate passes."""
    if not live:
        raise AuditExecutionError("Live execution requires the explicit --live flag.")
    if not api_key:
        raise AuditExecutionError("Live execution requires OPENAI_API_KEY.")
    if max_audit_cost_usd is None:
        raise AuditExecutionError(
            "Live execution requires --max-audit-cost-usd as a spending guardrail."
        )
    try:
        cost_limit = Decimal(max_audit_cost_usd)
    except Exception as error:
        raise AuditExecutionError(
            "The audit cost limit must be a decimal amount."
        ) from error
    if cost_limit <= 0:
        raise AuditExecutionError("The audit cost limit must be greater than zero.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    recorded_digest = plan.get("authorization_digest")
    digest_input = dict(plan)
    digest_input.pop("authorization_digest", None)
    if recorded_digest != _json_digest(digest_input):
        raise AuditExecutionError(
            "The saved dry-run summary has changed since creation."
        )
    if authorization != recorded_digest:
        raise AuditExecutionError(
            "Live authorization does not match the exact summarized configuration."
        )
    if plan.get("configuration") != {
        "model": MODEL,
        "reasoning_effort": "medium",
        "endpoint": "chat.completions",
        "temperature": None,
        "max_output_tokens": 8192,
        "include_summaries": False,
        "execution": "sequential",
    }:
        raise AuditExecutionError(
            "The dry-run configuration is not the frozen Luna POC."
        )
    price_schedule = schedule or PriceSchedule.default()
    if plan.get("pricing_identity") != price_schedule.identity:
        raise AuditExecutionError(
            "The price schedule differs from the authorized plan."
        )
    request_client = client or AuditRequestClient(
        api_key=api_key,
        request_config=REQUEST_CONFIG,
    )
    output_directory = plan_path.parent
    requests: list[dict[str, Any]] = []
    totals = _empty_usage()
    format_failures: list[str] = []
    canonical_findings: list[dict[str, Any]] = []
    complete = True
    incomplete_reason: str | None = None
    started = time.monotonic()
    for prompt in plan["prompts"]:
        current_cost = Decimal(price_schedule.estimate(MODEL, totals))
        if current_cost >= cost_limit:
            complete = False
            incomplete_reason = "audit_cost_limit_exhausted"
            break
        prompt_path = output_directory / prompt["path"]
        prompt_data = json.loads(prompt_path.read_text(encoding="utf-8"))
        prompt_text = str(prompt_data["prompt_text"])
        name = str(prompt["name"])
        if (
            hashlib.sha256(prompt_text.encode()).hexdigest()
            != plan["prompt_hashes"][name]
        ):
            raise AuditExecutionError(f"Prompt content drift detected for {name}.")
        attempts = []
        final_result: dict[str, Any] | None = None
        for attempt_index in range(3):
            result = request_client.call(prompt_text)
            _add_usage(totals, result)
            classification = (
                "success" if result.get("success") else _failure_classification(result)
            )
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "classification": classification,
                    "result": result,
                }
            )
            final_result = result
            if result.get("success"):
                break
            if classification not in RETRYABLE_FAILURES:
                complete = False
                incomplete_reason = classification
                break
            if attempt_index < 2:
                sleep(BACKOFF_SECONDS[attempt_index])
        assert final_result is not None
        request_record = {"name": name, "attempts": attempts}
        requests.append(request_record)
        if not final_result.get("success"):
            complete = False
            incomplete_reason = incomplete_reason or "transient_failures_exhausted"
            break
        normalized = normalize_prompt_response(
            name,
            str(final_result.get("response") or ""),
            run_id=str(plan["run_id"]),
            model=MODEL,
            page_url=str(plan["homepage_url"]),
        )
        if normalized.parse_status == "malformed":
            format_failures.append(name)
        canonical_findings.extend(asdict(item) for item in normalized.findings)
    manifest = {
        **plan,
        "kind": "model-evaluation-live-run",
        "authorized_plan_digest": recorded_digest,
        "maximum_audit_cost_usd": str(cost_limit),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "complete": complete,
        "rankable": complete,
        "incomplete_reason": incomplete_reason,
        "requests": requests,
        "usage": totals,
        "estimated_audit_cost_usd": price_schedule.estimate(MODEL, totals),
        "wall_time_seconds": round(time.monotonic() - started, 6),
        "request_durations_seconds": [
            attempt["result"].get("duration_seconds", 0)
            for request in requests
            for attempt in request["attempts"]
        ],
        "format_failures": format_failures,
        "canonical_findings": canonical_findings,
    }
    (output_directory / "canonical-audit-findings.json").write_text(
        json.dumps(canonical_findings, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (output_directory / "live-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
