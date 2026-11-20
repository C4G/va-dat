"""The matcher: fill review.csv's LLM decisions with the Automated reviewer.

One request per page: that page's review.csv rows and its normalized LLM
findings. Every page is decided before any review.csv is written, so a failed
review leaves the run as it was. The existing report path then validates the
written CSVs exactly as it validates a person's.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from vision_aid.evaluation.automated_review import AutomatedReviewer
from vision_aid.evaluation.full import report_full_evaluation
from vision_aid.evaluation.inputs.human_audit import HEADERS
from vision_aid.evaluation.page import report_page

PROMPT = "matcher_v1"
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
                    "llm_finding_ids": {"type": "array", "items": {"type": "string"}},
                    "match_reason": {"type": "string"},
                    "review_notes": {"type": "string"},
                },
                "required": [
                    "human_finding_id", "llm_finding_ids", "match_reason", "review_notes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


def review_pages(run: Path) -> list[Path]:
    """Return the page run folders of a complete `run` or `run-all` folder.

    Refuses previews and incomplete runs, as `report` and `report-all` do.
    """
    if (run / "full.json").is_file():
        manifest = json.loads((run / "full.json").read_text())
        if not manifest["complete"]:
            raise ValueError("Incomplete Full evaluations cannot produce a final report")
        return [run / page["run_dir"] for page in manifest["pages"]]
    manifest = json.loads((run / "run.json").read_text())
    if not manifest["complete"]:
        raise ValueError("Incomplete Evaluation runs cannot produce a final report")
    return [run]


def _read_review(page: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a page's review.csv as its column order and rows."""
    with (page / "review.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or ()), list(reader)


def _payload(page: Path, rows: list[dict[str, str]], llm: list[dict]) -> dict[str, Any]:
    """Build the matcher's view of one page: Human findings and LLM findings."""
    manifest = json.loads((page / "run.json").read_text())
    return {
        "source_url": manifest["source_url"],
        "human_findings": [
            {
                "human_finding_id": row["human_finding_id"],
                "page_scope": row["page_scope"],
                "source_element": row["source_element"],
                "human_audit": {header: row[header] for header in HEADERS},
                "classification": row["classification"],
                "classification_reason": row["classification_reason"],
                "programmatic_finding_id": row["programmatic_finding_id"],
                "programmatic_match_reason": row.get("programmatic_match_reason", ""),
            }
            for row in rows
        ],
        "llm_findings": [
            {
                key: item.get(key)
                for key in ("finding_id", "prompt", "problem", "element", "location",
                            "wcag_evidence")
            }
            for item in llm
        ],
    }


def _validated(
    response: Any, rows: list[dict[str, str]], llm_ids: set[str],
) -> dict[str, dict[str, str]]:
    """Check one page's decisions and return the review.csv values per Human finding.

    Raises ValueError naming the first problem, which is sent back on retry.
    """
    if not isinstance(response, dict) or not isinstance(response.get("decisions"), list):
        raise ValueError("the response must be an object with a decisions list")
    expected = {row["human_finding_id"]: row for row in rows}
    decided: dict[str, dict[str, str]] = {}
    used: dict[str, str] = {}
    for decision in response["decisions"]:
        human_id = decision.get("human_finding_id") if isinstance(decision, dict) else None
        if human_id not in expected:
            raise ValueError(f"unknown Human finding: {human_id}")
        if human_id in decided:
            raise ValueError(f"Human finding {human_id} is decided more than once")
        ids = [str(item).strip() for item in decision.get("llm_finding_ids") or []]
        ids = [item for item in ids if item]
        reason = str(decision.get("match_reason") or "").strip()
        unknown = sorted(set(ids) - llm_ids)
        if unknown:
            raise ValueError(f"unknown LLM finding ID for {human_id}: {', '.join(unknown)}")
        if len(ids) != len(set(ids)):
            raise ValueError(f"an LLM finding ID is repeated for {human_id}")
        for item in ids:
            if item in used:
                raise ValueError(
                    f"LLM finding {item} is used for both {used[item]} and {human_id}"
                )
            used[item] = human_id
        if ids and not reason:
            raise ValueError(f"Human finding {human_id} has LLM finding IDs but no match_reason")
        if ids and expected[human_id]["classification"].strip() in NOT_TESTABLE:
            raise ValueError(f"Human finding {human_id} is not testable and cannot be matched")
        decided[human_id] = {
            "llm_finding_id": ";".join(ids),
            "match_reason": reason if ids else "",
            "review_notes": str(decision.get("review_notes") or "").strip(),
        }
    missing = sorted(set(expected) - set(decided))
    if missing:
        raise ValueError(f"no decision for Human finding: {', '.join(missing)}")
    return decided


def _write_review(page: Path, fields: list[str], rows: list[dict[str, str]],
                  decided: dict[str, dict[str, str]]) -> None:
    """Write the LLM decision columns into review.csv, leaving every other cell as it was."""
    for row in rows:
        row.update(decided[row["human_finding_id"]])
    with (page / "review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def review_and_report(run: Path, reviewer: AutomatedReviewer) -> Path:
    """Decide every page with `reviewer`, write review.csv, and write the report(s).

    Returns the top-level report path. Raises ReviewFailure (or
    CostLimitReached) without writing anything when a page can't be decided.
    """
    run = run.resolve()
    pages = review_pages(run)
    decisions = []
    for page in pages:
        fields, rows = _read_review(page)
        llm = json.loads((page / "normalized-llm-findings.json").read_text())
        llm_ids = {item["finding_id"] for item in llm}
        decided = reviewer.decide(
            _payload(page, rows, llm), DECISION_SCHEMA,
            lambda response, rows=rows, ids=llm_ids: _validated(response, rows, ids),
            label=str(page.relative_to(run.parent)),
        )
        decisions.append((page, fields, rows, decided))
    for page, fields, rows, decided in decisions:
        _write_review(page, fields, rows, decided)
    if (run / "full.json").is_file():
        report_full_evaluation(run, reviewer.attribution)
    else:
        report_page(run, reviewer.attribution)
    return run / "report.html"
