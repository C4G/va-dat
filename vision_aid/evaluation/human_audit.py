"""Import the known Human audit's Home and Global defect rows."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import openpyxl

from vision_aid.evaluation.schemas import HumanAudit, HumanFinding

SHEET = "Defect report"
HEADERS = (
    "Sr. #",
    "element name",
    "Browser Combination",
    "Page name",
    "Issue Title",
    "Steps to Reproduce",
    "actual result",
    "expected result",
    "Recommendation for Fix",
    "WCAG Sc",
    "Type of Change",
    "comment",
)
ELIGIBILITY_VALUES = (
    "llm_eligible",
    "programmatic",
    "unavailable_evidence",
    "ambiguous",
)


def import_homepage_human_findings(path: Path, homepage_url: str) -> HumanAudit:
    """Preserve every applicable source row and its original cell text."""
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book[SHEET]
        rows = sheet.iter_rows(values_only=True)
        headers = tuple(str(value or "") for value in next(rows))
        if headers[: len(HEADERS)] != HEADERS:
            raise ValueError("Human audit has unexpected Defect report columns")
        human_findings = []
        for number, values in enumerate(rows, start=2):
            raw = {
                header: "" if value is None else str(value)
                for header, value in zip(headers, values, strict=False)
                if header
            }
            scope = raw["Page name"].strip().casefold()
            if scope not in {"home", "global"}:
                continue
            if not raw["Issue Title"].strip():
                raise ValueError(f"Defect report row {number} has no Issue Title")
            identity = f"{checksum}:{SHEET}:{number}".encode()
            human_findings.append(
                HumanFinding(
                    human_finding_id="human-" + hashlib.sha256(identity).hexdigest()[:16],
                    source_sheet=SHEET,
                    source_row=number,
                    page_scope=scope,
                    source_element=raw["element name"],
                    problem=raw["Issue Title"],
                    raw_evidence=raw,
                    wcag_evidence=tuple(
                        dict.fromkeys(re.findall(r"\b\d+\.\d+\.\d+\b", raw["WCAG Sc"]))
                    ),
                )
            )
    finally:
        book.close()
    if not human_findings:
        raise ValueError("Human audit has no Home or Global defects")
    return HumanAudit(path.name, checksum, homepage_url, tuple(human_findings))
