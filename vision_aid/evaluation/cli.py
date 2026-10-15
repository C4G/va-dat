"""Prepare and execute fixed-model evaluations, then score human decisions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from vision_aid.evaluation.full import (
    capture_snapshots,
    execute_full_evaluation,
    load_full_inputs,
    prepare_full_evaluation,
    report_full_evaluation,
)
from vision_aid.evaluation.human_audit import import_homepage_human_findings
from vision_aid.evaluation.llm_audit import (
    DEFAULT_MODEL,
    MODEL_PRESETS,
    LLMRequestConfig,
    evaluation_configuration,
    execute,
    positive_cost,
)
from vision_aid.evaluation.page import prepare_page, report_page
from vision_aid.evaluation.pricing import PriceSchedule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HUMAN_AUDIT = PROJECT_ROOT / "Pristine Accessibility Defect Report.xlsx"


def build_parser() -> argparse.ArgumentParser:
    """Expose the supported evaluation operations."""
    parser = argparse.ArgumentParser(prog="visionaid-evaluate")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser(
        "capture", help="download each Human audit URL to a saved Benchmark snapshot",
        description=(
            "Download listed URLs in source order, following redirects. "
            "No model key or approval is required."
        ),
    )
    capture.add_argument("--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT)
    capture.add_argument(
        "--output-dir", type=Path, required=True, help="new snapshot directory"
    )
    run = commands.add_parser(
        "run", help="preview or execute an Evaluation run with one selected model",
        description=(
            "Haiku 5.5 (default), Opus 5.5 "
            "and Sonnet 5.5 use adaptive thinking with medium effort. GPT models "
            "use Chat Completions with medium reasoning effort. All presets omit "
            "temperature, disable summaries, and cap output at 24,192 tokens "
            "including reasoning/thinking. Live GPT execution requires OPENAI_API_KEY; "
            "live Claude execution requires ANTHROPIC_API_KEY. Previews need no key."
        ),
    )
    run.add_argument(
        "--model", choices=MODEL_PRESETS, default=DEFAULT_MODEL,
        help=f"fixed model preset (default: {DEFAULT_MODEL})",
    )
    run.add_argument(
        "--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT, help="Human audit"
    )
    run.add_argument("--html", type=Path, required=True, help="local Benchmark HTML")
    run.add_argument("--source-url", required=True, help="URL represented by the HTML")
    run.add_argument(
        "--max-cost-usd", required=True,
        help="positive between-request limit; a request underway can exceed it",
    )
    run.add_argument("--live", action="store_true", help="enable billable execution")
    run.add_argument(
        "--approve-live",
        action="store_true",
        help="explicitly approve billable execution without a prompt",
    )
    run_all = commands.add_parser(
        "run-all", help="preview or execute every listed page with one shared allowance",
        description=run.description,
    )
    run_all.add_argument(
        "--model", choices=MODEL_PRESETS, default=DEFAULT_MODEL,
        help=f"fixed model preset (default: {DEFAULT_MODEL})",
    )
    run_all.add_argument(
        "--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT, help="Human audit"
    )
    run_all.add_argument(
        "--snapshots", type=Path, required=True,
        help="saved snapshots.json mapping from capture; resolves HTML beside it",
    )
    run_all.add_argument(
        "--max-cost-usd", required=True,
        help=(
            "positive total allowance shared across pages; checked between requests; "
            "a request underway can exceed it"
        ),
    )
    run_all.add_argument("--live", action="store_true", help="enable billable execution")
    run_all.add_argument(
        "--approve-live", action="store_true",
        help="explicitly approve all displayed pages without a prompt; requires --live",
    )
    report = commands.add_parser(
        "report", help="score completed run and edited review.csv"
    )
    report.add_argument("--run-dir", type=Path, required=True)
    report.add_argument("--reviewer", required=True, help="who made the review decisions")
    report_all = commands.add_parser(
        "report-all", help="validate every page review and score unique Human findings",
        description=(
            "Final combined reporting requires every listed execution to complete "
            "and all page reviews to validate. Each original Human finding counts "
            "once. A Global finding earns source credit through complete detection "
            "on any single page; testable Global classifications must agree. "
            "Individual completed page reports remain available after parent failure."
        ),
    )
    report_all.add_argument("--run-dir", type=Path, required=True, help="Full evaluation directory")
    report_all.add_argument("--reviewer", required=True, help="who made all page review decisions")
    return parser


def _new_run_directory(kind: str = "runs") -> Path:
    """Create a unique private directory under the containing worktree root."""
    current = Path.cwd()
    worktree = next(
        (
            parent
            for parent in (current, *current.parents)
            if (parent / ".git").exists()
        ),
        current,
    )
    root = worktree / ".model-evaluation" / kind
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run = root / run_id
    run.mkdir()
    return run


def _run(args: argparse.Namespace) -> int:
    """Prepare a fresh run and execute only after explicit approval."""
    request_config = MODEL_PRESETS[args.model]
    configuration = evaluation_configuration(request_config)
    limit = positive_cost(args.max_cost_usd)
    if args.approve_live and not args.live:
        raise ValueError("--approve-live requires --live")
    if not args.html.is_file():
        raise ValueError(f"Benchmark HTML not found: {args.html}")
    human_audit = import_homepage_human_findings(args.human_audit, args.source_url)
    run = _new_run_directory()
    manifest = prepare_page(
        run, args.html, args.source_url, human_audit, request_config, limit
    )
    snapshot_hash = manifest["snapshot_sha256"]
    schedule = PriceSchedule.load(run / "artifacts" / "pricing.json")
    print(f"Evaluation run: {run}")
    _display_model(
        request_config, configuration, schedule, len(manifest["prompts"]), limit
    )
    print(
        f"Snapshot SHA-256: {snapshot_hash}; "
        f"Human findings: {len(human_audit.human_findings)}"
    )
    print(f"Review CSV: {run / 'review.csv'}")
    if not args.live:
        print("Preview complete; no paid requests made.")
        return 0
    api_key = _approved_api_key(args, configuration)
    if api_key is None:
        return 0
    complete = execute(run, manifest, api_key, request_config)
    print(f"Run {'complete' if complete else 'incomplete'}: {run}")
    return 0 if complete else 1


def _approved_api_key(args: argparse.Namespace, configuration: dict[str, Any]) -> str | None:
    """Select the provider's credentials and ask once for the displayed scope."""
    load_dotenv(PROJECT_ROOT / ".env")
    key_name = (
        "OPENAI_API_KEY" if configuration["provider"] == "openai" else "ANTHROPIC_API_KEY"
    )
    api_key = os.getenv(key_name)
    if not api_key:
        raise ValueError(f"Live execution requires {key_name}")
    if not args.approve_live and (
        not sys.stdin.isatty()
        or input("Type 'yes' to approve paid execution: ") != "yes"
    ):
        print("Live execution declined; no paid requests made.")
        return None
    return api_key


def _display_model(
    request_config: LLMRequestConfig,
    configuration: dict[str, Any],
    schedule: PriceSchedule,
    prompt_count: int,
    limit: Decimal,
) -> None:
    """Display fixed request settings, recorded prices and the shared guardrail."""
    print(
        f"Model: {request_config.model}; provider: {configuration['provider']}; "
        f"endpoint: {configuration['endpoint']}; "
        f"thinking: {configuration.get('thinking', {}).get('type', 'none')}; "
        f"effort: {request_config.reasoning_effort or 'omitted'}; "
        f"thinking budget: {request_config.thinking_budget_tokens or 'none'}; "
        f"output cap: {request_config.max_output_tokens}"
    )
    print(
        "Temperature: omitted; summaries: disabled; "
        f"prompts: {prompt_count}"
    )
    print(f"Pricing: {schedule.version} ({schedule.identity})")
    rates = schedule.data["models"][request_config.model]
    tiers = [("", rates)]
    if "long_context" in rates:
        upper = rates["long_context"]
        threshold = upper["above_input_tokens"]
        tiers = [
            (f"up to {threshold:,} total input tokens per request", rates),
            (f"above {threshold:,} total input tokens per request", upper),
        ]
    cache_write = (
        "5-minute cache write" if configuration["provider"] == "anthropic" else "cache write"
    )
    for description, tier in tiers:
        print(
            f"Rates per million tokens (USD){f' ({description})' if description else ''}: "
            f"input ${tier['input_per_million_usd']}; "
            f"output ${tier['output_per_million_usd']}; "
            f"cache read ${tier['cached_input_per_million_usd']}; "
            f"{cache_write} ${tier['cache_creation_input_per_million_usd']}"
        )
    print(
        f"Cost guardrail: ${limit}; checked before each request; "
        "a request underway can exceed the limit"
    )


def _run_all(args: argparse.Namespace) -> int:
    """Prepare all listed pages and approve the entire scope once."""
    request_config = MODEL_PRESETS[args.model]
    limit = positive_cost(args.max_cost_usd)
    if args.approve_live and not args.live:
        raise ValueError("--approve-live requires --live")
    audits, snapshots = load_full_inputs(args.human_audit, args.snapshots)
    run = _new_run_directory("full-runs")
    print(f"Full evaluation: {run}")
    manifest = prepare_full_evaluation(run, audits, snapshots, request_config, limit)
    prompt_count = 0
    for page in manifest["pages"]:
        child = run / page["run_dir"]
        child_manifest = json.loads((child / "run.json").read_text())
        prompt_count += len(child_manifest["prompts"])
        print(f"Page: {page['source_url']}; Evaluation run: {child}")
        print(f"Review CSV: {child / 'review.csv'}")
    first_child = run / manifest["pages"][0]["run_dir"]
    schedule = PriceSchedule.load(first_child / "artifacts/pricing.json")
    _display_model(
        request_config, manifest["configuration"], schedule, prompt_count, limit
    )
    if not args.live:
        print("Preview complete; no paid requests made.")
        return 0
    api_key = _approved_api_key(args, manifest["configuration"])
    if api_key is None:
        return 0
    complete = execute_full_evaluation(run, manifest, api_key, request_config)
    print(f"Full evaluation {'complete' if complete else 'incomplete'}: {run}")
    return 0 if complete else 1


def _report(args: argparse.Namespace) -> int:
    """Validate human decisions and report a completed run."""
    run = args.run_dir.resolve()
    report_page(run, args.reviewer)
    print(f"Markdown report: {run / 'report.md'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the requested CLI operation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            mapping = capture_snapshots(args.human_audit, args.output_dir)
            print(f"Snapshot mapping: {mapping}")
            return 0
        if args.command == "run-all":
            return _run_all(args)
        if args.command == "report-all":
            run = args.run_dir.resolve()
            report_full_evaluation(run, args.reviewer)
            print(f"Combined Markdown report: {run / 'report.md'}")
            return 0
        return _run(args) if args.command == "run" else _report(args)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
