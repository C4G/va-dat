"""Validated JSON serialization at private evaluation workflow boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vision_aid.evaluation.schemas import (
    CanonicalFinding,
    MatchDecision,
    ReferenceDefect,
    ReferenceSet,
    ReviewProvenance,
    RunMetadata,
    Usage,
)


def write_json(path: Path, value: object) -> None:
    """Write stable, human-readable JSON to a private artifact path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def json_digest(value: object) -> str:
    """Hash a canonical JSON representation for content identity checks."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def reference_set_identity(reference_set: ReferenceSet) -> str:
    """Hash all approved reference and eligibility decision content."""
    return json_digest(reference_set.to_dict())


def save_reference_set(path: Path, reference_set: ReferenceSet) -> None:
    """Persist a canonical reference set."""
    write_json(path, reference_set.to_dict())


def _provenance(value: dict[str, Any] | None) -> ReviewProvenance | None:
    """Construct optional reviewer provenance from JSON data."""
    return ReviewProvenance(**value) if value else None


def load_reference_set(path: Path) -> ReferenceSet:
    """Load a canonical reference set from a private artifact."""
    data = json.loads(path.read_text(encoding="utf-8"))
    references = []
    for value in data["references"]:
        value = dict(value)
        value["wcag_evidence"] = tuple(value.get("wcag_evidence", ()))
        value["required_subdefects"] = tuple(value.get("required_subdefects", ()))
        value["eligibility_review"] = _provenance(value.get("eligibility_review"))
        references.append(ReferenceDefect(**value))
    return ReferenceSet(
        version=data["version"],
        workbook_filename=data["workbook_filename"],
        workbook_sha256=data["workbook_sha256"],
        homepage_url=data["homepage_url"],
        references=tuple(references),
    )


def save_findings(path: Path, findings: tuple[CanonicalFinding, ...]) -> None:
    """Persist canonical findings without changing their raw evidence."""
    write_json(path, [asdict(item) for item in findings])


def load_findings(path: Path) -> tuple[CanonicalFinding, ...]:
    """Load canonical audit or programmatic findings."""
    values = json.loads(path.read_text(encoding="utf-8"))
    findings = []
    for value in values:
        value["wcag_evidence"] = tuple(value.get("wcag_evidence", ()))
        findings.append(CanonicalFinding(**value))
    return tuple(findings)


def save_match_decisions(path: Path, decisions: tuple[MatchDecision, ...]) -> None:
    """Persist reviewed match decisions."""
    write_json(path, [asdict(item) for item in decisions])


def load_match_decisions(path: Path) -> tuple[MatchDecision, ...]:
    """Load reviewed match decisions and their provenance."""
    values = json.loads(path.read_text(encoding="utf-8"))
    decisions = []
    for value in values:
        value["provenance"] = ReviewProvenance(**value["provenance"])
        decisions.append(MatchDecision(**value))
    return tuple(decisions)


def load_run_metadata(value: dict[str, Any]) -> RunMetadata:
    """Load synthetic run metadata from an in-memory test bundle."""
    value = dict(value)
    value["usage"] = Usage(**value.get("usage", {}))
    value["request_durations_seconds"] = tuple(
        value.get("request_durations_seconds", ())
    )
    return RunMetadata(**value)


def load_verified_run_metadata(
    path: Path,
    reference_set: ReferenceSet,
) -> RunMetadata:
    """Derive score metadata from a manifest and verify every identity."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    identity_fields = {
        key: manifest[key]
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
    benchmark_identity = json_digest(identity_fields)
    if manifest.get("benchmark_identity") != benchmark_identity:
        raise ValueError(
            "Run manifest benchmark identities are inconsistent or changed."
        )
    if manifest["workbook_sha256"] != reference_set.workbook_sha256:
        raise ValueError("Run manifest workbook checksum does not match references.")
    if manifest["reference_set_version"] != reference_set.version:
        raise ValueError(
            "Run manifest reference-set version does not match references."
        )
    expected_eligibility = reference_set_identity(reference_set)
    if manifest["eligibility_identity"] != expected_eligibility:
        raise ValueError("Run manifest eligibility decisions do not match references.")
    usage_value = manifest.get("usage", {})
    reasoning_tokens = usage_value.get("reasoning_tokens", 0)
    usage = Usage(
        reasoning_tokens=None if reasoning_tokens is None else int(reasoning_tokens),
        **{
            key: int(usage_value.get(key, 0))
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
            )
        },
    )
    return RunMetadata(
        run_id=str(manifest["run_id"]),
        model=str(manifest["configuration"]["model"]),
        complete=bool(manifest.get("complete", False)),
        comparable_identity=benchmark_identity,
        audit_cost_usd=str(manifest.get("estimated_audit_cost_usd", "0")),
        evaluation_cost_usd=str(manifest.get("evaluation_cost_usd", "0")),
        usage=usage,
        wall_time_seconds=float(manifest.get("wall_time_seconds", 0)),
        request_durations_seconds=tuple(
            float(value) for value in manifest.get("request_durations_seconds", ())
        ),
        workbook_sha256=str(manifest["workbook_sha256"]),
        snapshot_sha256=str(manifest["snapshot_sha256"]),
        reference_set_version=str(manifest["reference_set_version"]),
        prompt_hashes_identity=json_digest(manifest["prompt_hashes"]),
        parser_identity=str(manifest["parser_hash"]),
        eligibility_identity=str(manifest["eligibility_identity"]),
        configuration_identity=json_digest(
            {
                "configuration": manifest["configuration"],
                "filters": manifest["filters"],
            }
        ),
        homepage_url=str(manifest["homepage_url"]),
        prompt_names=tuple(item["name"] for item in manifest["prompts"]),
    )
