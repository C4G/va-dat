import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from vision_aid.evaluation.matching import MatchValidationError
from vision_aid.evaluation.reporting import write_reports
from vision_aid.evaluation.schemas import (
    CanonicalFinding,
    MatchDecision,
    ReferenceDefect,
    ReferenceSet,
    ReviewProvenance,
    RunMetadata,
    Usage,
)
from vision_aid.evaluation.scoring import rank_scores, score_evaluation

REVIEW = ReviewProvenance(
    reviewer="reviewer@example.test",
    rationale="Evidence describes the same failure at the same location.",
    confidence=0.95,
    timestamp="2026-09-19T12:00:00Z",
)


def _reference(
    identifier: str,
    eligibility: str,
    *,
    required_subdefects: tuple[str, ...] = (),
) -> ReferenceDefect:
    """Build one approved synthetic reference defect."""
    return ReferenceDefect(
        reference_id=identifier,
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        source_sheet="Defects",
        source_row=int(identifier[-1]),
        raw_evidence={"Problem": identifier},
        canonical_url="https://example.test/",
        page_scope="home",
        problem=identifier,
        location="hero",
        wcag_evidence=("1.1.1",),
        required_subdefects=required_subdefects,
        eligibility=eligibility,  # type: ignore[arg-type]
        eligibility_state="accepted",
        eligibility_review=REVIEW,
    )


def _finding(identifier: str, source: str = "audit") -> CanonicalFinding:
    """Build one synthetic canonical finding."""
    return CanonicalFinding(
        finding_id=identifier,
        source=source,  # type: ignore[arg-type]
        run_id="run-1",
        model="gpt-5.6-luna" if source == "audit" else None,
        prompt="decorative_verification",
        checklist="CL03",
        page_url="https://example.test/",
        problem_family="nontext",
        problem=identifier,
        element="img",
        location="hero",
        wcag_evidence=("1.1.1",),
        raw_source={"problem": identifier},
        parse_status="parsed",
    )


def _match(reference: str, finding: str, subdefect: str | None = None) -> MatchDecision:
    """Build one accepted, evidence-compatible match decision."""
    return MatchDecision(
        reference_id=reference,
        finding_id=finding,
        state="accepted",
        provenance=REVIEW,
        required_subdefect=subdefect,
        page_compatible=True,
        failure_compatible=True,
        location_compatible=True,
    )


def test_deterministic_score_separates_coverage() -> None:
    """Scoring separates coverage and requires every compound sub-defect."""
    references = ReferenceSet(
        version="v1",
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        homepage_url="https://example.test/",
        references=(
            _reference("ref1", "llm_eligible"),
            _reference("ref2", "llm_eligible", required_subdefects=("a", "b")),
            _reference("ref3", "programmatic"),
            _reference("ref4", "unavailable_evidence"),
            _reference("ref5", "ambiguous"),
        ),
    )
    audit_findings = (
        _finding("finding1"),
        _finding("finding2"),
        _finding("extra"),
    )
    programmatic_findings = (_finding("program1", "programmatic"),)
    run = RunMetadata(
        run_id="run-1",
        model="gpt-5.6-luna",
        complete=True,
        comparable_identity="benchmark-v1",
        audit_cost_usd="0.001234",
        evaluation_cost_usd="0.02",
        usage=Usage(input_tokens=100, output_tokens=25, reasoning_tokens=5),
        wall_time_seconds=4.5,
        request_durations_seconds=(1.0, 2.0),
    )

    partial = score_evaluation(
        references,
        audit_findings,
        programmatic_findings,
        (_match("ref1", "finding1"), _match("ref2", "finding2", "a")),
        (_match("ref3", "program1"),),
        run,
        parse_failures=("heading_structure",),
    )
    complete = score_evaluation(
        references,
        audit_findings,
        programmatic_findings,
        (
            _match("ref1", "finding1"),
            _match("ref2", "finding2", "a"),
            _match("ref2", "extra", "b"),
        ),
        (_match("ref3", "program1"),),
        run,
        parse_failures=("heading_structure",),
    )

    assert partial.workbook_row_recall == {
        "caught": 1,
        "denominator": 2,
        "rate": "0.5",
    }
    assert complete.workbook_row_recall == {
        "caught": 2,
        "denominator": 2,
        "rate": "1",
    }
    assert complete.programmatic_coverage == {
        "caught": 1,
        "denominator": 1,
        "rate": "1",
    }
    assert complete.combined_workbook_coverage == {
        "caught": 3,
        "denominator": 5,
        "rate": "0.6",
    }
    assert complete.unmatched_audit_finding_ids == ()
    assert complete.parse_failures == ("heading_structure",)
    assert complete.total_experiment_cost_usd == "0.021234"
    assert (
        complete.to_dict()
        == score_evaluation(
            references,
            audit_findings,
            programmatic_findings,
            (
                _match("ref1", "finding1"),
                _match("ref2", "finding2", "a"),
                _match("ref2", "extra", "b"),
            ),
            (_match("ref3", "program1"),),
            run,
            parse_failures=("heading_structure",),
        ).to_dict()
    )


def test_match_conflicts_and_incomplete_runs_cannot_be_ranked() -> None:
    """Conflicting matches and incomplete runs fail closed."""
    references = ReferenceSet(
        version="v1",
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        homepage_url="https://example.test/",
        references=(
            _reference("ref1", "llm_eligible"),
            _reference("ref2", "llm_eligible"),
        ),
    )
    finding = _finding("finding1")
    run = RunMetadata(
        run_id="run-1",
        model="gpt-5.6-luna",
        complete=False,
        comparable_identity="benchmark-v1",
        audit_cost_usd="0.01",
    )
    with pytest.raises(MatchValidationError, match="one-to-one"):
        score_evaluation(
            references,
            (finding,),
            (),
            (_match("ref1", "finding1"), _match("ref2", "finding1")),
            (),
            run,
        )

    score = score_evaluation(references, (finding,), (), (), (), run)
    with pytest.raises(ValueError, match="incomplete"):
        rank_scores((score,))


@pytest.mark.parametrize("reasoning_tokens", [0, None])
def test_reports_are_projections_of_one_score_object(
    tmp_path: Path, reasoning_tokens
) -> None:
    """Every format exposes the same totals, latency, and row disposition."""
    references = ReferenceSet(
        version="v1",
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        homepage_url="https://example.test/",
        references=(_reference("ref1", "llm_eligible"),),
    )
    finding = _finding("finding1")
    run = RunMetadata(
        run_id="run-1",
        model="gpt-5.6-luna",
        complete=True,
        comparable_identity="benchmark-v1",
        audit_cost_usd="0.001",
        usage=Usage(output_tokens=16002, reasoning_tokens=reasoning_tokens),
    )
    score = score_evaluation(
        references,
        (finding,),
        (),
        (_match("ref1", "finding1"),),
        (),
        run,
    )

    paths = write_reports(score, tmp_path)

    json_report = json.loads(paths.json.read_text(encoding="utf-8"))
    with paths.csv.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    markdown = paths.markdown.read_text(encoding="utf-8")
    assert json_report["usage"]["reasoning_tokens"] == reasoning_tokens
    assert json_report["usage"]["output_tokens"] == 16002
    if reasoning_tokens is None:
        assert "Reasoning tokens: unavailable" in markdown
    assert json_report["workbook_row_recall"]["caught"] == 1
    assert json_report["request_duration_sum_seconds"] == 0
    assert csv_rows[0]["model_caught"] == "True"
    assert csv_rows[0]["workbook_recall_caught"] == "1"
    assert csv_rows[0]["request_duration_sum_seconds"] == "0"
    assert "1/1 (100.00%)" in markdown
    assert "Input tokens: 0" in markdown
    assert "Request duration sum: 0s" in markdown
    assert "finding1" in markdown
    assert REVIEW.rationale in markdown


def test_equal_recall_is_ranked_only_by_unrounded_audit_cost() -> None:
    """Operational metrics cannot displace cost as the recall tie-breaker."""
    references = ReferenceSet(
        version="v1",
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        homepage_url="https://example.test/",
        references=(_reference("ref1", "llm_eligible"),),
    )
    finding = _finding("finding1")
    base_run = RunMetadata(
        run_id="expensive",
        model="model-expensive",
        complete=True,
        comparable_identity="benchmark-v1",
        audit_cost_usd="0.0012349",
        workbook_sha256="a" * 64,
        snapshot_sha256="snapshot-v1",
        reference_set_version="v1",
        prompt_hashes_identity="prompts-v1",
        parser_identity="parser-v1",
        eligibility_identity="eligibility-v1",
        configuration_identity="configuration-v1",
    )
    expensive_finding = replace(
        finding,
        run_id=base_run.run_id,
        model=base_run.model,
    )
    expensive = score_evaluation(
        references,
        (expensive_finding,),
        (),
        (_match("ref1", "finding1"),),
        (),
        base_run,
    )
    cheap = score_evaluation(
        references,
        (replace(finding, run_id="cheap", model="model-cheap"),),
        (),
        (_match("ref1", "finding1"),),
        (),
        replace(
            base_run,
            run_id="cheap",
            model="model-cheap",
            audit_cost_usd="0.0012341",
            wall_time_seconds=999,
        ),
    )

    assert [score.model for score in rank_scores((expensive, cheap))] == [
        "model-cheap",
        "model-expensive",
    ]

    incompatible = score_evaluation(
        replace(references, version="v2"),
        (replace(finding, run_id="incompatible", model="other"),),
        (),
        (_match("ref1", "finding1"),),
        (),
        replace(
            base_run,
            run_id="incompatible",
            model="other",
            reference_set_version="v2",
        ),
    )
    with pytest.raises(ValueError, match="incompatible benchmark"):
        rank_scores((expensive, incompatible))

    for field in (
        "snapshot_sha256",
        "prompt_hashes_identity",
        "parser_identity",
        "eligibility_identity",
        "configuration_identity",
    ):
        changed_run = replace(
            base_run,
            run_id=f"changed-{field}",
            model="other",
            **{field: "changed"},
        )
        changed = score_evaluation(
            references,
            (
                replace(
                    finding,
                    run_id=changed_run.run_id,
                    model=changed_run.model,
                ),
            ),
            (),
            (_match("ref1", "finding1"),),
            (),
            changed_run,
        )
        with pytest.raises(ValueError, match="incompatible benchmark"):
            rank_scores((expensive, changed))
