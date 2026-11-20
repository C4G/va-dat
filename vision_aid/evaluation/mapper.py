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

from vision_aid.evaluation.automated_review import (
    AutomatedReviewer,
    decision_schema,
    decision_text,
    validated_decisions,
)
from vision_aid.evaluation.human_finding_mapping_review import (
    CLASSIFICATION_COLUMNS,
    MATCH_COLUMNS,
    approve_human_finding_mapping_review,
    prepare_human_finding_mapping_review,
    write_review_csv,
)
from vision_aid.evaluation.inputs.human_audit import ELIGIBILITY_VALUES, HEADERS, NOT_TESTABLE

PROMPT = "mapper"
DECISION_SCHEMA = decision_schema({
    "classification": {"type": "string", "enum": list(ELIGIBILITY_VALUES)},
    "classification_reason": {"type": "string"},
    "programmatic_finding_refs": {"type": "array", "items": {"type": "string"}},
    "programmatic_reason": {"type": "string"},
})
# Classifications decided on earlier pages: Human finding ID -> (classification, reason, URL).
Classified = dict[str, tuple[str, str, str]]


def _read(path: Path) -> list[dict[str, str]]:
    """Read one of the prepared review CSVs."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _payload(
    url: str, rows: list[dict[str, str]], catalog: list[dict[str, str]],
    classified: Classified,
) -> dict:
    """Build the mapper's view of one page: its Human and programmatic findings.

    A Global finding classified on an earlier page carries that decision as
    `decided_classification`, so this page only supplies its matches.
    """
    humans = []
    for row in rows:
        human = {
            "human_finding_id": row["human_finding_id"],
            "page_scope": row["page_scope"],
            "source_element": row["source_element"],
            "human_audit": {header: row[header] for header in HEADERS},
        }
        if row["human_finding_id"] in classified:
            classification, reason, _ = classified[row["human_finding_id"]]
            human["decided_classification"] = {
                "classification": classification, "classification_reason": reason,
            }
        humans.append(human)
    return {
        "source_url": url,
        "human_findings": humans,
        "programmatic_findings": [
            {key: value for key, value in finding.items() if key != "source_url"}
            for finding in catalog
        ],
    }


def _validated(
    response: Any, url: str, human_ids: list[str], refs: set[str], classified: Classified,
) -> dict[str, dict[str, Any]]:
    """Check one page's decisions and return them per Human finding.

    `classified` holds the classifications earlier pages chose; the payload
    tells the mapper about them, and this check still refuses a Global
    finding classified differently. Raises ValueError naming the first
    problem, which is sent back on retry.
    """
    def decide(human_id: str, decision: dict[str, Any], chosen: list[str]) -> dict[str, Any]:
        """Apply the mapper's own checks to one decision."""
        classification = decision_text(decision, "classification")
        if classification not in ELIGIBILITY_VALUES:
            raise ValueError(
                f"Human finding {human_id} has invalid classification {classification!r}"
            )
        reason = decision_text(decision, "classification_reason")
        match_reason = decision_text(decision, "programmatic_reason")
        if not reason or not match_reason:
            raise ValueError(
                f"Human finding {human_id} needs classification_reason and programmatic_reason"
            )
        if classification == "programmatic" and not chosen:
            raise ValueError(
                f"Human finding {human_id} is programmatic but has no matching reference "
                "on this page"
            )
        if classification in NOT_TESTABLE and chosen:
            raise ValueError(
                f"Human finding {human_id} is {classification} and cannot have references"
            )
        if human_id in classified and classified[human_id][0] != classification:
            earlier, _, page = classified[human_id]
            raise ValueError(
                f"Human finding {human_id} is classified {earlier} on {page} but "
                f"{classification} on {url}; a Global finding has one classification "
                "on every page"
            )
        return {
            "classification": classification,
            "classification_reason": reason,
            "programmatic_finding_refs": ";".join(chosen),
            "programmatic_reason": match_reason,
        }

    return validated_decisions(
        response, human_ids, "programmatic_finding_refs", refs,
        "or wrong-page programmatic finding reference", decide,
    )


def _map_and_approve(
    directory: Path, human_audit: Path, snapshots: Path,
    reviewer: AutomatedReviewer, output: Path | None,
) -> Path:
    """Decide every page, fill both review CSVs, and run the existing approval."""
    classifications = _read(directory / "classifications.csv")
    matches = _read(directory / "programmatic-review.csv")
    catalog = _read(directory / "programmatic-findings.csv")
    classified: Classified = {}
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
    write_review_csv(directory / "classifications.csv", CLASSIFICATION_COLUMNS, classifications)
    write_review_csv(directory / "programmatic-review.csv", MATCH_COLUMNS, matches)
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
