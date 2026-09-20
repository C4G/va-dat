"""Import workbook rows into traceable homepage reference defects."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation

from vision_aid.evaluation.schemas import (
    ReferenceDefect,
    ReferenceSet,
    ReviewProvenance,
)


class ReferenceSetError(ValueError):
    """The private workbook cannot produce a trustworthy reference set."""


class EligibilityReviewer(Protocol):
    """Adapter contract for human or future model eligibility review."""

    def review(self, reference_set: ReferenceSet) -> ReferenceSet:
        """Return the reference set with validated review decisions."""


_ALIASES = {
    "scope": ("page", "page scope", "scope", "page name"),
    "url": ("url", "page url", "web address"),
    "problem": (
        "problem",
        "issue",
        "issue title",
        "defect",
        "description",
    ),
    "location": ("location", "element", "element name", "where"),
    "wcag": (
        "wcag",
        "wcag sc",
        "wcag criteria",
        "success criterion",
        "criterion",
    ),
    "recommendation": (
        "recommendation",
        "recommendation for fix",
        "remediation",
        "fix",
    ),
}
ELIGIBILITY_VALUES = (
    "llm_eligible",
    "programmatic",
    "unavailable_evidence",
    "ambiguous",
)
DECISION_VALUES = ("accepted", "rejected", "needs_review")
ELIGIBILITY_COLUMNS = (
    "reference_id",
    "source_sheet",
    "source_row",
    "page_scope",
    "canonical_url",
    "problem",
    "location",
    "wcag_evidence",
    "recommendation",
    "raw_evidence",
    "classification",
    "decision",
    "rationale",
    "reviewer",
    "confidence",
    "timestamp",
    "required_subdefects",
    "notes",
)


def _text(value: object) -> str:
    """Retain workbook cell content as text without semantic rewriting."""
    if value is None:
        return ""
    return str(value)


def _canonical_url(value: str) -> str:
    """Normalize URL identity while discarding query and fragment drift."""
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip()
    path = parts.path or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, "", "")
    )


def _field(headers: dict[str, str], raw: dict[str, str], name: str) -> str:
    """Read one canonical field through the supported workbook aliases."""
    for alias in _ALIASES[name]:
        header = headers.get(alias)
        if header is not None:
            return raw.get(header, "")
    return ""


def _wcag_values(value: str) -> tuple[str, ...]:
    """Extract ordered WCAG success-criterion identifiers."""
    return tuple(dict.fromkeys(re.findall(r"\b\d+\.\d+\.\d+\b", value)))


def import_homepage_references(
    workbook_path: Path,
    *,
    expected_sha256: str,
    homepage_url: str,
    version: str,
) -> ReferenceSet:
    """Import every Home and Global row, retaining source text verbatim."""
    if not workbook_path.is_file():
        raise ReferenceSetError(
            f"Private workbook not found at {workbook_path}. Obtain it from "
            "an "
            "authorized project source or pass an explicit local path."
        )
    actual_sha256 = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise ReferenceSetError(
            "Private workbook checksum drift detected: expected "
            f"{expected_sha256}, found {actual_sha256}. Review and record "
            "the new "
            "authorized workbook before importing it."
        )

    try:
        workbook = openpyxl.load_workbook(
            workbook_path, read_only=True, data_only=True
        )
    except (OSError, ValueError, TypeError) as error:
        raise ReferenceSetError(
            f"Could not read private workbook: {error}"
        ) from error

    canonical_homepage = _canonical_url(homepage_url)
    imported: list[ReferenceDefect] = []
    for sheet in workbook.worksheets:
        rows = sheet.iter_rows(values_only=True)
        first = next(rows, None)
        if first is None:
            continue
        header_names = [_text(value).strip() for value in first]
        normalized_headers = {
            header.casefold(): header for header in header_names if header
        }
        if not any(alias in normalized_headers for alias in _ALIASES["scope"]):
            continue
        for row_number, values in enumerate(rows, start=2):
            raw = {
                header: _text(value)
                for header, value in zip(header_names, values, strict=False)
                if header
            }
            scope_text = (
                _field(normalized_headers, raw, "scope").strip().casefold()
            )
            row_url = _canonical_url(_field(normalized_headers, raw, "url"))
            is_global = scope_text == "global" or row_url.casefold() in {
                "global",
                "all pages",
                "sitewide",
                "site-wide",
            }
            is_home = scope_text in {"home", "homepage", "home page"}
            if not is_home and not is_global and row_url != canonical_homepage:
                continue
            page_scope: Literal["home", "global"] = (
                "global" if is_global else "home"
            )
            identity = f"{actual_sha256}:{sheet.title}:{row_number}".encode()
            imported.append(
                ReferenceDefect(
                    reference_id="ref-"
                    + hashlib.sha256(identity).hexdigest()[:16],
                    workbook_filename=workbook_path.name,
                    workbook_sha256=actual_sha256,
                    source_sheet=sheet.title,
                    source_row=row_number,
                    raw_evidence=raw,
                    canonical_url=canonical_homepage,
                    page_scope=page_scope,
                    problem=_field(normalized_headers, raw, "problem"),
                    location=_field(normalized_headers, raw, "location"),
                    wcag_evidence=_wcag_values(
                        _field(normalized_headers, raw, "wcag")
                    ),
                    recommendation=_field(
                        normalized_headers, raw, "recommendation"
                    ),
                )
            )
    workbook.close()
    if not imported:
        raise ReferenceSetError(
            "The workbook contained no Home or applicable Global rows. "
            "Check the "
            "homepage URL and workbook column names."
        )
    return ReferenceSet(
        version=version,
        workbook_filename=workbook_path.name,
        workbook_sha256=actual_sha256,
        homepage_url=canonical_homepage,
        references=tuple(imported),
    )


def export_eligibility_workbook(
    reference_set: ReferenceSet,
    output_path: Path,
) -> None:
    """Create a private, multiline-friendly eligibility review workbook."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Eligibility"
    sheet.append(ELIGIBILITY_COLUMNS)
    for reference in reference_set.references:
        sheet.append(
            (
                reference.reference_id,
                reference.source_sheet,
                reference.source_row,
                reference.page_scope,
                reference.canonical_url,
                reference.problem,
                reference.location,
                ", ".join(reference.wcag_evidence),
                reference.recommendation,
                json.dumps(
                    reference.raw_evidence, ensure_ascii=False, sort_keys=True
                ),
                reference.eligibility or "",
                reference.eligibility_state or "needs_review",
                (
                    reference.eligibility_review.rationale
                    if reference.eligibility_review
                    else ""
                ),
                (
                    reference.eligibility_review.reviewer
                    if reference.eligibility_review
                    else ""
                ),
                (
                    reference.eligibility_review.confidence
                    if reference.eligibility_review
                    else ""
                ),
                (
                    reference.eligibility_review.timestamp
                    if reference.eligibility_review
                    else ""
                ),
                "\n".join(reference.required_subdefects),
                "",
            )
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["F"].width = 45
    sheet.column_dimensions["G"].width = 32
    sheet.column_dimensions["J"].width = 60
    sheet.column_dimensions["M"].width = 45
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = openpyxl.styles.Alignment(
                wrap_text=True, vertical="top"
            )
    classification_validation = DataValidation(
        type="list",
        formula1='"' + ",".join(ELIGIBILITY_VALUES) + '"',
    )
    decision_validation = DataValidation(
        type="list",
        formula1='"' + ",".join(DECISION_VALUES) + '"',
    )
    sheet.add_data_validation(classification_validation)
    sheet.add_data_validation(decision_validation)
    classification_validation.add(f"K2:K{max(2, sheet.max_row)}")
    decision_validation.add(f"L2:L{max(2, sheet.max_row)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)


class HumanEligibilityReviewer:
    """Load eligibility decisions from the private review workbook."""

    def __init__(self, review_path: Path):
        """Select the private Eligibility workbook to read."""
        self.review_path = review_path

    def review(self, reference_set: ReferenceSet) -> ReferenceSet:
        """Validate and apply exactly one decision for every source row."""
        try:
            workbook = openpyxl.load_workbook(
                self.review_path,
                read_only=True,
                data_only=True,
            )
            sheet = workbook["Eligibility"]
        except (OSError, KeyError, ValueError) as error:
            raise ReferenceSetError(
                f"Could not read Eligibility review workbook: {error}"
            ) from error
        rows = sheet.iter_rows(values_only=True)
        raw_headers = next(rows, None)
        headers = [_text(value).strip() for value in raw_headers or ()]
        missing_columns = set(ELIGIBILITY_COLUMNS) - set(headers)
        if missing_columns:
            raise ReferenceSetError(
                "Eligibility review is missing columns: "
                + ", ".join(sorted(missing_columns))
            )
        decisions: dict[str, dict[str, str]] = {}
        for row_number, values in enumerate(rows, start=2):
            record = {
                header: _text(value).strip()
                for header, value in zip(headers, values, strict=False)
            }
            reference_id = record["reference_id"]
            if not reference_id:
                continue
            if reference_id in decisions:
                raise ReferenceSetError(
                    f"Eligibility review repeats reference {reference_id}."
                )
            classification = record["classification"]
            state = record["decision"]
            if classification not in ELIGIBILITY_VALUES:
                raise ReferenceSetError(
                    f"Eligibility row {row_number} has invalid classification "
                    f"{classification!r}."
                )
            if state not in DECISION_VALUES:
                raise ReferenceSetError(
                    f"Eligibility row {row_number} has invalid decision "
                    f"{state!r}."
                )
            for field in ("rationale", "reviewer", "timestamp"):
                if not record[field]:
                    raise ReferenceSetError(
                        f"Eligibility row {row_number} requires {field}."
                    )
            try:
                confidence = float(record["confidence"])
            except ValueError as error:
                raise ReferenceSetError(
                    f"Eligibility row {row_number} requires numeric "
                    "confidence."
                ) from error
            if not 0 <= confidence <= 1:
                raise ReferenceSetError(
                    f"Eligibility row {row_number} confidence must be 0 "
                    "through 1."
                )
            record["confidence"] = str(confidence)
            decisions[reference_id] = record
        workbook.close()

        expected_ids = {item.reference_id for item in reference_set.references}
        if set(decisions) != expected_ids:
            missing = sorted(expected_ids - set(decisions))
            unknown = sorted(set(decisions) - expected_ids)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unknown:
                details.append("unknown " + ", ".join(unknown))
            raise ReferenceSetError(
                "Eligibility review must decide every reference exactly once: "
                + "; ".join(details)
            )

        reviewed = []
        for reference in reference_set.references:
            decision = decisions[reference.reference_id]
            subdefects = tuple(
                value.strip()
                for value in decision["required_subdefects"].splitlines()
                if value.strip()
            )
            reviewed.append(
                replace(
                    reference,
                    eligibility=decision["classification"],  # type: ignore[arg-type]
                    eligibility_state=decision["decision"],  # type: ignore[arg-type]
                    eligibility_review=ReviewProvenance(
                        reviewer=decision["reviewer"],
                        rationale=decision["rationale"],
                        confidence=float(decision["confidence"]),
                        timestamp=decision["timestamp"],
                    ),
                    required_subdefects=subdefects,
                )
            )
        return replace(reference_set, references=tuple(reviewed))
