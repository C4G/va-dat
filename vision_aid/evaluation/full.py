"""Coordinate Full evaluation preparation and saved Benchmark snapshots."""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from vision_aid.evaluation.human_audit import import_all_human_findings, list_audit_urls
from vision_aid.evaluation.llm_audit import (
    LLMRequestConfig, USAGE_KEYS, evaluation_configuration, write_json,
)
from vision_aid.evaluation.page import prepare_page
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
    })
    write_json(run / "full.json", manifest)
    for page in pages:
        child = run / page["run_dir"]
        try:
            child.mkdir(parents=True)
            child_manifest = prepare_page(
                child, snapshots[page["source_url"]], page["source_url"],
                audits[page["source_url"]], request_config, limit,
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
