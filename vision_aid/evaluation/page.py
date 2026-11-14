"""Prepare, validate, and report one page run."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from entry_points.run_pipeline import run_pipeline
from vision_aid.evaluation.execution.llm_audit import (
    USAGE_KEYS,
    LLMRequestConfig,
    evaluation_configuration,
    write_json,
)
from vision_aid.evaluation.execution.normalization import (
    normalize_programmatic_findings,
)
from vision_aid.evaluation.execution.pricing import DEFAULT_SCHEDULE, PriceSchedule
from vision_aid.evaluation.human_finding_mapping import (
    HUMAN_FINDING_MAPPING_ARTIFACT,
    apply_human_finding_mapping,
    load_human_finding_mapping,
    resolved_decisions,
)
from vision_aid.evaluation.reporting.html_report import write_page_report
from vision_aid.evaluation.review import create_review, reviewed_rows
from vision_aid.evaluation.schemas import HumanAudit


@dataclass(frozen=True)
class PageReview:
    """A completed page run with its validated review."""

    manifest: dict[str, Any]
    rows: list[dict[str, Any]]
    llm: list[dict[str, Any]]
    programmatic: list[dict[str, Any]]
    schedule: PriceSchedule


def prepare_page(
    run: Path,
    html: Path,
    source_url: str,
    human_audit: HumanAudit,
    request_config: LLMRequestConfig,
    limit: Decimal,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """Save a page's snapshot, checker results, prompts, and blank review.

    Makes no model requests. `run` must already exist and be empty.
    """
    artifacts = run / "artifacts"
    artifacts.mkdir()
    shutil.copyfile(html, run / "snapshot.html")
    shutil.copyfile(DEFAULT_SCHEDULE, artifacts / "pricing.json")
    human = human_audit.to_dict()
    write_json(artifacts / "human-findings.json", human)
    production = run_pipeline(
        html_path=str(run / "snapshot.html"),
        output_dir=artifacts,
        api_key=None,
        model=request_config.model,
        dry_run=True,
        include_summaries=False,
        request_config=request_config,
    )
    (artifacts / "manifest.json").unlink()
    raw_path = artifacts / "programmatic_findings.json"
    raw_programmatic = json.loads(raw_path.read_text())
    raw_path.rename(artifacts / "raw-programmatic-findings.json")
    programmatic = [
        asdict(item) for item in normalize_programmatic_findings(
            raw_programmatic, run_id=run.name, page_url=source_url,
        )
    ]
    write_json(artifacts / "normalized-programmatic-findings.json", programmatic)
    create_review(run / "review.csv", list(human["human_findings"]))
    schedule = PriceSchedule.load(artifacts / "pricing.json")
    manifest = {
        "run_id": run.name,
        "source_url": source_url,
        "human_audit_filename": human_audit.human_audit_filename,
        "human_audit_sha256": human_audit.human_audit_sha256,
        "snapshot_sha256": hashlib.sha256((run / "snapshot.html").read_bytes()).hexdigest(),
        "configuration": evaluation_configuration(request_config),
        "pricing_version": schedule.version,
        "pricing_sha256": schedule.identity,
        "max_cost_usd": str(limit),
        "complete": False,
        "incomplete_reason": "preview",
        "estimated_cost_usd": "0",
        "usage": {key: 0 for key in USAGE_KEYS},
        "format_failures": [],
        "prompts": [
            {"name": entry["name"], "checklist": entry["checklist"]}
            for entry in production["prompts_dry_run"]
        ],
        "filters": production["pass1_filters_active"],
        "skipped_prompts": production["prompts_skipped"],
    }
    apply_human_finding_mapping(run, manifest, human, programmatic, mapping)
    write_json(run / "run.json", manifest)
    (run / "README.md").write_text(
        "# Review this page run\n\n"
        "`run.json` says whether the run completed. A run without `--live` is a "
        "preview and has no model output to review.\n\n"
        "1. Compare `normalized-llm-findings.json` with the human findings in "
        "`review.csv`. Check `snapshot.html` if you need the page itself.\n"
        "2. Fill in `llm_finding_id`, `match_reason`, and `review_notes`. Separate "
        "several IDs with semicolons, and leave the ID blank for a miss. Don't "
        "change the other columns.\n"
        "3. Generate the report from the repository root:\n\n"
        "```bash\n"
        f"uv run visionaid-evaluate report --run-dir {shlex.quote(str(run.resolve()))} "
        '--reviewer "Your name and review method"\n'
        "```\n",
        encoding="utf-8",
    )
    return manifest


def validated_page_review(run: Path) -> PageReview:
    """Load a completed page run and validate its review.csv."""
    run = run.resolve()
    artifacts = run / "artifacts"
    manifest = json.loads((run / "run.json").read_text())
    if not manifest["complete"]:
        raise ValueError("Incomplete Evaluation runs cannot produce a final report")
    human_audit = json.loads((artifacts / "human-findings.json").read_text())
    llm = json.loads((run / "normalized-llm-findings.json").read_text())
    programmatic = json.loads((artifacts / "normalized-programmatic-findings.json").read_text())
    mapping = load_human_finding_mapping(run / HUMAN_FINDING_MAPPING_ARTIFACT, manifest["human_audit_sha256"])
    approved = resolved_decisions(mapping, human_audit, manifest["source_url"], programmatic)
    rows = reviewed_rows(
        run / "review.csv", human_audit["human_findings"], llm, programmatic, approved
    )
    schedule = PriceSchedule.load(artifacts / "pricing.json")
    return PageReview(manifest, rows, llm, programmatic, schedule)


def report_page(run: Path, reviewer: str) -> PageReview:
    """Validate the review and write the page report."""
    (run / "report.html").unlink(missing_ok=True)
    if not reviewer.strip():
        raise ValueError("A reviewer description is required")
    review = validated_page_review(run)
    write_page_report(run / "report.html", review, reviewer)
    return review
