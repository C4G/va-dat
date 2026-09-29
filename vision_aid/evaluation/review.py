"""One editable CSV for human decisions and one deterministic Markdown report."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any

from vision_aid.evaluation.human_audit import ELIGIBILITY_VALUES, HEADERS

DECISION_COLUMNS = (
    "classification",
    "classification_reason",
    "llm_finding_id",
    "programmatic_finding_id",
    "match_reason",
    "review_notes",
)
REVIEW_COLUMNS = (
    "human_finding_id",
    "source_sheet",
    "source_row",
    "page_scope",
    "source_element",
    *HEADERS,
    *DECISION_COLUMNS,
)


def create_review(path: Path, human_findings: list[dict[str, Any]]) -> None:
    """Create one editable row per Human finding with blank decisions."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for item in human_findings:
            writer.writerow(
                {
                    "human_finding_id": item["human_finding_id"],
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
    human_findings: list[dict[str, Any]],
    llm: list[dict[str, Any]],
    programmatic: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate completeness and finding kind before granting any row credit."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(REVIEW_COLUMNS).issubset(reader.fieldnames or ()):
            raise ValueError("Review CSV is missing required columns")
        entered = list(reader)
    expected = {item["human_finding_id"]: item for item in human_findings}
    if len(entered) != len(expected):
        raise ValueError("Review CSV must contain each Human finding exactly once")
    by_kind = {
        "llm": {item["finding_id"]: item for item in llm},
        "programmatic": {item["finding_id"]: item for item in programmatic},
    }
    used: dict[str, set[str]] = {"llm": set(), "programmatic": set()}
    result: dict[str, dict[str, Any]] = {}
    for row in entered:
        human_finding_id = row["human_finding_id"]
        if human_finding_id not in expected or human_finding_id in result:
            raise ValueError(f"Unknown or repeated Human finding: {human_finding_id}")
        human_finding = expected[human_finding_id]
        for field in ("source_sheet", "source_row", "source_element"):
            if str(row[field]) != str(human_finding[field]):
                raise ValueError(
                    f"Human finding identity changed for {human_finding_id}: {field}"
                )
        classification = row["classification"].strip()
        if classification not in ELIGIBILITY_VALUES:
            raise ValueError(f"Human finding {human_finding_id}: invalid classification")
        matched: dict[str, tuple[str, ...]] = {}
        for kind, column, label in (
            ("llm", "llm_finding_id", "LLM"),
            ("programmatic", "programmatic_finding_id", "Programmatic"),
        ):
            ids = _ids(row[column])
            unknown = set(ids) - set(by_kind[kind])
            if unknown:
                raise ValueError(
                    f"Unknown {label} finding ID: {', '.join(sorted(unknown))}"
                )
            reused = set(ids) & used[kind]
            if reused:
                raise ValueError(
                    f"Conflicting {label} finding ID: {', '.join(sorted(reused))}"
                )
            used[kind].update(ids)
            matched[kind] = ids
        if any(matched.values()) and not row["match_reason"].strip():
            raise ValueError(f"Human finding {human_finding_id} needs a match reason")
        if classification in {"unavailable_evidence", "ambiguous"} and any(
            matched.values()
        ):
            raise ValueError(f"Human finding {human_finding_id} is not testable; cannot claim coverage")
        result[human_finding_id] = {
            "human_finding": human_finding, "decision": row, "matches": matched,
        }
    return [result[identity] for identity in expected]


def _rate(part: str, caught: int, total: int) -> str:
    """Explain each denominator, including when there is nothing to score."""
    if part == "Overall":
        return f"Overall detection rate: Of all {total} Human findings, either part of the tool caught {caught} ({caught / total:.1%})."
    label = part.removesuffix(" checks")
    if total == 0:
        return f"{label} detection rate: No Human findings were expected to be detected by the {part} from the page's HTML."
    subject = "it" if part == "LLM" else "they"
    return f"{label} detection rate: Of the {total} Human findings the {part} could be expected to detect from the page's HTML, {subject} caught {caught} ({caught / total:.1%})."


def _md(value: object) -> str:
    """Escape inline text for Markdown, including raw HTML, keeping line breaks."""
    text = str(value)
    for character in "\\`*_[]|<>":
        text = text.replace(character, "\\" + character)
    return text.replace("\n", "<br>")


def write_report(
    path: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    llm: list[dict[str, Any]],
    programmatic: list[dict[str, Any]],
    reviewer: str,
    pricing_date: str,
) -> None:
    """Explain the review's catches, misses, and scoring in source order."""
    if not manifest["complete"]:
        raise ValueError("Incomplete Evaluation runs cannot produce a final report")
    findings = {item["finding_id"]: item for item in llm + programmatic}
    expected = {
        "llm_eligible": "LLM",
        "programmatic": "Programmatic checks",
        "unavailable_evidence": "Not testable",
        "ambiguous": "Not testable",
    }
    covered = [row for row in rows if any(row["matches"].values())]
    usage = manifest["usage"]
    tokens = [f"{usage['input_tokens']} input tokens", f"{usage['output_tokens']} output tokens"]
    for key, label in (("cached_input_tokens", "cached input"), ("cache_creation_input_tokens", "cache-creation input")):
        if usage[key]:
            tokens.append(f"{usage[key]} {label} tokens")
    lines = [
        f"# LLM accessibility evaluation: {_md(manifest['source_url'])}",
        "",
        "## How to read this report",
        "",
        "The benchmark is the Human audit, an accessibility audit performed by human testers. Each problem they reported is a Human finding.",
        "The tool has two parts. The LLM asks a large language model to judge accessibility problems. Programmatic checks apply fixed rules without AI.",
        "The tool saw only saved HTML, not a live browser or screen reader. This evaluation covers the homepage only, including Global findings that apply there.",
        "A reviewer decided which part should be expected to detect each Human finding. A catch counts only when the matched findings fully cover the whole Human finding. Partial coverage earns no credit.",
        "",
        "## Summary",
        "",
        f"Model: {_md(manifest['configuration']['model'])}. Run ID: {_md(manifest['run_id'])}.",
        f"Review decisions by: {_md(reviewer)}",
        "",
    ]
    for classification, kind, part in (
        ("llm_eligible", "llm", "LLM"),
        ("programmatic", "programmatic", "Programmatic checks"),
    ):
        eligible = [row for row in rows if row["decision"]["classification"].strip() == classification]
        lines.extend([_rate(part, sum(bool(row["matches"][kind]) for row in eligible), len(eligible)), ""])
    lines.extend([
        _rate("Overall", len(covered), len(rows)),
        "",
        f"Estimated run cost: ${Decimal(manifest['estimated_cost_usd']):.2f}, calculated from {', '.join(tokens)} multiplied by the published prices dated {_md(pricing_date)}. The actual bill may differ slightly.",
        "",
    ])
    if manifest["format_failures"]:
        checks = ", ".join(_md(name.replace("_", " ") + " check") for name in manifest["format_failures"])
        lines.extend([f"The LLM returned unreadable output for {len(manifest['format_failures'])} of {len(manifest['prompts'])} checks: {checks}.", ""])
    lines.extend([
        "## Human findings", "",
        "| Issue Title | WCAG | Expected to be caught by | LLM | Programmatic checks |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row in rows:
        human = row["human_finding"]
        marks = ["✓" if row["matches"][kind] else "✗" for kind in ("llm", "programmatic")]
        lines.append(f"| {_md(human['problem'])} | {_md(human['raw_evidence']['WCAG Sc'])} | {expected[row['decision']['classification'].strip()]} | {' | '.join(marks)} |")
    lines.extend([
        "",
        "The LLM and Programmatic detection rates count only catches by the expected part. A catch by the other part still gets a ✓ and counts toward the Overall detection rate, which counts each Human finding once out of all imported Human findings.",
    ])
    groups = {
        "What each part of the tool caught": covered,
        "Missed": [
            row for row in rows
            if expected[row["decision"]["classification"].strip()] != "Not testable"
            and not any(row["matches"].values())
        ],
        "Not testable from the page file": [
            row for row in rows
            if expected[row["decision"]["classification"].strip()] == "Not testable"
        ],
    }
    for heading, group in groups.items():
        lines.extend(["", f"## {heading}", ""])
        if heading == "Not testable from the page file":
            lines.extend(["These Human findings cannot be judged from the saved HTML or are too unclear to judge. They are left out of the LLM and Programmatic detection rates but remain in the Overall denominator.", ""])
        for row in group:
            decision = row["decision"]
            matches = row["matches"]
            lines.extend([f"### {_md(row['human_finding']['problem'])}", ""])
            for kind in ("llm", "programmatic"):
                for identity in matches[kind]:
                    finding = findings[identity]
                    label = (
                        f"LLM ({finding['prompt'].replace('_', ' ')} check)"
                        if kind == "llm" else f"Programmatic check {finding['prompt']}"
                    )
                    lines.extend([f"- {_md(label)}: {_md(finding['problem'])}", f"  Why this counts: {_md(decision['match_reason'])}"])
            if heading == "Not testable from the page file":
                lines.append(_md(decision["classification_reason"]))
            elif not any(matches.values()):
                for field, label in (
                    ("classification_reason", "Why it was expected to be caught"),
                    ("review_notes", "Why it was missed"),
                ):
                    if decision[field].strip():
                        lines.append(f"{label}: {_md(decision[field])}")
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
