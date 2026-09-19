"""JSON, CSV, and Markdown projections of one evaluation score."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from vision_aid.evaluation.scoring import EvaluationScore


@dataclass(frozen=True)
class ReportPaths:
    """Files written for one score object."""

    json: Path
    csv: Path
    markdown: Path


def _percentage(metric: dict[str, int | str]) -> str:
    """Format one metric rate for the human report."""
    return f"{Decimal(str(metric['rate'])) * 100:.2f}%"


def _markdown(value: object) -> str:
    """Keep multiline evidence inside one safe Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def write_reports(
    score: EvaluationScore, output_directory: Path
) -> ReportPaths:
    """Write three consistent views without recalculating any score."""
    output_directory.mkdir(parents=True, exist_ok=True)
    base = output_directory / score.run_id
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    markdown_path = base.with_suffix(".md")
    json_path.write_text(
        json.dumps(
            score.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    common = {
        "run_id": score.run_id,
        "model": score.model,
        "complete": score.complete,
        "rankable": score.rankable,
        "workbook_recall_caught": score.workbook_row_recall["caught"],
        "workbook_recall_denominator": score.workbook_row_recall[
            "denominator"
        ],
        "workbook_recall_rate": score.workbook_row_recall["rate"],
        "programmatic_coverage_caught": score.programmatic_coverage["caught"],
        "programmatic_coverage_denominator": score.programmatic_coverage[
            "denominator"
        ],
        "programmatic_coverage_rate": score.programmatic_coverage["rate"],
        "combined_caught": score.combined_workbook_coverage["caught"],
        "combined_denominator": score.combined_workbook_coverage[
            "denominator"
        ],
        "combined_rate": score.combined_workbook_coverage["rate"],
        "audit_cost_usd": score.audit_cost_usd,
        "evaluation_cost_usd": score.evaluation_cost_usd,
        "total_experiment_cost_usd": score.total_experiment_cost_usd,
        **score.usage,
        "wall_time_seconds": score.wall_time_seconds,
        "request_duration_sum_seconds": score.request_duration_sum_seconds,
        "request_durations_seconds": json.dumps(
            score.request_durations_seconds
        ),
        "parse_failure_count": len(score.parse_failures),
        "unmatched_audit_finding_count": len(
            score.unmatched_audit_finding_ids
        ),
    }
    row_dicts = [{**common, **asdict(row)} for row in score.rows]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        if row_dicts:
            writer = csv.DictWriter(stream, fieldnames=list(row_dicts[0]))
            writer.writeheader()
            for data_row in row_dicts:
                data_row["model_finding_ids"] = "; ".join(
                    data_row["model_finding_ids"]
                )
                data_row["programmatic_finding_ids"] = "; ".join(
                    data_row["programmatic_finding_ids"]
                )
                data_row["model_evidence"] = "; ".join(
                    data_row["model_evidence"]
                )
                data_row["programmatic_evidence"] = "; ".join(
                    data_row["programmatic_evidence"]
                )
                writer.writerow(data_row)
    recall = score.workbook_row_recall
    programmatic = score.programmatic_coverage
    combined = score.combined_workbook_coverage
    lines = [
        f"# Illustrative model evaluation: {score.model}",
        "",
        (
            "> This homepage result is illustrative and does not establish "
            "broad "
            "small-versus-large model equivalence."
        ),
        "",
        (
            "- Workbook-row recall: "
            f"{recall['caught']}/{recall['denominator']} "
            f"({_percentage(recall)})"
        ),
        (
            f"- Programmatic coverage: {programmatic['caught']}/"
            f"{programmatic['denominator']} ({_percentage(programmatic)})"
        ),
        (
            f"- Combined workbook coverage: {combined['caught']}/"
            f"{combined['denominator']} ({_percentage(combined)})"
        ),
        f"- Estimated audit cost: ${score.audit_cost_usd}",
        f"- Estimated evaluation cost: ${score.evaluation_cost_usd}",
        (
            "- Estimated total experiment cost: "
            f"${score.total_experiment_cost_usd}"
        ),
        f"- Input tokens: {score.usage['input_tokens']}",
        f"- Cached input tokens: {score.usage['cached_input_tokens']}",
        f"- Output tokens: {score.usage['output_tokens']}",
        f"- Reasoning tokens: {score.usage['reasoning_tokens']}",
        (
            "- Cache-creation input tokens: "
            f"{score.usage['cache_creation_input_tokens']}"
        ),
        f"- End-to-end wall time: {score.wall_time_seconds:g}s",
        f"- Request duration sum: {score.request_duration_sum_seconds:g}s",
        "- Per-request durations: "
        + json.dumps(score.request_durations_seconds),
        f"- Complete and rankable: {score.rankable}",
        f"- Format failures: {len(score.parse_failures)}",
        (
            "- Unmatched audit findings: "
            f"{len(score.unmatched_audit_finding_ids)}"
        ),
        "",
        (
            "| Source row | Problem | Location | Eligibility | Rationale | "
            "Programmatic evidence | Model evidence | Disposition |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for report_row in score.rows:
        lines.append(
            f"| {report_row.source_sheet}!{report_row.source_row} | "
            f"{_markdown(report_row.problem)} | "
            f"{_markdown(report_row.location)} | "
            f"{report_row.eligibility} | "
            f"{_markdown(report_row.eligibility_rationale)} | "
            f"{_markdown('; '.join(report_row.programmatic_evidence))} | "
            f"{_markdown('; '.join(report_row.model_evidence))} | "
            f"{report_row.disposition} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ReportPaths(json=json_path, csv=csv_path, markdown=markdown_path)
