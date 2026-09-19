"""Validated JSON serialization at private evaluation workflow boundaries."""

from __future__ import annotations

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_reference_set(path: Path, reference_set: ReferenceSet) -> None:
    write_json(path, reference_set.to_dict())


def _provenance(value: dict[str, Any] | None) -> ReviewProvenance | None:
    return ReviewProvenance(**value) if value else None


def load_reference_set(path: Path) -> ReferenceSet:
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
    write_json(path, [asdict(item) for item in findings])


def load_findings(path: Path) -> tuple[CanonicalFinding, ...]:
    values = json.loads(path.read_text(encoding="utf-8"))
    findings = []
    for value in values:
        value["wcag_evidence"] = tuple(value.get("wcag_evidence", ()))
        findings.append(CanonicalFinding(**value))
    return tuple(findings)


def save_match_decisions(path: Path, decisions: tuple[MatchDecision, ...]) -> None:
    write_json(path, [asdict(item) for item in decisions])


def load_match_decisions(path: Path) -> tuple[MatchDecision, ...]:
    values = json.loads(path.read_text(encoding="utf-8"))
    decisions = []
    for value in values:
        value["provenance"] = ReviewProvenance(**value["provenance"])
        decisions.append(MatchDecision(**value))
    return tuple(decisions)


def load_run_metadata(value: dict[str, Any]) -> RunMetadata:
    value = dict(value)
    value["usage"] = Usage(**value.get("usage", {}))
    value["request_durations_seconds"] = tuple(
        value.get("request_durations_seconds", ())
    )
    return RunMetadata(**value)
