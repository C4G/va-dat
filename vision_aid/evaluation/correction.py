"""Apply approved decisions to saved evidence after preserving original results."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from vision_aid.evaluation.baseline import (
    apply_baseline,
    resolved_decisions,
    select_baseline,
    validate_baseline,
)
from vision_aid.evaluation.full import report_full_evaluation, save_full_baseline


def _inventory(directory: Path) -> dict[str, str]:
    """Hash every saved file by its relative path for an independently checkable copy."""
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def preserve_run_history(run: Path) -> Path:
    """Make and verify one complete original backup, preserving it across retries."""
    history = run.parent / "review-history" / run.name
    if history.exists():
        inventory = json.loads((history / "inventory.json").read_text())
        if inventory.get("source_run") != str(run) or _inventory(
            history / "original"
        ) != inventory.get("files"):
            raise ValueError(
                f"Original backup failed verification: {history}; restore it before correction"
            )
        return history
    history.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{run.name}-", dir=history.parent))
    try:
        before = _inventory(run)
        shutil.copytree(run, staging / "original")
        if _inventory(staging / "original") != before or _inventory(run) != before:
            raise ValueError(
                "Saved evidence changed during backup; retry with the run held fixed"
            )
        inventory = {
            "source_run": str(run),
            "created_at": datetime.now(UTC).isoformat(),
            "files": before,
        }
        (staging / "inventory.json").write_text(
            json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(history)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return history


def _children(run: Path, manifest: dict[str, Any]) -> list[Path]:
    """Reject foreign child paths before correction can alter any review artifacts."""
    children = []
    for page in manifest["pages"]:
        child = (run / page["run_dir"]).resolve()
        if (
            page["run_dir"] != f"pages/{page['run_id']}"
            or child.parent != run / "pages"
            or child.name != page["run_id"]
            or child in children
        ):
            raise ValueError(
                "Child Evaluation run identity or directory ownership differs"
            )
        children.append(child)
    if not children:
        raise ValueError("Saved Full evaluation has no child pages")
    return children


def _incompatible_llm_decisions(
    child: Path,
    decisions: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Surface invalid retained LLM claims without changing any model-specific cell."""
    manifest = json.loads((child / "run.json").read_text())
    llm = json.loads((child / "normalized-llm-findings.json").read_text())
    known = {item["finding_id"] for item in llm}
    with (child / "review.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    used: set[str] = set()
    issues = []
    for row in rows:
        identity = row["human_finding_id"]
        if identity not in decisions:
            raise ValueError(f"Unknown Human finding in saved review: {identity}")
        ids = [
            part.strip() for part in row["llm_finding_id"].split(";") if part.strip()
        ]
        classification = decisions[identity]["classification"]
        reason = None
        if ids and classification in {"unavailable_evidence", "ambiguous"}:
            reason = "Approved classification is not testable; a saved LLM catch cannot claim coverage"
        elif set(ids) - known:
            reason = (
                "Saved LLM IDs do not belong to this page's normalized LLM findings"
            )
        elif len(ids) != len(set(ids)) or used.intersection(ids):
            reason = "Saved LLM finding ID is reused across or within Human findings"
        elif ids and not row["match_reason"].strip():
            reason = "Saved LLM catch needs a complete-match explanation"
        used.update(ids)
        if reason:
            issues.append(
                {
                    "run_dir": str(child),
                    "source_url": manifest["source_url"],
                    "human_finding_id": identity,
                    "human_problem": row["Issue Title"],
                    "approved_classification": classification,
                    "issue": reason,
                    "llm_finding_id": row["llm_finding_id"],
                    "match_reason": row["match_reason"],
                    "review_notes": row["review_notes"],
                }
            )
    return issues


def _original_reviewers(report: Path) -> list[str]:
    """Read recorded reviewer attribution from the preserved original HTML report."""
    if not report.is_file():
        return []
    document = BeautifulSoup(report.read_text(encoding="utf-8"), "html.parser")
    prefix = "Review decisions by:"
    return list(
        dict.fromkeys(
            text[len(prefix) :].strip()
            for paragraph in document.find_all("p")
            if (text := paragraph.get_text(" ", strip=True)).startswith(prefix)
            and text[len(prefix) :].strip()
        )
    )


def _record_correction(
    run: Path,
    children: list[Path],
    history: Path,
    reviewer: str,
    baseline: dict[str, Any],
) -> None:
    """Keep original LLM attribution separate from baseline approval and correction."""
    common = {
        "corrected_by": reviewer,
        "corrected_at": datetime.now(UTC).isoformat(),
        "baseline_approved_by": baseline["approved_by"],
        "original_backup": str(history),
        "backup_inventory_sha256": hashlib.sha256(
            (history / "inventory.json").read_bytes()
        ).hexdigest(),
    }
    parent_reviewers = _original_reviewers(history / "original/report.html")
    for directory, filename in [
        (run, "full.json"),
        *[(child, "run.json") for child in children],
    ]:
        relative_report = (directory / "report.html").relative_to(run)
        original_reviewers = _original_reviewers(history / "original" / relative_report)
        manifest_path = directory / filename
        manifest = json.loads(manifest_path.read_text())
        manifest["review_correction"] = {
            **common,
            "original_report": relative_report.as_posix(),
            "original_llm_reviewers": original_reviewers or parent_reviewers,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def correct_full_evaluation(
    run: Path, reviewer: str, baseline_path: Path | None = None
) -> Path:
    """Preserve originals, apply shared decisions and regenerate saved-run reports."""
    run = run.resolve()
    if not reviewer.strip():
        raise ValueError("A reviewer description is required")
    if not (run / "full.json").is_file():
        raise ValueError(f"Saved Full evaluation not found: {run}")
    history = preserve_run_history(run)
    # Only invalidate results after their original bytes have a verified backup.
    (run / "report.html").unlink(missing_ok=True)
    (run / "report.md").unlink(missing_ok=True)
    try:
        manifest = json.loads((run / "full.json").read_text())
        if manifest["run_id"] != run.name or not manifest["complete"]:
            raise ValueError(
                "Correction requires a completed Full evaluation in its original run directory"
            )
        children = _children(run, manifest)
        for child in children:
            (child / "report.html").unlink(missing_ok=True)
            (child / "report.md").unlink(missing_ok=True)
        baseline = select_baseline(baseline_path, manifest["human_audit_sha256"])
        if baseline is None:
            raise ValueError(
                "No approved Evaluation baseline for this Human audit; supply --baseline PATH"
            )
        validate_baseline(baseline, manifest["human_audit_sha256"])
        original = json.loads((run / "human-findings.json").read_text())
        if {item["human_finding_id"] for item in baseline["decisions"]} != {
            item["human_finding_id"] for item in original["human_findings"]
        }:
            raise ValueError(
                "Full evaluation baseline must contain each original Human finding exactly once"
            )
        # Resolve all expectations before changing any review or baseline pin.
        incompatible = []
        pending_path = run / "correction-review.json"
        pending_path.unlink(missing_ok=True)
        for child in children:
            human = json.loads((child / "artifacts/human-findings.json").read_text())
            child_manifest = json.loads((child / "run.json").read_text())
            programmatic = json.loads(
                (child / "normalized-programmatic-findings.json").read_text()
            )
            decisions = resolved_decisions(
                baseline, human, child_manifest["source_url"], programmatic
            )
            incompatible.extend(_incompatible_llm_decisions(child, decisions))
        if incompatible:
            pending = {
                "incompatible_llm_decisions": incompatible,
                "instructions": "Review the listed review.csv LLM cells explicitly, retaining qualifications in review_notes; rerun correct-all after resolution. Approved decisions remain fixed.",
                "original_backup": str(history),
            }
            pending_path.write_text(
                json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            affected = "; ".join(
                f"{item['human_finding_id']} on {item['source_url']}"
                for item in incompatible
            )
            raise ValueError(
                f"Saved decisions need explicit LLM review: {affected}; see {pending_path}. Edit the listed review.csv LLM cells and rerun correct-all"
            )
        for child in children:
            apply_baseline(child, baseline)
        save_full_baseline(run, baseline)
        _record_correction(run, children, history, reviewer, baseline)
        report_full_evaluation(run, reviewer)
    except (OSError, ValueError, KeyError) as error:
        raise ValueError(
            f"{error}. Original evidence and reports preserved at {history}"
        ) from error
    return history
