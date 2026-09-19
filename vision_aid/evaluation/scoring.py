"""Network-free deterministic workbook-row scoring and ranking."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from vision_aid.evaluation.matching import validate_match_decisions
from vision_aid.evaluation.schemas import (
    CanonicalFinding,
    MatchDecision,
    ReferenceDefect,
    ReferenceSet,
    RunMetadata,
)


def _metric(caught: int, denominator: int) -> dict[str, int | str]:
    rate = Decimal(caught) / Decimal(denominator) if denominator else Decimal(0)
    return {"caught": caught, "denominator": denominator, "rate": str(rate)}


@dataclass(frozen=True)
class RowScore:
    """Explain the final disposition for one workbook source row."""

    reference_id: str
    source_sheet: str
    source_row: int
    page_scope: str
    eligibility: str
    eligibility_rationale: str
    problem: str
    location: str
    programmatic_caught: bool
    model_caught: bool
    model_finding_ids: tuple[str, ...]
    programmatic_finding_ids: tuple[str, ...]
    disposition: str


@dataclass(frozen=True)
class EvaluationScore:
    """The complete deterministic object from which every report is projected."""

    run_id: str
    model: str
    complete: bool
    rankable: bool
    comparable_identity: str
    reference_set_version: str
    workbook_sha256: str
    workbook_row_recall: dict[str, int | str]
    programmatic_coverage: dict[str, int | str]
    combined_workbook_coverage: dict[str, int | str]
    audit_cost_usd: str
    evaluation_cost_usd: str
    total_experiment_cost_usd: str
    usage: dict[str, int]
    wall_time_seconds: float
    request_durations_seconds: tuple[float, ...]
    unmatched_audit_finding_ids: tuple[str, ...]
    parse_failures: tuple[str, ...]
    rows: tuple[RowScore, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-compatible score representation."""
        return asdict(self)


def _caught_references(
    references: Sequence[ReferenceDefect],
    decisions: Sequence[MatchDecision],
) -> tuple[set[str], dict[str, tuple[str, ...]]]:
    accepted = [item for item in decisions if item.state == "accepted"]
    by_reference: dict[str, list[MatchDecision]] = {}
    for decision in accepted:
        by_reference.setdefault(decision.reference_id, []).append(decision)
    caught: set[str] = set()
    evidence: dict[str, tuple[str, ...]] = {}
    for reference in references:
        matches = by_reference.get(reference.reference_id, [])
        if reference.required_subdefects:
            matched_parts = {item.required_subdefect for item in matches}
            is_caught = set(reference.required_subdefects) <= matched_parts
        else:
            is_caught = bool(matches)
        if is_caught:
            caught.add(reference.reference_id)
        evidence[reference.reference_id] = tuple(
            sorted(item.finding_id for item in matches)
        )
    return caught, evidence


def score_evaluation(
    reference_set: ReferenceSet,
    audit_findings: Sequence[CanonicalFinding],
    programmatic_findings: Sequence[CanonicalFinding],
    audit_matches: Sequence[MatchDecision],
    programmatic_matches: Sequence[MatchDecision],
    run: RunMetadata,
    *,
    parse_failures: Sequence[str] = (),
) -> EvaluationScore:
    """Calculate binary workbook-row credit from approved normalized inputs."""
    unapproved = [
        item.reference_id
        for item in reference_set.references
        if item.eligibility_state != "accepted" or item.eligibility is None
    ]
    if unapproved:
        raise ValueError(
            "Scoring requires accepted eligibility decisions for every reference: "
            + ", ".join(unapproved)
        )
    audit_matches = validate_match_decisions(
        reference_set.references,
        audit_findings,
        audit_matches,
    )
    programmatic_matches = validate_match_decisions(
        reference_set.references,
        programmatic_findings,
        programmatic_matches,
    )
    model_caught, model_evidence = _caught_references(
        reference_set.references, audit_matches
    )
    programmatic_caught, programmatic_evidence = _caught_references(
        reference_set.references, programmatic_matches
    )
    llm_references = {
        item.reference_id
        for item in reference_set.references
        if item.eligibility == "llm_eligible"
    }
    programmatic_references = {
        item.reference_id
        for item in reference_set.references
        if item.eligibility == "programmatic"
    }
    combined = model_caught | programmatic_caught
    rows = []
    for reference in reference_set.references:
        model_hit = reference.reference_id in model_caught
        programmatic_hit = reference.reference_id in programmatic_caught
        if model_hit and programmatic_hit:
            disposition = "caught_by_both"
        elif model_hit:
            disposition = "caught_by_model"
        elif programmatic_hit:
            disposition = "caught_programmatically"
        elif reference.eligibility == "programmatic":
            disposition = "programmatic_gap"
        elif reference.eligibility == "unavailable_evidence":
            disposition = "unavailable_evidence"
        elif reference.eligibility == "ambiguous":
            disposition = "ambiguous"
        else:
            disposition = "missed_by_model"
        rows.append(
            RowScore(
                reference_id=reference.reference_id,
                source_sheet=reference.source_sheet,
                source_row=reference.source_row,
                page_scope=reference.page_scope,
                eligibility=reference.eligibility or "",
                eligibility_rationale=(
                    reference.eligibility_review.rationale
                    if reference.eligibility_review
                    else ""
                ),
                problem=reference.problem,
                location=reference.location,
                programmatic_caught=programmatic_hit,
                model_caught=model_hit,
                model_finding_ids=model_evidence[reference.reference_id],
                programmatic_finding_ids=programmatic_evidence[reference.reference_id],
                disposition=disposition,
            )
        )
    accepted_audit_ids = {
        item.finding_id for item in audit_matches if item.state == "accepted"
    }
    total_cost = Decimal(run.audit_cost_usd) + Decimal(run.evaluation_cost_usd)
    return EvaluationScore(
        run_id=run.run_id,
        model=run.model,
        complete=run.complete,
        rankable=run.complete,
        comparable_identity=run.comparable_identity,
        reference_set_version=reference_set.version,
        workbook_sha256=reference_set.workbook_sha256,
        workbook_row_recall=_metric(
            len(model_caught & llm_references), len(llm_references)
        ),
        programmatic_coverage=_metric(
            len(programmatic_caught & programmatic_references),
            len(programmatic_references),
        ),
        combined_workbook_coverage=_metric(
            len(combined), len(reference_set.references)
        ),
        audit_cost_usd=run.audit_cost_usd,
        evaluation_cost_usd=run.evaluation_cost_usd,
        total_experiment_cost_usd=str(total_cost),
        usage=asdict(run.usage),
        wall_time_seconds=run.wall_time_seconds,
        request_durations_seconds=run.request_durations_seconds,
        unmatched_audit_finding_ids=tuple(
            sorted(
                item.finding_id
                for item in audit_findings
                if item.finding_id not in accepted_audit_ids
            )
        ),
        parse_failures=tuple(sorted(parse_failures)),
        rows=tuple(rows),
    )


def rank_scores(scores: Sequence[EvaluationScore]) -> tuple[EvaluationScore, ...]:
    """Rank comparable complete runs by recall, then unrounded audit cost only."""
    if any(not item.rankable for item in scores):
        raise ValueError("An incomplete run is unranked and cannot be compared.")
    identities = {item.comparable_identity for item in scores}
    if len(identities) > 1:
        raise ValueError(
            "Runs use incompatible benchmark versions; cross-version analysis must "
            "be explicitly requested and labeled."
        )
    return tuple(
        sorted(
            scores,
            key=lambda item: (
                -Decimal(str(item.workbook_row_recall["rate"])),
                Decimal(item.audit_cost_usd),
                item.run_id,
            ),
        )
    )
