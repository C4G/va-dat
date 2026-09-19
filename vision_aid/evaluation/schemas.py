"""Canonical, JSON-compatible records shared by evaluation stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Eligibility = Literal[
    "llm_eligible",
    "programmatic",
    "unavailable_evidence",
    "ambiguous",
]
DecisionState = Literal["accepted", "rejected", "needs_review"]


@dataclass(frozen=True)
class ReviewProvenance:
    """Who made a review decision and why."""

    reviewer: str
    rationale: str
    confidence: float
    timestamp: str


@dataclass(frozen=True)
class ReferenceDefect:
    """One workbook source row retained as one benchmark scoring unit."""

    reference_id: str
    workbook_filename: str
    workbook_sha256: str
    source_sheet: str
    source_row: int
    raw_evidence: dict[str, str]
    canonical_url: str
    page_scope: Literal["home", "global"]
    problem: str
    location: str
    wcag_evidence: tuple[str, ...]
    recommendation: str = ""
    required_subdefects: tuple[str, ...] = ()
    eligibility: Eligibility | None = None
    eligibility_state: DecisionState | None = None
    eligibility_review: ReviewProvenance | None = None


@dataclass(frozen=True)
class ReferenceSet:
    """Versioned collection of imported or reviewed reference defects."""

    version: str
    workbook_filename: str
    workbook_sha256: str
    homepage_url: str
    references: tuple[ReferenceDefect, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return asdict(self)


@dataclass(frozen=True)
class CanonicalFinding:
    """Lossless normalized output from one audit or programmatic source."""

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


@dataclass(frozen=True)
class MatchDecision:
    """Reviewed relationship between one finding and one reference defect."""

    reference_id: str
    finding_id: str
    state: DecisionState
    provenance: ReviewProvenance
    required_subdefect: str | None = None
    page_compatible: bool | None = None
    failure_compatible: bool | None = None
    location_compatible: bool | None = None
    notes: str = ""


@dataclass(frozen=True)
class Usage:
    """Token categories reported by providers across all attempts."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class RunMetadata:
    """Operational facts used by deterministic scoring and comparison."""

    run_id: str
    model: str
    complete: bool
    comparable_identity: str
    audit_cost_usd: str
    evaluation_cost_usd: str = "0"
    usage: Usage = field(default_factory=Usage)
    wall_time_seconds: float = 0
    request_durations_seconds: tuple[float, ...] = ()
    workbook_sha256: str = ""
    snapshot_sha256: str = ""
    reference_set_version: str = ""
    prompt_hashes_identity: str = ""
    parser_identity: str = ""
    eligibility_identity: str = ""
    configuration_identity: str = ""
