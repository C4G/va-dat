"""Coordinate Full evaluation preparation and saved Benchmark snapshots."""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from vision_aid.evaluation.baseline import (
    BASELINE_ARTIFACT,
    load_baseline_snapshot,
    save_baseline_snapshot,
    validate_baseline,
)
from vision_aid.evaluation.execution.llm_audit import (
    USAGE_KEYS,
    LLMRequestConfig,
    evaluation_configuration,
    execute,
    write_json,
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
    """Download only listed pages and publish their mapping after all succeed."""
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
    """Load listed page assignments and saved snapshots without downloading."""
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
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare all listed pages, retaining membership and progress on failure."""
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
    write_json(run / "human-findings.json", {
        "human_audit_filename": first_audit.human_audit_filename,
        "human_audit_sha256": first_audit.human_audit_sha256,
        "human_findings": sorted(originals.values(), key=lambda item: item["source_row"]),
        "page_assignments": assignments,
        "source_urls": list(audits),
    })
    write_json(run / "full.json", manifest)
    if baseline is not None:
        save_full_baseline(run, baseline)
        manifest = json.loads((run / "full.json").read_text())
        pages = manifest["pages"]
    for page in pages:
        child = run / page["run_dir"]
        try:
            child.mkdir(parents=True)
            child_manifest = prepare_page(
                child, snapshots[page["source_url"]], page["source_url"],
                audits[page["source_url"]], request_config, limit, baseline,
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


def save_full_baseline(run: Path, baseline: dict[str, Any]) -> None:
    """Pin the approved source shared by all children during preparation."""
    manifest = json.loads((run / "full.json").read_text())
    validate_baseline(baseline, manifest["human_audit_sha256"])
    original = json.loads((run / "human-findings.json").read_text())
    if {item["human_finding_id"] for item in baseline["decisions"]} != {
        item["human_finding_id"] for item in original["human_findings"]
    }:
        raise ValueError("Full evaluation Human finding mapping must contain each original Human finding exactly once")
    save_baseline_snapshot(run, manifest, baseline)
    write_json(run / "full.json", manifest)


def execute_full_evaluation(
    run: Path, manifest: dict[str, Any], api_key: str,
    request_config: LLMRequestConfig,
) -> bool:
    """Execute prepared pages sequentially with one remaining cost allowance."""
    total_cost = Decimal(0)
    usage = {key: 0 for key in USAGE_KEYS}
    limit = Decimal(manifest["max_cost_usd"])
    manifest["incomplete_reason"] = None
    for number, page in enumerate(manifest["pages"]):
        remaining = limit - total_cost
        if remaining <= 0:
            manifest["incomplete_reason"] = "cost guardrail exhausted before next page"
            for unfinished in manifest["pages"][number:]:
                unfinished["status"] = "not_executed"
            write_json(run / "full.json", manifest)
            return False
        child = run / page["run_dir"]
        child_manifest = json.loads((child / "run.json").read_text())
        child_manifest["max_cost_usd"] = str(remaining)
        write_json(child / "run.json", child_manifest)
        try:
            complete = execute(child, child_manifest, api_key, request_config)
        except Exception as error:  # noqa: BLE001
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
            manifest["incomplete_reason"] = (
                f"page execution failed for {page['source_url']}: "
                f"{child_manifest['incomplete_reason']}"
            )
            for unfinished in manifest["pages"][number + 1:]:
                unfinished["status"] = "not_executed"
        write_json(run / "full.json", manifest)
        if not complete:
            return False
    manifest.update(complete=True, incomplete_reason=None)
    write_json(run / "full.json", manifest)
    return True


def _pooled_rows(
    originals: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    reviews: list[PageReview],
) -> list[dict[str, Any]]:
    """Keep each original once, using complete source matches on any one page."""
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
        classifications = {
            row["decision"]["classification"].strip() for row in page_rows
            if row["decision"]["classification"].strip() in {"llm_eligible", "programmatic"}
        }
        if len(classifications) > 1:
            raise ValueError(
                f"Global Human finding {finding['human_finding_id']} has conflicting "
                "testable classifications; all testable pages must agree"
            )
        classification = (
            next(iter(classifications)) if classifications
            else page_rows[0]["decision"]["classification"].strip()
        )
        pooled.append({
            "human_finding": finding,
            "decision": {"classification": classification},
            "matches": {
                kind: tuple(identity for row in page_rows for identity in row["matches"][kind])
                for kind in ("llm", "programmatic")
            },
            "page_reviews": page_rows,
        })
    return pooled


def _validated_full_reviews(
    run: Path, manifest: dict[str, Any], original: dict[str, Any],
) -> list[PageReview]:
    """Check ordered membership, original evidence and ownership for every child."""
    if manifest["run_id"] != run.name:
        raise ValueError("Full evaluation evidence does not belong to this directory")
    if not manifest["complete"]:
        raise ValueError("Incomplete Full evaluations cannot produce a final report")
    urls = original["source_urls"]
    if not urls or len(urls) != len(set(urls)) or [
        page["source_url"] for page in manifest["pages"]
    ] != urls:
        raise ValueError("Full evaluation membership differs from the original ordered targets")
    if original["human_audit_sha256"] != manifest["human_audit_sha256"]:
        raise ValueError("Human audit identity differs from the Full evaluation")
    findings = original["human_findings"]
    identities = [item["human_finding_id"] for item in findings]
    if not identities or len(identities) != len(set(identities)):
        raise ValueError("Full evaluation must preserve each original Human finding once")
    assignments = original["page_assignments"]
    locals_ = {item["human_finding_id"] for item in findings if item["page_scope"] != "global"}
    if set(assignments) != locals_ or any(url not in urls for url in assignments.values()):
        raise ValueError("Full evaluation has invalid original page assignments")
    baseline_path = run / BASELINE_ARTIFACT
    baseline_digest = manifest.get("evaluation_baseline_sha256")
    if baseline_digest:
        baseline = load_baseline_snapshot(run, manifest, "Saved Full evaluation Human finding mapping")
        if {item["human_finding_id"] for item in baseline["decisions"]} != set(identities):
            raise ValueError("Full evaluation Human finding mapping differs from original Human findings")
    elif baseline_path.exists():
        raise ValueError("Saved Full evaluation Human finding mapping is missing its parent identity")
    reviews = []
    child_ids: set[str] = set()
    tool_ids: set[str] = set()
    for page in manifest["pages"]:
        child = (run / page["run_dir"]).resolve()
        if (
            page["run_id"] in child_ids
            or page["run_dir"] != f"pages/{page['run_id']}"
            or child.parent != run / "pages"
            or child.name != page["run_id"]
        ):
            raise ValueError("Child Evaluation run identity or directory ownership differs")
        child_ids.add(page["run_id"])
        if not page["complete"] or page["status"] != "complete":
            raise ValueError("Every listed page must complete execution before combined reporting")
        expected = [
            item for item in findings if item["page_scope"] == "global"
            or assignments[item["human_finding_id"]] == page["source_url"]
        ]
        if page["human_finding_ids"] != [item["human_finding_id"] for item in expected]:
            raise ValueError("Child Human finding membership differs from its original assignments")
        evidence = json.loads((child / "artifacts/human-findings.json").read_text())
        if evidence["human_findings"] != expected or evidence["homepage_url"] != page["source_url"]:
            raise ValueError("Child Human finding evidence differs from the original page selection")
        review = validated_page_review(child)
        saved = review.manifest
        if saved.get("evaluation_baseline_sha256") != baseline_digest:
            raise ValueError(f"Child Human finding mapping differs from the Full evaluation: {page['source_url']}")
        for field, expected_value in (
            ("run_id", page["run_id"]), ("source_url", page["source_url"]),
            ("human_audit_sha256", manifest["human_audit_sha256"]),
            ("configuration", manifest["configuration"]),
            ("snapshot_sha256", page["snapshot_sha256"]),
        ):
            if saved[field] != expected_value:
                raise ValueError(f"Child {field} differs from the Full evaluation")
        if hashlib.sha256((child / "snapshot.html").read_bytes()).hexdigest() != saved["snapshot_sha256"]:
            raise ValueError("Child Benchmark snapshot checksum differs from the saved evidence")
        if review.schedule.identity != saved["pricing_sha256"] or review.schedule.version != saved["pricing_version"]:
            raise ValueError("Child pricing evidence differs from its recorded schedule")
        for filename in ("raw-llm-responses.json", "raw-programmatic-findings.json"):
            json.loads((child / "artifacts" / filename).read_text())
        for prompt in saved["prompts"]:
            json.loads((child / "artifacts/prompts" / f"{prompt['name']}.json").read_text())
        if any(item["model"] != manifest["configuration"]["model"] for item in review.llm):
            raise ValueError("LLM findings do not belong to the selected model")
        ids = [item["finding_id"] for item in review.llm + review.programmatic]
        if len(ids) != len(set(ids)) or tool_ids.intersection(ids):
            raise ValueError("Tool finding identities must be unique across all page runs")
        tool_ids.update(ids)
        reviews.append(review)
    cost = sum((Decimal(review.manifest["estimated_cost_usd"]) for review in reviews), Decimal(0))
    usage = {key: sum(review.manifest["usage"][key] for review in reviews) for key in USAGE_KEYS}
    if cost != Decimal(manifest["estimated_cost_usd"]) or usage != manifest["usage"]:
        raise ValueError("Full evaluation totals differ from authoritative child cost and usage")
    return reviews


def report_full_evaluation(run: Path, reviewer: str) -> None:
    """Validate every page review before writing page and combined reports."""
    if not reviewer.strip():
        raise ValueError("A reviewer description is required")
    run = run.resolve()
    # Regeneration cannot leave a previous final report beside invalid decisions.
    (run / "report.html").unlink(missing_ok=True)
    (run / "report.md").unlink(missing_ok=True)
    manifest = json.loads((run / "full.json").read_text())
    original = json.loads((run / "human-findings.json").read_text())
    reviews = _validated_full_reviews(run, manifest, original)
    rows = _pooled_rows(original["human_findings"], manifest["pages"], reviews)
    for page, review in zip(manifest["pages"], reviews, strict=True):
        child = run / page["run_dir"]
        write_page_report(child / "report.html", review, reviewer)
        (child / "report.md").unlink(missing_ok=True)
    write_full_report(run / "report.html", manifest, rows, reviews, reviewer)
