"""Import the known Reference workbook's Home and Global defect rows."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import openpyxl

from vision_aid.evaluation.schemas import ReferenceDefect, ReferenceSet

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


def import_homepage_references(workbook_path: Path, homepage_url: str) -> ReferenceSet:
    """Preserve every applicable source row and its original cell text."""
    checksum = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    book = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        sheet = book[SHEET]
        rows = sheet.iter_rows(values_only=True)
        headers = tuple(str(value or "") for value in next(rows))
        if headers[: len(HEADERS)] != HEADERS:
            raise ValueError("Reference workbook has unexpected Defect report columns")
        references = []
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
            references.append(
                ReferenceDefect(
                    reference_id="ref-" + hashlib.sha256(identity).hexdigest()[:16],
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
    if not references:
        raise ValueError("Reference workbook has no Home or Global defects")
    return ReferenceSet(workbook_path.name, checksum, homepage_url, tuple(references))
