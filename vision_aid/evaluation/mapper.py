"""The mapper: build and approve a Human finding mapping with the Automated reviewer.

It prepares the mapping review folder as `human-finding-mapping-prepare` does,
sends one request per page (that page's Human findings and programmatic
findings), and fills `classifications.csv` and `programmatic-review.csv` only
after every page is decided. The existing approve step then validates the CSVs
exactly as it validates a person's.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from vision_aid.evaluation.automated_review import AutomatedReviewer
from vision_aid.evaluation.human_finding_mapping_review import (
    CLASSIFICATION_COLUMNS,
    MATCH_COLUMNS,
    _write_csv,
    approve_human_finding_mapping_review,
    prepare_human_finding_mapping_review,
)
from vision_aid.evaluation.inputs.human_audit import ELIGIBILITY_VALUES, HEADERS

PROMPT = "mapper_v1"
NOT_TESTABLE = {"unavailable_evidence", "ambiguous"}
DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "human_finding_id": {"type": "string"},
                    "classification": {"type": "string", "enum": list(ELIGIBILITY_VALUES)},
                    "classification_reason": {"type": "string"},
                    "programmatic_finding_refs": {"type": "array", "items": {"type": "string"}},
                    "programmatic_reason": {"type": "string"},
                },
                "required": [
                    "human_finding_id", "classification", "classification_reason",
                    "programmatic_finding_refs", "programmatic_reason",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


def _read(path: Path) -> list[dict[str, str]]:
    """Read one of the prepared review CSVs."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _payload(
    url: str, rows: list[dict[str, str]], catalog: list[dict[str, str]],
    classified: dict[str, tuple[str, str, str]],
) -> dict:
    """Build the mapper's view of one page: its Human and programmatic findings.

    A Global finding classified on an earlier page carries that decision as
    `decided_classification`, so this page only supplies its matches.
    """
    return {
        "source_url": url,
        "human_findings": [
            {
                "human_finding_id": row["human_finding_id"],
                "page_scope": row["page_scope"],
                "source_element": row["source_element"],
                "human_audit": {header: row[header] for header in HEADERS},
                **({"decided_classification": {
                    "classification": classified[row["human_finding_id"]][0],
                    "classification_reason": classified[row["human_finding_id"]][1],
                }} if row["human_finding_id"] in classified else {}),
            }
            for row in rows
        ],
        "programmatic_findings": [
            {key: value for key, value in finding.items() if key != "source_url"}
            for finding in catalog
        ],
    }


def _validated(
    response: Any,
    url: str,
    human_ids: list[str],
    refs: set[str],
    classified: dict[str, tuple[str, str, str]],
) -> dict[str, dict[str, Any]]:
    """Check one page's decisions and return them per Human finding.

    `classified` holds the classifications earlier pages chose; a Global
    finding must get the same one here. Raises ValueError naming the first
    problem, which is sent back on retry.
    """
    if not isinstance(response, dict) or not isinstance(response.get("decisions"), list):
        raise ValueError("the response must be an object with a decisions list")
    decided: dict[str, dict[str, Any]] = {}
    used: dict[str, str] = {}
    for decision in response["decisions"]:
        human_id = decision.get("human_finding_id") if isinstance(decision, dict) else None
        if human_id not in human_ids:
            raise ValueError(f"unknown Human finding: {human_id}")
        if human_id in decided:
            raise ValueError(f"Human finding {human_id} is decided more than once")
        classification = str(decision.get("classification") or "").strip()
        if classification not in ELIGIBILITY_VALUES:
            raise ValueError(f"Human finding {human_id} has invalid classification {classification!r}")
        reason = str(decision.get("classification_reason") or "").strip()
        match_reason = str(decision.get("programmatic_reason") or "").strip()
        if not reason or not match_reason:
            raise ValueError(
                f"Human finding {human_id} needs classification_reason and programmatic_reason"
            )
        chosen = [str(item).strip() for item in decision.get("programmatic_finding_refs") or []]
        chosen = [item for item in chosen if item]
        unknown = sorted(set(chosen) - refs)
        if unknown:
            raise ValueError(
                f"unknown or wrong-page programmatic finding reference for {human_id}: "
                f"{', '.join(unknown)}"
            )
        if len(chosen) != len(set(chosen)):
            raise ValueError(f"a programmatic finding reference is repeated for {human_id}")
        for ref in chosen:
            if ref in used:
                raise ValueError(f"reference {ref} is used for both {used[ref]} and {human_id}")
            used[ref] = human_id
        if classification == "programmatic" and not chosen:
            raise ValueError(
                f"Human finding {human_id} is programmatic but has no matching reference on this page"
            )
        if classification in NOT_TESTABLE and chosen:
            raise ValueError(
                f"Human finding {human_id} is {classification} and cannot have references"
            )
        if human_id in classified and classified[human_id][0] != classification:
            earlier, _, page = classified[human_id]
            raise ValueError(
                f"Human finding {human_id} is classified {earlier} on {page} but "
                f"{classification} on {url}; a Global finding has one classification on every page"
            )
        decided[human_id] = {
            "classification": classification,
            "classification_reason": reason,
            "programmatic_finding_refs": ";".join(chosen),
            "programmatic_reason": match_reason,
        }
    missing = [human_id for human_id in human_ids if human_id not in decided]
    if missing:
        raise ValueError(f"no decision for Human finding: {', '.join(missing)}")
    return decided


def _map_and_approve(
    directory: Path, human_audit: Path, snapshots: Path,
    reviewer: AutomatedReviewer, output: Path | None,
) -> Path:
    """Decide every page, fill both review CSVs, and run the existing approval."""
    classifications = _read(directory / "classifications.csv")
    matches = _read(directory / "programmatic-review.csv")
    catalog = _read(directory / "programmatic-findings.csv")
    classified: dict[str, tuple[str, str, str]] = {}
    by_page: dict[tuple[str, str], dict[str, Any]] = {}
    for url in dict.fromkeys(row["source_url"] for row in matches):
        rows = [row for row in matches if row["source_url"] == url]
        findings = [finding for finding in catalog if finding["source_url"] == url]
        decided = reviewer.decide(
            _payload(url, rows, findings, classified), DECISION_SCHEMA,
            lambda response, url=url, rows=rows, findings=findings: _validated(
                response, url, [row["human_finding_id"] for row in rows],
                {finding["finding_ref"] for finding in findings}, classified,
            ),
            label=url,
        )
        for human_id, decision in decided.items():
            classified.setdefault(
                human_id, (decision["classification"], decision["classification_reason"], url)
            )
            by_page[(url, human_id)] = decision
    for row in classifications:
        row["classification"], row["classification_reason"], _ = classified[row["human_finding_id"]]
    for row in matches:
        decision = by_page[(row["source_url"], row["human_finding_id"])]
        row["programmatic_finding_refs"] = decision["programmatic_finding_refs"]
        row["programmatic_reason"] = decision["programmatic_reason"]
    _write_csv(directory / "classifications.csv", CLASSIFICATION_COLUMNS, classifications)
    _write_csv(directory / "programmatic-review.csv", MATCH_COLUMNS, matches)
    return approve_human_finding_mapping_review(
        directory, human_audit, snapshots, reviewer.attribution, output,
    )


def build_human_finding_mapping(
    human_audit: Path, snapshots: Path, directory: Path,
    reviewer: AutomatedReviewer, output: Path | None = None,
) -> Path:
    """Prepare `directory`, have `reviewer` fill it, approve it, and return the mapping path.

    The mapping is approved as `reviewer.attribution`. The reviewer's usage
    and cost are recorded in `directory/automated-review.json` whether it
    succeeds or not. Raises ReviewFailure (or CostLimitReached) without
    filling either CSV when a page can't be decided, and ValueError when the
    approval step rejects the filled CSVs.
    """
    prepare_human_finding_mapping_review(human_audit, snapshots, directory)
    try:
        mapping = _map_and_approve(directory, human_audit, snapshots, reviewer, output)
    except Exception as error:
        reviewer.record(directory, "failed", str(error))
        raise
    reviewer.record(directory, "complete")
    return mapping
