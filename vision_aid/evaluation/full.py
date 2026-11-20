"""Capture snapshots and prepare, run, and report full evaluations."""

from __future__ import annotations

import hashlib
import json
import shlex
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from vision_aid.evaluation.execution.llm_audit import (
    USAGE_KEYS,
    LLMRequestConfig,
    evaluation_configuration,
    execute,
    write_json,
)
from vision_aid.evaluation.human_finding_mapping import (
    save_human_finding_mapping_snapshot,
    validate_human_finding_mapping,
)
from vision_aid.evaluation.inputs.human_audit import (
    import_all_human_findings,
    list_audit_urls,
)
from vision_aid.evaluation.page import PageReview, prepare_page, validated_page_review
from vision_aid.evaluation.reporting.html_report import (
    write_full_report,
    write_page_report,
)
from vision_aid.evaluation.schemas import HumanAudit


def capture_snapshots(human_audit: Path, output_dir: Path) -> Path:
    """Download each listed page, writing snapshots.json only if all succeed."""
    urls = list_audit_urls(human_audit)
    audit_checksum = hashlib.sha256(human_audit.read_bytes()).hexdigest()
    output_dir.mkdir(parents=True)
    snapshots = []
    for number, source_url in enumerate(urls, start=1):
        response = requests.get(source_url, allow_redirects=True)
        response.raise_for_status()
        html = f"page-{number:03d}.html"
        (output_dir / html).write_bytes(response.content)
        snapshots.append({"source_url": source_url, "html": html})
    mapping = output_dir / "snapshots.json"
    write_json(mapping, {
        "human_audit_filename": human_audit.name,
        "human_audit_sha256": audit_checksum,
        "snapshots": snapshots,
    })
    return mapping


def load_full_inputs(
    human_audit: Path, mapping_path: Path,
) -> tuple[dict[str, HumanAudit], dict[str, Path]]:
    """Load the audit's pages and check they match snapshots.json."""
    audits = import_all_human_findings(human_audit)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    checksum = next(iter(audits.values())).human_audit_sha256
    if not isinstance(mapping, dict) or mapping.get("human_audit_sha256") != checksum:
        raise ValueError(
            "Snapshot mapping Human audit identity differs from the supplied audit"
        )
    entries = mapping.get("snapshots")
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict)
        or not isinstance(entry.get("source_url"), str)
        or not isinstance(entry.get("html"), str)
        for entry in entries
    ):
        raise ValueError(
            "Snapshot mapping must contain source URLs and relative HTML filenames"
        )
    if [entry["source_url"] for entry in entries] != list(audits):
        raise ValueError(
            "Snapshot mapping must match every listed target once in source order"
        )
    snapshots = {}
    directory = mapping_path.parent.resolve()
    for entry in entries:
        filename = Path(entry["html"])
        html = (directory / filename).resolve()
        if filename.is_absolute() or not html.is_relative_to(directory):
            raise ValueError(
                "Snapshot mapping HTML files must be relative files beside the mapping"
            )
        if not html.is_file():
            raise ValueError(f"Snapshot mapping Benchmark HTML not found: {filename}")
        snapshots[entry["source_url"]] = html
    return audits, snapshots


def prepare_full_evaluation(
    run: Path,
    audits: dict[str, HumanAudit],
    snapshots: dict[str, Path],
    request_config: LLMRequestConfig,
    limit: Decimal,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """Prepare a page run for every listed page, recording progress in full.json."""
    first_audit = next(iter(audits.values()))
    pages = []
    originals = {}
    assignments = {}
    for number, (source_url, audit) in enumerate(audits.items(), start=1):
        child_id = f"{run.name}-page-{number:03d}-{uuid.uuid4().hex[:8]}"
        human_ids = []
        for finding in audit.to_dict()["human_findings"]:
            identity = finding["human_finding_id"]
            originals[identity] = finding
            human_ids.append(identity)
            if finding["page_scope"] != "global":
                assignments[identity] = source_url
        pages.append({
            "source_url": source_url,
            "run_id": child_id,
            "run_dir": f"pages/{child_id}",
            "human_finding_ids": human_ids,
            "status": "unprepared",
            "complete": False,
        })
    manifest = {
        "run_id": run.name,
        "human_audit_filename": first_audit.human_audit_filename,
        "human_audit_sha256": first_audit.human_audit_sha256,
        "configuration": evaluation_configuration(request_config),
        "max_cost_usd": str(limit),
        "estimated_cost_usd": "0",
        "usage": {key: 0 for key in USAGE_KEYS},
        "complete": False,
        "incomplete_reason": "preparing pages",
        "pages": pages,
    }
    validate_human_finding_mapping(mapping, first_audit.human_audit_sha256)
    if {item["human_finding_id"] for item in mapping["decisions"]} != set(originals):
        raise ValueError(
            "Human finding mapping must contain each original Human finding exactly once"
        )
    write_json(run / "human-findings.json", {
        "human_audit_filename": first_audit.human_audit_filename,
        "human_audit_sha256": first_audit.human_audit_sha256,
        "human_findings": sorted(originals.values(), key=lambda item: item["source_row"]),
        "page_assignments": assignments,
        "source_urls": list(audits),
    })
    save_human_finding_mapping_snapshot(run, manifest, mapping)
    write_json(run / "full.json", manifest)
    (run / "README.md").write_text(
        "# Review this full evaluation\n\n"
        "`full.json` lists the page directories and says whether the run completed. "
        "A run without `--live` is a preview and has no model output to review.\n\n"
        "1. Open each directory under `pages/` and follow its README to fill in "
        "`review.csv`. Global findings appear on every page, so review them on each.\n"
        "2. Generate all the reports from the repository root:\n\n"
        "```bash\n"
        f"uv run visionaid-evaluate report-all --run-dir {shlex.quote(str(run.resolve()))} "
        '--reviewer "Your name and review method"\n'
        "```\n\n"
        "The combined report is this directory's `report.html`. Each page also gets "
        "its own.\n",
        encoding="utf-8",
    )
    for page in pages:
        child = run / page["run_dir"]
        try:
            child.mkdir(parents=True)
            child_manifest = prepare_page(
                child, snapshots[page["source_url"]], page["source_url"],
                audits[page["source_url"]], request_config, limit, mapping,
            )
        except (OSError, ValueError, KeyError) as error:
            page["status"] = "preparation_failed"
            manifest["incomplete_reason"] = (
                f"page preparation failed for {page['source_url']}: {error}"
            )
            write_json(run / "full.json", manifest)
            raise
        page.update(
            status="prepared", snapshot_sha256=child_manifest["snapshot_sha256"]
        )
        write_json(run / "full.json", manifest)
    manifest["incomplete_reason"] = "preview"
    write_json(run / "full.json", manifest)
    return manifest


def _stop_full_evaluation(
    run: Path, manifest: dict[str, Any], reason: str, unfinished: list[dict[str, Any]],
) -> bool:
    """Record why execution stopped and mark the remaining pages as not run."""
    manifest["incomplete_reason"] = reason
    for page in unfinished:
        page["status"] = "not_executed"
    write_json(run / "full.json", manifest)
    return False


def execute_full_evaluation(
    run: Path, manifest: dict[str, Any], api_key: str,
    request_config: LLMRequestConfig,
) -> bool:
    """Run each page in order, passing the remaining cost allowance to the next."""
    total_cost = Decimal(0)
    usage = {key: 0 for key in USAGE_KEYS}
    limit = Decimal(manifest["max_cost_usd"])
    pages = manifest["pages"]
    manifest["incomplete_reason"] = None
    for number, page in enumerate(pages):
        remaining = limit - total_cost
        if remaining <= 0:
            return _stop_full_evaluation(
                run, manifest, "cost guardrail exhausted before next page", pages[number:]
            )
        child = run / page["run_dir"]
        child_manifest = json.loads((child / "run.json").read_text())
        child_manifest["max_cost_usd"] = str(remaining)
        write_json(child / "run.json", child_manifest)
        try:
            complete = execute(child, child_manifest, api_key, request_config)
        except Exception as error:
            # Provider setup can fail before the executor saves a request outcome.
            child_manifest.update(complete=False, incomplete_reason=str(error))
            write_json(child / "run.json", child_manifest)
            complete = False
        total_cost += Decimal(child_manifest["estimated_cost_usd"])
        for key in USAGE_KEYS:
            usage[key] += child_manifest["usage"][key]
        page.update(status="complete" if complete else "incomplete", complete=complete)
        manifest.update(estimated_cost_usd=str(total_cost), usage=usage)
        if not complete:
            return _stop_full_evaluation(
                run, manifest,
                f"page execution failed for {page['source_url']}: "
                f"{child_manifest['incomplete_reason']}",
                pages[number + 1:],
            )
        write_json(run / "full.json", manifest)
    manifest.update(complete=True, incomplete_reason=None)
    write_json(run / "full.json", manifest)
    return True


def _pooled_rows(
    originals: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    reviews: list[PageReview],
) -> list[dict[str, Any]]:
    """Combine page rows so each original finding appears once.

    A finding counts as caught by a source if that source caught it on any page.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for page, review in zip(pages, reviews, strict=True):
        for row in review.rows:
            grouped.setdefault(row["human_finding"]["human_finding_id"], []).append({
                "source_url": page["source_url"],
                "decision": row["decision"],
                "matches": row["matches"],
            })
    pooled = []
    for finding in originals:
        page_rows = grouped[finding["human_finding_id"]]
        pooled.append({
            "human_finding": finding,
            "decision": {"classification": page_rows[0]["decision"]["classification"].strip()},
            "matches": {
                kind: tuple(identity for row in page_rows for identity in row["matches"][kind])
                for kind in ("llm", "programmatic")
            },
            "page_reviews": page_rows,
        })
    return pooled


def report_full_evaluation(run: Path, reviewer: str) -> None:
    """Validate every page review, then write the page and combined reports."""
    if not reviewer.strip():
        raise ValueError("A reviewer description is required")
    run = run.resolve()
    # Remove the old report first so a failed validation can't leave it looking current.
    (run / "report.html").unlink(missing_ok=True)
    manifest = json.loads((run / "full.json").read_text())
    if not manifest["complete"]:
        raise ValueError("Incomplete Full evaluations cannot produce a final report")
    original = json.loads((run / "human-findings.json").read_text())
    reviews = [validated_page_review(run / page["run_dir"]) for page in manifest["pages"]]
    rows = _pooled_rows(original["human_findings"], manifest["pages"], reviews)
    for page, review in zip(manifest["pages"], reviews, strict=True):
        write_page_report(run / page["run_dir"] / "report.html", review, reviewer)
    write_full_report(run / "report.html", manifest, rows, reviews, reviewer)
