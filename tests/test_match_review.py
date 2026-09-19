from pathlib import Path

import openpyxl

from vision_aid.evaluation.matching import (
    HumanMatchReviewer,
    export_match_workbook,
    generate_candidates,
)
from vision_aid.evaluation.schemas import CanonicalFinding, ReferenceDefect


def _reference(identifier: str, scope: str = "home") -> ReferenceDefect:
    """Build one synthetic image reference defect."""
    return ReferenceDefect(
        reference_id=identifier,
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        source_sheet="Defects",
        source_row=2,
        raw_evidence={"Problem": "Image problem"},
        canonical_url="https://example.test/",
        page_scope=scope,  # type: ignore[arg-type]
        problem="Image has the wrong alternative text",
        location="hero image",
        wcag_evidence=("1.1.1",),
    )


def _finding(
    identifier: str, page: str = "https://example.test/"
) -> CanonicalFinding:
    """Build one synthetic canonical audit finding."""
    return CanonicalFinding(
        finding_id=identifier,
        source="audit",
        run_id="run-1",
        model="gpt-5.6-luna",
        prompt="informative_alt_quality",
        checklist="CL03",
        page_url=page,
        problem_family="informative_alt_quality",
        problem="Alternative text does not describe the hero",
        element="img",
        location="hero image",
        wcag_evidence=("1.1.1",),
        raw_source={"problem": "Alternative text does not describe the hero"},
        parse_status="parsed",
    )


def test_candidate_generation_only_removes_hard_incompatibilities() -> None:
    """Global evidence remains eligible while different Home pages do not."""
    home = _reference("home")
    global_reference = _reference("global", "global")
    same_page = _finding("same")
    other_page = _finding("other", "https://example.test/contact")

    candidates = generate_candidates(
        (home, global_reference), (same_page, other_page)
    )

    assert ("home", "same") in candidates
    assert ("home", "other") not in candidates
    assert ("global", "same") in candidates
    assert ("global", "other") in candidates


def test_human_match_review_round_trips_side_by_side_evidence(
    tmp_path: Path,
) -> None:
    """The Matches workbook returns provenance-complete decisions."""
    references = (_reference("ref1"),)
    findings = (_finding("finding1"),)
    review_path = tmp_path / "matches.xlsx"
    export_match_workbook(references, findings, review_path)

    workbook = openpyxl.load_workbook(review_path)
    sheet = workbook["Matches"]
    columns = {cell.value: cell.column for cell in sheet[1]}
    values = {
        "decision": "accepted",
        "page_compatible": True,
        "failure_compatible": True,
        "location_compatible": True,
        "rationale": "Same alt-text failure on the hero image.",
        "reviewer": "reviewer@example.test",
        "confidence": 0.9,
        "timestamp": "2026-09-19T12:00:00Z",
    }
    for name, value in values.items():
        sheet.cell(2, columns[name], value)
    workbook.save(review_path)

    decisions = HumanMatchReviewer(review_path).review(references, findings)

    assert len(decisions) == 1
    assert decisions[0].state == "accepted"
    assert decisions[0].page_compatible is True
    assert decisions[0].provenance.reviewer == "reviewer@example.test"
