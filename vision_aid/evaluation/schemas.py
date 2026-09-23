"""Evidence records for the fixed homepage evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ReferenceDefect:
    reference_id: str
    source_sheet: str
    source_row: int
    page_scope: Literal["home", "global"]
    source_element: str
    problem: str
    raw_evidence: dict[str, str]
    wcag_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceSet:
    workbook_filename: str
    workbook_sha256: str
    homepage_url: str
    references: tuple[ReferenceDefect, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalFinding:
    finding_id: str
    source: Literal["audit", "programmatic"]
    run_id: str
    model: str | None
    prompt: str
    checklist: str
    page_url: str
    problem_family: str
    problem: str
    element: str
    location: str
    wcag_evidence: tuple[str, ...]
    raw_source: Any
    parse_status: str
