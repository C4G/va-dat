"""Validate editable Human review decisions and calculate deterministic counts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from vision_aid.evaluation.baseline import LOCKED_COLUMNS
from vision_aid.evaluation.inputs.human_audit import ELIGIBILITY_VALUES, HEADERS

DECISION_COLUMNS = (
    "classification",
    "classification_reason",
    "llm_finding_id",
    "programmatic_finding_id",
    "match_reason",
    "review_notes",
)
REVIEW_COLUMNS = (
    "human_finding_id",
    "source_sheet",
    "source_row",
    "page_scope",
    "source_element",
    *HEADERS,
    *DECISION_COLUMNS,
)


def create_review(path: Path, human_findings: list[dict[str, Any]]) -> None:
    """Create one editable row per Human finding with blank decisions."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for item in human_findings:
            writer.writerow(
                {
                    "human_finding_id": item["human_finding_id"],
                    "source_sheet": item["source_sheet"],
                    "source_row": item["source_row"],
                    "page_scope": item["page_scope"],
                    "source_element": item["source_element"],
                    **item["raw_evidence"],
                    **{column: "" for column in DECISION_COLUMNS},
                }
            )


def _ids(value: str) -> tuple[str, ...]:
    """Semicolons join multiple finding IDs in either finding column."""
    parts = tuple(part.strip() for part in value.split(";") if part.strip())
    if len(parts) != len(set(parts)):
        raise ValueError("A finding ID is repeated within one review row")
    return parts


def reviewed_rows(
    path: Path,
    human_findings: list[dict[str, Any]],
    llm: list[dict[str, Any]],
    programmatic: list[dict[str, Any]],
    approved: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Validate completeness and finding kind before granting any row credit."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(REVIEW_COLUMNS).issubset(reader.fieldnames or ()):
            raise ValueError("Review CSV is missing required columns")
        if approved is not None and not set(LOCKED_COLUMNS).issubset(reader.fieldnames or ()):
            raise ValueError("Review CSV is missing approved Evaluation baseline columns")
        entered = list(reader)
    expected = {item["human_finding_id"]: item for item in human_findings}
    if len(entered) != len(expected):
        raise ValueError("Review CSV must contain each Human finding exactly once")
    by_kind = {
        "llm": {item["finding_id"]: item for item in llm},
        "programmatic": {item["finding_id"]: item for item in programmatic},
    }
    used: dict[str, set[str]] = {"llm": set(), "programmatic": set()}
    result: dict[str, dict[str, Any]] = {}
    for row in entered:
        human_finding_id = row["human_finding_id"]
        if human_finding_id not in expected or human_finding_id in result:
            raise ValueError(f"Unknown or repeated Human finding: {human_finding_id}")
        human_finding = expected[human_finding_id]
        for field in ("source_sheet", "source_row", "source_element"):
            if str(row[field]) != str(human_finding[field]):
                raise ValueError(
                    f"Human finding identity changed for {human_finding_id}: {field}"
                )
        if approved is not None and (
            row["page_scope"] != human_finding["page_scope"] or any(
                row[field] != human_finding["raw_evidence"].get(field, "") for field in HEADERS
            )
        ):
            raise ValueError(f"Human finding evidence changed for {human_finding_id}")
        if approved is not None:
            for column in LOCKED_COLUMNS:
                actual, required = row[column], approved[human_finding_id][column]
                if column == "programmatic_finding_id":
                    unchanged = set(_ids(actual)) == set(_ids(required))
                else:
                    unchanged = actual == required
                if not unchanged:
                    raise ValueError(
                        f"Human finding {human_finding_id}: approved Evaluation baseline "
                        f"decision changed: {column}. Restore the saved decision; "
                        "review LLM matches in this run, or approve a new baseline CSV review for future runs."
                    )
        classification = row["classification"].strip()
        if classification not in ELIGIBILITY_VALUES:
            raise ValueError(f"Human finding {human_finding_id}: invalid classification")
        matched: dict[str, tuple[str, ...]] = {}
        for kind, column, label in (
            ("llm", "llm_finding_id", "LLM"),
            ("programmatic", "programmatic_finding_id", "Programmatic"),
        ):
            ids = _ids(row[column])
            unknown = set(ids) - set(by_kind[kind])
            if unknown:
                raise ValueError(
                    f"Unknown {label} finding ID: {', '.join(sorted(unknown))}"
                )
            reused = set(ids) & used[kind]
            if reused:
                raise ValueError(
                    f"Conflicting {label} finding ID: {', '.join(sorted(reused))}"
                )
            used[kind].update(ids)
            matched[kind] = ids
        needs_reason = bool(matched["llm"]) or (approved is None and bool(matched["programmatic"]))
        if needs_reason and not row["match_reason"].strip():
            raise ValueError(f"Human finding {human_finding_id} needs a match reason")
        if classification in {"unavailable_evidence", "ambiguous"} and any(
            matched.values()
        ):
            raise ValueError(f"Human finding {human_finding_id} is not testable; cannot claim coverage")
        result[human_finding_id] = {
            "human_finding": human_finding, "decision": row, "matches": matched,
        }
    return [result[identity] for identity in expected]


def detection_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count validated catches and denominators without averaging page rates.

    Each row represents one Human finding. Cross-catches earn Overall credit,
    while source rates include only catches by the expected source. Not-testable
    findings remain in the Overall denominator.
    """
    counts = {}
    for classification, kind in (
        ("llm_eligible", "llm"), ("programmatic", "programmatic")
    ):
        eligible = [
            row for row in rows
            if row["decision"]["classification"].strip() == classification
        ]
        counts[kind] = {
            "caught": sum(bool(row["matches"][kind]) for row in eligible),
            "eligible": len(eligible),
        }
    counts["overall"] = {
        "caught": sum(any(row["matches"].values()) for row in rows),
        "eligible": len(rows),
    }
    return counts
