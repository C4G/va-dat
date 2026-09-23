"""Run one private Haiku evaluation, then score a human-edited CSV."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from entry_points.run_pipeline import run_pipeline
from vision_aid.evaluation.audit import (
    CONFIGURATION,
    MODEL,
    REQUEST_CONFIG,
    execute,
    positive_cost,
    write_json,
)
from vision_aid.evaluation.normalization import normalize_programmatic_findings
from vision_aid.evaluation.pricing import DEFAULT_SCHEDULE, PriceSchedule
from vision_aid.evaluation.references import import_homepage_references
from vision_aid.evaluation.review import create_review, reviewed_rows, write_report

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKBOOK = PROJECT_ROOT / "Pristine Accessibility Defect Report.xlsx"


def build_parser() -> argparse.ArgumentParser:
    """Expose the two supported evaluation operations."""
    parser = argparse.ArgumentParser(prog="visionaid-evaluate")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="preview or execute the fixed Haiku experiment"
    )
    run.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    run.add_argument("--html", type=Path, required=True, help="local Benchmark HTML")
    run.add_argument("--source-url", required=True, help="URL represented by the HTML")
    run.add_argument(
        "--max-cost-usd", required=True, help="positive between-request limit"
    )
    run.add_argument("--live", action="store_true", help="enable billable execution")
    run.add_argument(
        "--approve-live",
        action="store_true",
        help="explicitly approve billable execution without a prompt",
    )
    report = commands.add_parser(
        "report", help="score completed run and edited review.csv"
    )
    report.add_argument("--run-dir", type=Path, required=True)
    return parser


def _new_run_directory() -> Path:
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
    root = worktree / ".model-evaluation" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run = root / run_id
    run.mkdir()
    return run


def _run(args: argparse.Namespace) -> int:
    """Prepare a fresh run and execute only after explicit approval."""
    limit = positive_cost(args.max_cost_usd)
    if args.approve_live and not args.live:
        raise ValueError("--approve-live requires --live")
    if not args.html.is_file():
        raise ValueError(f"Benchmark HTML not found: {args.html}")
    references = import_homepage_references(args.workbook, args.source_url)
    run = _new_run_directory()
    shutil.copyfile(args.html, run / "snapshot.html")
    shutil.copyfile(DEFAULT_SCHEDULE, run / "pricing.json")
    snapshot_hash = hashlib.sha256((run / "snapshot.html").read_bytes()).hexdigest()
    write_json(run / "references.json", references.to_dict())
    production = run_pipeline(
        html_path=str(run / "snapshot.html"),
        output_dir=run,
        api_key=None,
        model=MODEL,
        dry_run=True,
        include_summaries=False,
        request_config=REQUEST_CONFIG,
    )
    (run / "manifest.json").unlink()
    raw_programmatic = json.loads((run / "programmatic_findings.json").read_text())
    findings = normalize_programmatic_findings(
        raw_programmatic,
        run_id=run.name,
        page_url=args.source_url,
    )
    write_json(run / "programmatic-findings.json", [asdict(item) for item in findings])
    create_review(run / "review.csv", list(references.to_dict()["references"]))
    schedule = PriceSchedule.load(run / "pricing.json")
    manifest = {
        "run_id": run.name,
        "source_url": args.source_url,
        "workbook_filename": references.workbook_filename,
        "workbook_sha256": references.workbook_sha256,
        "snapshot_sha256": snapshot_hash,
        "configuration": CONFIGURATION,
        "pricing_version": schedule.version,
        "pricing_sha256": schedule.identity,
        "max_cost_usd": str(limit),
        "complete": False,
        "incomplete_reason": "preview",
        "estimated_cost_usd": "0",
        "usage": {
            key: 0
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "cache_creation_input_tokens",
                "output_tokens",
            )
        },
        "format_failures": [],
        "prompts": [
            {"name": entry["name"], "checklist": entry["checklist"]}
            for entry in production["prompts_dry_run"]
        ],
        "filters": production["pass1_filters_active"],
        "skipped_prompts": production["prompts_skipped"],
    }
    write_json(run / "run.json", manifest)
    print(f"Evaluation run: {run}")
    print(
        f"Model: {MODEL}; endpoint: Messages; "
        f"thinking: {CONFIGURATION['thinking_budget_tokens']}; "
        f"output cap: {CONFIGURATION['max_output_tokens']}"
    )
    print(
        "Temperature: omitted; summaries: disabled; "
        f"prompts: {len(manifest['prompts'])}"
    )
    print(
        f"Snapshot SHA-256: {snapshot_hash}; "
        f"Reference rows: {len(references.references)}"
    )
    print(f"Pricing: {schedule.version} ({schedule.identity})")
    print(f"Cost guardrail: ${limit}; checked before each request")
    print(f"Review CSV: {run / 'review.csv'}")
    if not args.live:
        print("Preview complete; no paid requests made.")
        return 0
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Live execution requires ANTHROPIC_API_KEY")
    if not args.approve_live and (
        not sys.stdin.isatty()
        or input("Type 'yes' to approve paid execution: ") != "yes"
    ):
        print("Live execution declined; no paid requests made.")
        return 0
    complete = execute(run, manifest, api_key)
    print(f"Run {'complete' if complete else 'incomplete'}: {run}")
    return 0 if complete else 1


def _report(args: argparse.Namespace) -> int:
    """Validate human decisions and report a completed run."""
    run = args.run_dir.resolve()
    manifest = json.loads((run / "run.json").read_text())
    if manifest["run_id"] != run.name:
        raise ValueError("Run evidence does not belong to this directory")
    if not manifest["complete"]:
        raise ValueError("Incomplete Evaluation runs cannot produce a final report")
    reference_set = json.loads((run / "references.json").read_text())
    if reference_set["workbook_sha256"] != manifest["workbook_sha256"]:
        raise ValueError("Reference workbook identity differs from the run")
    audit = json.loads((run / "audit-findings.json").read_text())
    programmatic = json.loads((run / "programmatic-findings.json").read_text())
    for kind, collection in (("audit", audit), ("programmatic", programmatic)):
        if any(
            item["run_id"] != run.name
            or item["source"] != kind
            or item["page_url"] != manifest["source_url"]
            for item in collection
        ):
            raise ValueError(f"{kind} findings do not belong to this run")
    rows = reviewed_rows(
        run / "review.csv", reference_set["references"], audit, programmatic
    )
    write_report(run / "report.md", manifest, rows, audit, programmatic)
    print(f"Markdown report: {run / 'report.md'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the requested CLI operation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args) if args.command == "run" else _report(args)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
