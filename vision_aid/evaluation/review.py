"""One editable CSV for human decisions and one deterministic Markdown report."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from vision_aid.evaluation.references import ELIGIBILITY_VALUES, HEADERS

DECISION_COLUMNS = (
    "classification",
    "classification_reason",
    "audit_finding_id",
    "programmatic_finding_id",
    "match_reason",
    "review_notes",
)
REVIEW_COLUMNS = (
    "reference_id",
    "source_sheet",
    "source_row",
    "page_scope",
    "source_element",
    *HEADERS,
    *DECISION_COLUMNS,
)


def create_review(path: Path, references: list[dict[str, Any]]) -> None:
    """Create one editable row per Reference defect with blank decisions."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for item in references:
            writer.writerow(
                {
                    "reference_id": item["reference_id"],
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
    references: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    programmatic: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate completeness and finding kind before granting any row credit."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(REVIEW_COLUMNS).issubset(reader.fieldnames or ()):
            raise ValueError("Review CSV is missing required columns")
        entered = list(reader)
    expected = {item["reference_id"]: item for item in references}
    if len(entered) != len(expected):
        raise ValueError("Review CSV must contain each Reference defect exactly once")
    by_kind = {
        "audit": {item["finding_id"]: item for item in audit},
        "programmatic": {item["finding_id"]: item for item in programmatic},
    }
    seen_rows: set[str] = set()
    used: dict[str, set[str]] = {"audit": set(), "programmatic": set()}
    result = []
    for row in entered:
        reference_id = row["reference_id"]
        if reference_id not in expected or reference_id in seen_rows:
            raise ValueError(f"Unknown or repeated Reference defect: {reference_id}")
        seen_rows.add(reference_id)
        reference = expected[reference_id]
        for field in ("source_sheet", "source_row", "source_element"):
            if str(row[field]) != str(reference[field]):
                raise ValueError(
                    f"Reference identity changed for {reference_id}: {field}"
                )
        classification = row["classification"].strip()
        if classification not in ELIGIBILITY_VALUES:
            raise ValueError(f"Reference {reference_id} needs a valid classification")
        if not row["classification_reason"].strip():
            raise ValueError(f"Reference {reference_id} needs a classification reason")
        matched: dict[str, tuple[str, ...]] = {}
        for kind, column in (
            ("audit", "audit_finding_id"),
            ("programmatic", "programmatic_finding_id"),
        ):
            ids = _ids(row[column])
            unknown = set(ids) - set(by_kind[kind])
            if unknown:
                raise ValueError(
                    f"Unknown {kind} finding ID: {', '.join(sorted(unknown))}"
                )
            reused = set(ids) & used[kind]
            if reused:
                raise ValueError(
                    f"Conflicting {kind} finding ID: {', '.join(sorted(reused))}"
                )
            used[kind].update(ids)
            matched[kind] = ids
        if any(matched.values()) and not row["match_reason"].strip():
            raise ValueError(f"Reference {reference_id} needs a match reason")
        if classification in {"unavailable_evidence", "ambiguous"} and any(
            matched.values()
        ):
            raise ValueError(f"Excluded Reference {reference_id} cannot claim coverage")
        result.append({"reference": reference, "decision": row, "matches": matched})
    return result


def _metric(caught: int, total: int) -> str:
    """Format a binary row-coverage count without inventing an empty rate."""
    if total == 0:
        return "N/A (0 eligible rows)"
    return f"{caught}/{total} ({caught / total:.1%})"


def _md(value: object) -> str:
    """Escape source evidence for Markdown without losing line breaks."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def write_report(
    path: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    programmatic: list[dict[str, Any]],
) -> None:
    """Write the single human-readable score and row evidence projection."""
    if not manifest["complete"]:
        raise ValueError("Incomplete Evaluation runs cannot produce a final report")
    findings = {item["finding_id"]: item for item in audit + programmatic}
    llm = [row for row in rows if row["decision"]["classification"] == "llm_eligible"]
    checks = [
        row for row in rows if row["decision"]["classification"] == "programmatic"
    ]
    covered = [row for row in rows if any(row["matches"].values())]
    audit_caught = sum(bool(row["matches"]["audit"]) for row in llm)
    programmatic_caught = sum(bool(row["matches"]["programmatic"]) for row in checks)
    unavailable = sum(
        row["decision"]["classification"] == "unavailable_evidence" for row in rows
    )
    ambiguous = sum(row["decision"]["classification"] == "ambiguous" for row in rows)
    lines = [
        f"# Evaluation run {manifest['run_id']}",
        "",
        f"- Model: {manifest['configuration']['model']}",
        f"- Workbook-row recall: {_metric(audit_caught, len(llm))}",
        f"- Programmatic coverage: {_metric(programmatic_caught, len(checks))}",
        f"- Combined workbook coverage: {_metric(len(covered), len(rows))}",
        f"- Estimated run cost: ${manifest['estimated_cost_usd']}",
        f"- Unavailable evidence: {unavailable}; ambiguous: {ambiguous}",
        f"- Reported usage: {_md(json.dumps(manifest['usage'], sort_keys=True))}",
        "",
        (
            "This is full-row coverage of this homepage workbook only. "
            "A blank finding cell means missed."
        ),
        (
            "The cost guardrail is checked between requests; "
            "a request can exceed the remaining amount."
        ),
        (
            "Malformed response prompts: "
            f"{_md(', '.join(manifest['format_failures']) or 'none')}"
        ),
        "",
        "## Reference defects",
        "",
    ]
    for row in rows:
        reference = row["reference"]
        decision = row["decision"]
        matches = row["matches"]
        evidence = _md(json.dumps(reference["raw_evidence"], ensure_ascii=False))
        lines.extend(
            [
                f"### {reference['reference_id']} — {_md(reference['problem'])}",
                "",
                (
                    f"- Source: {reference['source_sheet']} "
                    f"row {reference['source_row']} ({reference['page_scope']})"
                ),
                f"- source_element: {_md(reference['source_element'])}",
                f"- Original defect evidence: {evidence}",
                (
                    f"- Classification: {decision['classification']} — "
                    f"{_md(decision['classification_reason'])}"
                ),
                f"- Audit findings: {_md('; '.join(matches['audit']) or 'none')}",
                (
                    "- Programmatic findings: "
                    f"{_md('; '.join(matches['programmatic']) or 'none')}"
                ),
                f"- Match reason: {_md(decision['match_reason'] or 'none')}",
                f"- Review notes: {_md(decision['review_notes'] or 'none')}",
            ]
        )
        for finding_id in (*matches["audit"], *matches["programmatic"]):
            finding = findings[finding_id]
            lines.append(
                f"- {finding_id}: {_md(finding['problem'])} "
                f"@ {_md(finding['location'])}"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
