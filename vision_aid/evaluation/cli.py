"""Command-line entry point for visionaid-evaluate."""

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

from vision_aid.evaluation.execution.llm_audit import (
    DEFAULT_MODEL,
    MODEL_PRESETS,
    LLMRequestConfig,
    evaluation_configuration,
    execute,
    positive_cost,
)
from vision_aid.evaluation.execution.pricing import PriceSchedule
from vision_aid.evaluation.full import (
    capture_snapshots,
    execute_full_evaluation,
    load_full_inputs,
    prepare_full_evaluation,
    report_full_evaluation,
)
from vision_aid.evaluation.human_finding_mapping import select_human_finding_mapping
from vision_aid.evaluation.human_finding_mapping_review import (
    approve_human_finding_mapping_review,
    prepare_human_finding_mapping_review,
)
from vision_aid.evaluation.inputs.human_audit import import_page_human_findings
from vision_aid.evaluation.page import prepare_page, report_page

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HUMAN_AUDIT = PROJECT_ROOT / "Pristine Accessibility Defect Report.xlsx"


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    """Add the options `run` and `run-all` share."""
    parser.add_argument(
        "--model", choices=MODEL_PRESETS, default=DEFAULT_MODEL,
        help=f"model preset (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT)
    parser.add_argument(
        "--human-finding-mapping", type=Path,
        help="approved mapping JSON from human-finding-mapping-approve",
    )
    parser.add_argument(
        "--max-cost-usd", required=True,
        help="spending limit, checked between requests",
    )
    parser.add_argument("--live", action="store_true", help="call the model (costs money)")
    parser.add_argument(
        "--approve-live", action="store_true",
        help="skip the confirmation prompt; requires --live",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the visionaid-evaluate argument parser."""
    parser = argparse.ArgumentParser(prog="visionaid-evaluate")
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture", help="download each page listed in the audit")
    capture.add_argument("--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT)
    capture.add_argument("--output-dir", type=Path, required=True)

    prepare = commands.add_parser(
        "human-finding-mapping-prepare", help="write the mapping review CSVs",
    )
    prepare.add_argument("--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT)
    prepare.add_argument("--snapshots", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)

    approve = commands.add_parser(
        "human-finding-mapping-approve", help="validate the review CSVs and write the mapping",
    )
    approve.add_argument("--human-audit", type=Path, default=DEFAULT_HUMAN_AUDIT)
    approve.add_argument("--snapshots", type=Path, required=True)
    approve.add_argument("--review-dir", type=Path, required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument(
        "--output", type=Path,
        help="defaults to REVIEW_DIR/human-finding-mapping.json",
    )

    run = commands.add_parser("run", help="preview or run one page")
    _add_model_options(run)
    run.add_argument("--html", type=Path, required=True, help="saved page HTML")
    run.add_argument("--source-url", required=True, help="URL the HTML came from")

    run_all = commands.add_parser("run-all", help="preview or run every listed page")
    _add_model_options(run_all)
    run_all.add_argument(
        "--snapshots", type=Path, required=True, help="snapshots.json from capture",
    )

    for name, help_text in (
        ("report", "validate one page's review and write its report"),
        ("report-all", "validate every page's review and write all reports"),
    ):
        report = commands.add_parser(name, help=help_text)
        report.add_argument("--run-dir", type=Path, required=True)
        report.add_argument("--reviewer", required=True, help="who did the review")
    return parser


def _new_run_directory(kind: str = "runs") -> Path:
    """Create a fresh run directory under .model-evaluation/ in the repository root."""
    current = Path.cwd()
    repo = next(
        (parent for parent in (current, *current.parents) if (parent / ".git").exists()),
        current,
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run = repo / ".model-evaluation" / kind / run_id
    run.mkdir(parents=True)
    return run


def _required_human_finding_mapping(path: Path | None, audit_sha256: str) -> dict[str, Any]:
    """Load the approved mapping, which every new run needs."""
    mapping = select_human_finding_mapping(path, audit_sha256)
    if mapping is None:
        raise ValueError(
            "No approved Human finding mapping. Create one with "
            "human-finding-mapping-prepare and human-finding-mapping-approve, "
            "then pass --human-finding-mapping PATH."
        )
    return mapping


def _approved_api_key(args: argparse.Namespace, configuration: dict[str, Any]) -> str | None:
    """Return the provider's API key, or None if the user declines to spend."""
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
    """Print the model settings, prices, and cost limit before any spending."""
    print(
        f"Model: {request_config.model}; provider: {configuration['provider']}; "
        f"endpoint: {configuration['endpoint']}; "
        f"thinking: {configuration.get('thinking', {}).get('type', 'none')}; "
        f"effort: {request_config.reasoning_effort or 'omitted'}; "
        f"output cap: {request_config.max_output_tokens}; prompts: {prompt_count}"
    )
    print(f"Pricing: {schedule.version} ({schedule.identity})")
    rates = schedule.data["models"][request_config.model]
    tiers = [("", rates)]
    if "long_context" in rates:
        upper = rates["long_context"]
        threshold = upper["above_input_tokens"]
        tiers = [(f" (up to {threshold:,} input tokens)", rates),
                 (f" (above {threshold:,} input tokens)", upper)]
    for label, tier in tiers:
        print(
            f"Rates per million tokens (USD){label}: "
            f"input ${tier['input_per_million_usd']}; "
            f"output ${tier['output_per_million_usd']}; "
            f"cache read ${tier['cached_input_per_million_usd']}; "
            f"cache write ${tier['cache_creation_input_per_million_usd']}"
        )
    print(f"Cost guardrail: ${limit}; checked between requests")


def _run(args: argparse.Namespace) -> int:
    """Prepare one page, then execute it if --live is set and approved."""
    request_config = MODEL_PRESETS[args.model]
    configuration = evaluation_configuration(request_config)
    limit = positive_cost(args.max_cost_usd)
    if not args.html.is_file():
        raise ValueError(f"Benchmark HTML not found: {args.html}")
    human_audit = import_page_human_findings(args.human_audit, args.source_url)
    mapping = _required_human_finding_mapping(
        args.human_finding_mapping, human_audit.human_audit_sha256
    )
    run = _new_run_directory()
    manifest = prepare_page(
        run, args.html, args.source_url, human_audit, request_config, limit, mapping
    )
    print(f"Evaluation run: {run}")
    _display_model(
        request_config, configuration, PriceSchedule.load(run / "artifacts/pricing.json"),
        len(manifest["prompts"]), limit,
    )
    print(f"Human findings: {len(human_audit.human_findings)}")
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


def _run_all(args: argparse.Namespace) -> int:
    """Prepare every listed page, then execute them all after one approval."""
    request_config = MODEL_PRESETS[args.model]
    limit = positive_cost(args.max_cost_usd)
    audits, snapshots = load_full_inputs(args.human_audit, args.snapshots)
    mapping = _required_human_finding_mapping(
        args.human_finding_mapping, next(iter(audits.values())).human_audit_sha256
    )
    run = _new_run_directory("full-runs")
    print(f"Full evaluation: {run}")
    manifest = prepare_full_evaluation(run, audits, snapshots, request_config, limit, mapping)
    prompt_count = 0
    for page in manifest["pages"]:
        child = run / page["run_dir"]
        prompt_count += len(json.loads((child / "run.json").read_text())["prompts"])
        print(f"Page: {page['source_url']}; Evaluation run: {child}")
        print(f"Review CSV: {child / 'review.csv'}")
    first_child = run / manifest["pages"][0]["run_dir"]
    _display_model(
        request_config, manifest["configuration"],
        PriceSchedule.load(first_child / "artifacts/pricing.json"), prompt_count, limit,
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "approve_live", False) and not args.live:
            raise ValueError("--approve-live requires --live")
        if args.command == "capture":
            print(f"Snapshot mapping: {capture_snapshots(args.human_audit, args.output_dir)}")
        elif args.command == "human-finding-mapping-prepare":
            prepare_human_finding_mapping_review(args.human_audit, args.snapshots, args.output_dir)
            print(f"Mapping review CSVs: {args.output_dir.resolve()}")
        elif args.command == "human-finding-mapping-approve":
            mapping = approve_human_finding_mapping_review(
                args.review_dir, args.human_audit, args.snapshots, args.reviewer, args.output,
            )
            print(f"Approved Human finding mapping: {mapping.resolve()}")
        elif args.command == "run":
            return _run(args)
        elif args.command == "run-all":
            return _run_all(args)
        elif args.command == "report":
            run = args.run_dir.resolve()
            report_page(run, args.reviewer)
            print(f"HTML report: {run / 'report.html'}")
        else:
            run = args.run_dir.resolve()
            report_full_evaluation(run, args.reviewer)
            print(f"Combined HTML report: {run / 'report.html'}")
        return 0
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
