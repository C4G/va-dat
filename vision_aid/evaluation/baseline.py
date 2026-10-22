"""Approved audit decisions, resolved against each page's actual checker evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from vision_aid.evaluation.inputs.human_audit import ELIGIBILITY_VALUES

BASELINE_DIRECTORY = Path(__file__).with_name("baselines")
BASELINE_ARTIFACT = "artifacts/evaluation-baseline.json"
LOCKED_COLUMNS = (
    "classification", "classification_reason", "programmatic_finding_id",
    "programmatic_match_reason",
)


def _text(value: Any) -> bool:
    """Identify populated human-authored text without coercing invalid values."""
    return isinstance(value, str) and bool(value.strip())


def validate_baseline(baseline: dict[str, Any], audit_sha256: str) -> None:
    """Reject unrelated audits and incomplete or conflicting approved decisions."""
    if not isinstance(baseline, dict) or baseline.get("schema_version") != 1:
        raise ValueError("Evaluation baseline must use schema_version 1")
    if baseline.get("human_audit_sha256") != audit_sha256:
        raise ValueError("Evaluation baseline Human audit identity differs from the run")
    if not _text(baseline.get("approved_by")):
        raise ValueError("Evaluation baseline needs approved_by attribution")
    decisions = baseline.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Evaluation baseline needs approved decisions")
    seen = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Evaluation baseline decision must be an object")  # noqa: TRY004 - CLI input validation
        identity = decision.get("human_finding_id")
        if not _text(identity) or identity in seen:
            raise ValueError(f"Evaluation baseline has unknown or repeated Human finding: {identity}")
        seen.add(identity)
        prefix = f"Evaluation baseline Human finding {identity}"
        if decision.get("classification") not in ELIGIBILITY_VALUES:
            raise ValueError(f"{prefix}: invalid classification")
        if not _text(decision.get("classification_reason")):
            raise ValueError(f"{prefix}: needs approved classification_reason")
        pages = decision.get("programmatic_by_page")
        if not isinstance(pages, dict) or not pages:
            raise ValueError(f"{prefix}: needs explicit Programmatic decisions per page")
        for url, page in pages.items():
            if not _text(url) or not isinstance(page, dict):
                raise ValueError(f"{prefix}: invalid Programmatic page decision")
            expectations = page.get("expectations")
            if not isinstance(expectations, list) or not _text(page.get("reason")):
                raise ValueError(f"{prefix}, {url}: needs expectations and approved reason")
            classification = decision["classification"]
            if classification == "programmatic" and not expectations:
                raise ValueError(f"{prefix}, {url}: Programmatic responsibility requires expected coverage")
            if classification in {"unavailable_evidence", "ambiguous"} and expectations:
                raise ValueError(f"{prefix}, {url}: not testable; cannot claim Programmatic coverage")
            for expectation in expectations:
                if not isinstance(expectation, dict) or not _text(expectation.get("rule")):
                    raise ValueError(f"{prefix}, {url}: expectation needs an existing rule and evidence")
                evidence = expectation.get("evidence")
                if (
                    not isinstance(evidence, dict)
                    or not evidence
                    or set(evidence) - {"element", "location", "problem", "raw_source"}
                    or not any(value for value in evidence.values())
                ):
                    raise ValueError(f"{prefix}, {url}: expectation needs relevant element/page evidence")
                for field, value in evidence.items():
                    if field == "raw_source":
                        if not isinstance(value, dict) or not value:
                            raise ValueError(f"{prefix}, {url}: raw_source evidence must be a nonempty object")
                    elif not isinstance(value, str):
                        raise ValueError(f"{prefix}, {url}: {field} evidence must be text")


def load_baseline(path: Path, audit_sha256: str) -> dict[str, Any]:
    """Read explicitly selected approved decisions for exactly this Human audit."""
    baseline = json.loads(path.read_text(encoding="utf-8"))
    validate_baseline(baseline, audit_sha256)
    return baseline


def select_baseline(path: Path | None, audit_sha256: str) -> dict[str, Any] | None:
    """Select explicit decisions or the bundled baseline for this audit checksum."""
    if path is None:
        path = BASELINE_DIRECTORY / f"{audit_sha256}.json"
        if not path.is_file():
            return None
    return load_baseline(path, audit_sha256)


def _contains(actual: Any, expected: Any) -> bool:
    """Match exact evidence values, allowing a selected subset of raw object fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected


def resolved_decisions(
    baseline: dict[str, Any], human_audit: dict[str, Any], source_url: str,
    programmatic: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Resolve each approved complete match uniquely without run-dependent keys."""
    validate_baseline(baseline, human_audit["human_audit_sha256"])
    decisions = {item["human_finding_id"]: item for item in baseline["decisions"]}
    resolved = {}
    used = set()
    for human in human_audit["human_findings"]:
        identity = human["human_finding_id"]
        prefix = f"Evaluation baseline Human finding {identity}, {source_url}"
        if identity not in decisions:
            raise ValueError(f"{prefix}: missing approved decision")
        decision = decisions[identity]
        if source_url not in decision["programmatic_by_page"]:
            raise ValueError(f"{prefix}: missing explicit Programmatic page decision")
        page = decision["programmatic_by_page"][source_url]
        ids = []
        for expectation in page["expectations"]:
            candidates = [
                item for item in programmatic
                if item["problem_family"] == expectation["rule"]
                and _contains(item, expectation["evidence"])
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"{prefix}: expected Programmatic rule {expectation['rule']} "
                    f"with evidence {json.dumps(expectation['evidence'], ensure_ascii=False, sort_keys=True)} "
                    f"resolved to {len(candidates)} findings; expected exactly one. "
                    "Inspect the saved checker evidence and approved expectation."
                )
            finding_id = candidates[0]["finding_id"]
            if finding_id in used:
                raise ValueError(f"{prefix}: conflicting Programmatic finding ID reuse: {finding_id}")
            used.add(finding_id)
            ids.append(finding_id)
        resolved[identity] = {
            "classification": decision["classification"],
            "classification_reason": decision["classification_reason"],
            "programmatic_finding_id": ";".join(ids),
            "programmatic_match_reason": page["reason"],
        }
    return resolved


def save_baseline_snapshot(
    run: Path, manifest: dict[str, Any], baseline: dict[str, Any],
) -> None:
    """Save approved decisions and pin their bytes and attribution in a manifest."""
    path = run / BASELINE_ARTIFACT
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["evaluation_baseline_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["evaluation_baseline_approved_by"] = baseline["approved_by"]


def load_baseline_snapshot(
    run: Path, manifest: dict[str, Any], label: str = "Saved Evaluation baseline",
) -> dict[str, Any]:
    """Load a pinned approved source only after verifying its bytes and attribution."""
    path = run / BASELINE_ARTIFACT
    digest = manifest["evaluation_baseline_sha256"]
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"{label} is missing or its checksum changed")
    baseline = load_baseline(path, manifest["human_audit_sha256"])
    if manifest.get("evaluation_baseline_approved_by") != baseline["approved_by"]:
        raise ValueError(f"{label} approval attribution changed")
    return baseline


def apply_baseline(run: Path, baseline: dict[str, Any]) -> None:
    """Populate fixed decisions and save their source, preserving per-run LLM review."""
    manifest = json.loads((run / "run.json").read_text())
    human = json.loads((run / "artifacts/human-findings.json").read_text())
    programmatic = json.loads((run / "normalized-programmatic-findings.json").read_text())
    if human["human_audit_sha256"] != manifest["human_audit_sha256"]:
        raise ValueError("Human audit identity differs from the run")
    decisions = resolved_decisions(baseline, human, manifest["source_url"], programmatic)
    path = run / "review.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    if (
        len(rows) != len(decisions)
        or {row.get("human_finding_id") for row in rows} != set(decisions)
    ):
        raise ValueError("Review CSV must contain each Human finding exactly once")
    if "programmatic_match_reason" not in columns:
        columns.append("programmatic_match_reason")
    for row in rows:
        row.update(decisions[row["human_finding_id"]])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    save_baseline_snapshot(run, manifest, baseline)
    (run / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def saved_baseline_decisions(
    run: Path, manifest: dict[str, Any], human: dict[str, Any],
    programmatic: list[dict[str, Any]],
) -> dict[str, dict[str, str]] | None:
    """Load only the run's frozen decisions and verify their saved identity."""
    path = run / BASELINE_ARTIFACT
    digest = manifest.get("evaluation_baseline_sha256")
    if not digest:
        if path.exists():
            raise ValueError("Saved Evaluation baseline is missing its run identity")
        if (BASELINE_DIRECTORY / f"{manifest['human_audit_sha256']}.json").is_file():
            raise ValueError("This Human audit requires its approved Evaluation baseline; prepare a new run with --baseline PATH")
        return None
    baseline = load_baseline_snapshot(run, manifest)
    return resolved_decisions(baseline, human, manifest["source_url"], programmatic)
