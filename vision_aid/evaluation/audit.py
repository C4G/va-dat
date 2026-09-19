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

from processing_scripts.llm_client.audit import (
    AuditRequestClient,
    AuditRequestConfig,
)
from vision_aid.evaluation.normalization import (
    normalize_programmatic_findings,
    normalize_prompt_response,
)
from vision_aid.evaluation.pricing import PriceSchedule
from vision_aid.evaluation.serialization import (
    json_digest,
    load_reference_set,
    reference_set_identity,
    write_json,
)

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
PLAN_FILENAME = "evaluation-manifest.json"
LIVE_OUTPUT_FILENAMES = (
    "raw-attempts.json",
    "canonical-audit-findings.json",
    "live-manifest.json",
)
FROZEN_CONFIGURATION = {
    "model": MODEL,
    "reasoning_effort": "medium",
    "endpoint": "chat.completions",
    "temperature": None,
    "max_output_tokens": 8192,
    "include_summaries": False,
    "execution": "sequential",
}


class AuditExecutionError(ValueError):
    """An audit gate, identity check, or execution policy failed."""


class RequestClient(Protocol):
    def call(self, prompt: str) -> dict[str, Any]:
        """Call one prompt and return the production client result shape."""


Pipeline = Callable[..., dict[str, Any]]


def _sha256(path: Path) -> str:
    """Hash one artifact without transforming its bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _positive_cost(value: str) -> Decimal:
    """Parse one strictly positive audit-cost guardrail."""
    try:
        cost_limit = Decimal(value)
    except Exception as error:
        raise AuditExecutionError(
            "The audit cost limit must be a decimal amount."
        ) from error
    if not cost_limit.is_finite() or cost_limit <= 0:
        raise AuditExecutionError(
            "The audit cost limit must be greater than zero."
        )
    return cost_limit


def normalize_audit_cost(value: str) -> str:
    """Validate and normalize one planned maximum audit cost."""
    return format(_positive_cost(value).normalize(), "f")


def _recorded_path(path: Path, run_directory: Path) -> str:
    """Prefer a run-relative evidence path while supporting external inputs."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(run_directory.resolve()))
    except ValueError:
        return str(resolved)


def _resolve_recorded_path(value: str, run_directory: Path) -> Path:
    """Resolve one plan artifact path against its evaluation run."""
    path = Path(value)
    return path if path.is_absolute() else run_directory / path


def _repository_state(repository: Path) -> dict[str, Any]:
    """Return the source-control commit and dirty state when available."""
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
    maximum_audit_cost_usd: str,
    reference_set_path: Path,
    workbook_sha256: str,
    snapshot_sha256: str,
    reference_set_version: str,
    eligibility_identity: str,
    homepage_url: str = "benchmark-homepage",
    pipeline: Pipeline | None = None,
    repository: Path | None = None,
    schedule: PriceSchedule | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the existing pipeline dry and freeze the billable intent."""
    normalized_cost = normalize_audit_cost(maximum_audit_cost_usd)
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
    frozen_references = load_reference_set(reference_set_path)
    if frozen_references.workbook_sha256 != workbook_sha256:
        raise AuditExecutionError(
            "Frozen reference-set workbook identity does not match the plan."
        )
    if frozen_references.version != reference_set_version:
        raise AuditExecutionError(
            "Frozen reference-set version does not match the plan."
        )
    if reference_set_identity(frozen_references) != eligibility_identity:
        raise AuditExecutionError(
            "Frozen eligibility decisions do not match the plan."
        )
    resolved_run_id = run_id or output_directory.resolve().name
    raw_programmatic_path = output_directory / "programmatic_findings.json"
    raw_programmatic = json.loads(
        raw_programmatic_path.read_text(encoding="utf-8")
    )
    canonical_programmatic = normalize_programmatic_findings(
        raw_programmatic,
        run_id=resolved_run_id,
        page_url=homepage_url,
    )
    canonical_programmatic_path = (
        output_directory / "canonical-programmatic.json"
    )
    write_json(
        canonical_programmatic_path,
        [asdict(item) for item in canonical_programmatic],
    )
    plan: dict[str, Any] = {
        "kind": "model-evaluation-audit-plan",
        "created_at": now,
        "run_id": resolved_run_id,
        "homepage_url": homepage_url,
        "workbook_sha256": workbook_sha256,
        "snapshot_sha256": snapshot_sha256,
        "reference_set_version": reference_set_version,
        "eligibility_identity": eligibility_identity,
        "configuration": FROZEN_CONFIGURATION,
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
        "maximum_audit_cost_usd": normalized_cost,
        "execution_destination": str(output_directory.resolve()),
        "snapshot_evidence": {
            "path": _recorded_path(snapshot_path, output_directory),
            "sha256": snapshot_sha256,
        },
        "reference_evidence": {
            "path": _recorded_path(reference_set_path, output_directory),
            "sha256": _sha256(reference_set_path),
        },
        "repository": _repository_state(repository or Path.cwd()),
        "programmatic_findings": {
            "count": len(canonical_programmatic),
            "path": str(
                canonical_programmatic_path.relative_to(output_directory)
            ),
            "sha256": _sha256(canonical_programmatic_path),
        },
    }
    plan["benchmark_identity"] = json_digest(
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
    plan["plan_digest"] = json_digest(plan)
    write_json(output_directory / PLAN_FILENAME, plan)
    return plan


def load_audit_plan(run_directory: Path) -> dict[str, Any]:
    """Load one run's immutable plan and self-contained evidence."""
    run_directory = run_directory.resolve()
    plan_path = run_directory / PLAN_FILENAME
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    recorded_digest = plan.get("plan_digest")
    digest_input = dict(plan)
    digest_input.pop("plan_digest", None)
    if recorded_digest != json_digest(digest_input):
        raise AuditExecutionError(
            "The saved evaluation plan has changed since creation."
        )
    if plan.get("kind") != "model-evaluation-audit-plan":
        raise AuditExecutionError("The evaluation run has an invalid plan kind.")
    if plan.get("run_id") != run_directory.name:
        raise AuditExecutionError(
            "The evaluation run identifier does not match its directory. "
            "Create a fresh evaluation run instead of copying or renaming one."
        )
    _positive_cost(str(plan.get("maximum_audit_cost_usd", "")))
    reference = plan.get("reference_evidence") or {}
    reference_path = _resolve_recorded_path(
        str(reference.get("path", "")), run_directory
    )
    if (
        not reference_path.is_file()
        or _sha256(reference_path) != reference.get("sha256")
    ):
        raise AuditExecutionError(
            "Frozen reference-set bytes differ from the evaluation plan."
        )
    reference_set = load_reference_set(reference_path)
    if (
        reference_set.workbook_sha256 != plan.get("workbook_sha256")
        or reference_set.version != plan.get("reference_set_version")
        or reference_set_identity(reference_set)
        != plan.get("eligibility_identity")
    ):
        raise AuditExecutionError(
            "Frozen reference-set identities differ from the evaluation plan."
        )
    programmatic = plan.get("programmatic_findings") or {}
    programmatic_path = run_directory / str(programmatic.get("path", ""))
    if (
        not programmatic_path.is_file()
        or _sha256(programmatic_path) != programmatic.get("sha256")
    ):
        raise AuditExecutionError(
            "Programmatic findings differ from the evaluation plan."
        )
    return plan


def _verified_prompt_text(
    run_directory: Path,
    plan: dict[str, Any],
    prompt: dict[str, Any],
) -> str:
    """Load one prompt only when its saved content identity still matches."""
    name = str(prompt["name"])
    prompt_path = run_directory / str(prompt["path"])
    prompt_data = json.loads(prompt_path.read_text(encoding="utf-8"))
    prompt_text = str(prompt_data["prompt_text"])
    if (
        hashlib.sha256(prompt_text.encode()).hexdigest()
        != plan["prompt_hashes"].get(name)
    ):
        raise AuditExecutionError(f"Prompt content drift detected for {name}.")
    return prompt_text


def load_verified_audit_plan(
    run_directory: Path,
    *,
    schedule: PriceSchedule | None = None,
) -> dict[str, Any]:
    """Revalidate every point-of-use identity before live execution."""
    run_directory = run_directory.resolve()
    plan = load_audit_plan(run_directory)
    if plan.get("execution_destination") != str(run_directory):
        raise AuditExecutionError(
            "The live destination differs from the planned evaluation run. "
            "Create a fresh evaluation run instead of copying one."
        )
    if plan.get("configuration") != FROZEN_CONFIGURATION:
        raise AuditExecutionError(
            "The planned configuration is not the frozen Luna POC."
        )
    price_schedule = schedule or PriceSchedule.default()
    if plan.get("pricing_identity") != price_schedule.identity:
        raise AuditExecutionError(
            "The price schedule differs from the evaluation plan."
        )
    parser_path = Path(__file__).with_name("normalization.py")
    if plan.get("parser_hash") != _sha256(parser_path):
        raise AuditExecutionError(
            "The parser identity differs from the evaluation plan."
        )
    snapshot = plan.get("snapshot_evidence") or {}
    snapshot_path = _resolve_recorded_path(
        str(snapshot.get("path", "")), run_directory
    )
    if (
        not snapshot_path.is_file()
        or _sha256(snapshot_path) != snapshot.get("sha256")
        or snapshot.get("sha256") != plan.get("snapshot_sha256")
    ):
        raise AuditExecutionError(
            "Benchmark snapshot identity differs from the evaluation plan."
        )
    for prompt in plan.get("prompts", ()):
        _verified_prompt_text(run_directory, plan, prompt)
    return plan


def ensure_live_destination_available(run_directory: Path) -> None:
    """Refuse to overwrite any evidence from an earlier live execution."""
    occupied = [
        run_directory / name
        for name in LIVE_OUTPUT_FILENAMES
        if (run_directory / name).exists()
    ]
    if occupied:
        names = ", ".join(path.name for path in occupied)
        raise AuditExecutionError(
            f"Live output already exists ({names}). Create a fresh "
            "evaluation run before executing again."
        )


def _failure_classification(result: dict[str, Any]) -> str:
    """Classify a provider failure for the bounded retry policy."""
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
    if (
        status in {401, 403}
        or "auth" in failure_type
        or "permission" in failure_type
    ):
        return "authentication"
    if isinstance(status, int) and 400 <= status < 500:
        return "invalid_request"
    return "permanent"


def _empty_usage() -> dict[str, int]:
    """Create the token-category accumulator used across attempts."""
    return {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
    }


def _add_usage(total: dict[str, int], result: dict[str, Any]) -> None:
    """Add API-reported categories from one possibly billed attempt."""
    usage = result.get("usage") or {}
    for key in total:
        total[key] += int(usage.get(key, 0) or 0)


def execute_audit_run(
    run_directory: Path,
    *,
    live: bool = False,
    api_key: str | None,
    approval_mode: str,
    approved_at: str,
    client: RequestClient | None = None,
    schedule: PriceSchedule | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute one verified evaluation run after point-of-use approval."""
    if not live:
        raise AuditExecutionError(
            "Live execution requires the explicit --live flag."
        )
    if not api_key:
        raise AuditExecutionError("Live execution requires OPENAI_API_KEY.")
    if approval_mode not in {"interactive", "auto"}:
        raise AuditExecutionError(
            "Live execution requires interactive or automatic approval."
        )
    run_directory = run_directory.resolve()
    ensure_live_destination_available(run_directory)
    plan = load_verified_audit_plan(run_directory, schedule=schedule)
    recorded_digest = plan["plan_digest"]
    cost_limit = _positive_cost(plan["maximum_audit_cost_usd"])
    price_schedule = schedule or PriceSchedule.default()
    request_client = client or AuditRequestClient(
        api_key=api_key,
        request_config=REQUEST_CONFIG,
    )
    output_directory = run_directory
    requests: list[dict[str, Any]] = []
    totals = _empty_usage()
    format_failures: list[str] = []
    canonical_findings: list[dict[str, Any]] = []
    complete = True
    incomplete_reason: str | None = None
    started = time.monotonic()
    raw_attempts_path = output_directory / "raw-attempts.json"
    for prompt in plan["prompts"]:
        current_cost = Decimal(price_schedule.estimate(MODEL, totals))
        if current_cost >= cost_limit:
            complete = False
            incomplete_reason = "audit_cost_limit_exhausted"
            break
        prompt_text = _verified_prompt_text(output_directory, plan, prompt)
        name = str(prompt["name"])
        attempts = []
        final_result: dict[str, Any] | None = None
        budget_exhausted = False
        for attempt_index in range(3):
            current_cost = Decimal(price_schedule.estimate(MODEL, totals))
            if current_cost >= cost_limit:
                complete = False
                incomplete_reason = "audit_cost_limit_exhausted"
                budget_exhausted = True
                break
            result = request_client.call(prompt_text)
            _add_usage(totals, result)
            classification = (
                "success"
                if result.get("success")
                else _failure_classification(result)
            )
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "classification": classification,
                    "result": result,
                }
            )
            final_result = result
            write_json(
                raw_attempts_path,
                {
                    "plan_digest": recorded_digest,
                    "requests": [
                        *requests,
                        {"name": name, "attempts": attempts},
                    ],
                    "usage": totals,
                },
            )
            if result.get("success"):
                break
            if classification not in RETRYABLE_FAILURES:
                complete = False
                incomplete_reason = classification
                break
            if attempt_index < 2:
                sleep(BACKOFF_SECONDS[attempt_index])
        if budget_exhausted:
            if attempts:
                requests.append({"name": name, "attempts": attempts})
            break
        assert final_result is not None
        request_record = {"name": name, "attempts": attempts}
        requests.append(request_record)
        if not final_result.get("success"):
            complete = False
            incomplete_reason = (
                incomplete_reason or "transient_failures_exhausted"
            )
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
        "approval": {
            "mode": approval_mode,
            "approved_at": approved_at,
        },
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
    write_json(
        output_directory / "canonical-audit-findings.json",
        canonical_findings,
    )
    write_json(output_directory / "live-manifest.json", manifest)
    return manifest
