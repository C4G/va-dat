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
    return f"{Decimal(str(metric['rate'])) * 100:.2f}%"


def write_reports(score: EvaluationScore, output_directory: Path) -> ReportPaths:
    """Write three consistent views without recalculating any score."""
    output_directory.mkdir(parents=True, exist_ok=True)
    base = output_directory / score.run_id
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    markdown_path = base.with_suffix(".md")
    json_path.write_text(
        json.dumps(score.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    row_dicts = [asdict(row) for row in score.rows]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        if row_dicts:
            writer = csv.DictWriter(stream, fieldnames=list(row_dicts[0]))
            writer.writeheader()
            for data_row in row_dicts:
                data_row["model_finding_ids"] = "; ".join(data_row["model_finding_ids"])
                data_row["programmatic_finding_ids"] = "; ".join(
                    data_row["programmatic_finding_ids"]
                )
                writer.writerow(data_row)
    recall = score.workbook_row_recall
    programmatic = score.programmatic_coverage
    combined = score.combined_workbook_coverage
    lines = [
        f"# Illustrative model evaluation: {score.model}",
        "",
        (
            "> This homepage result is illustrative and does not establish broad "
            "small-versus-large model equivalence."
        ),
        "",
        (
            f"- Workbook-row recall: {recall['caught']}/{recall['denominator']} "
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
        f"- Estimated total experiment cost: ${score.total_experiment_cost_usd}",
        f"- Complete and rankable: {score.rankable}",
        f"- Format failures: {len(score.parse_failures)}",
        f"- Unmatched audit findings: {len(score.unmatched_audit_finding_ids)}",
        "",
        "| Source row | Eligibility | Programmatic | Model | Disposition |",
        "|---|---|---:|---:|---|",
    ]
    for report_row in score.rows:
        lines.append(
            f"| {report_row.source_sheet}!{report_row.source_row} | "
            f"{report_row.eligibility} | {report_row.programmatic_caught} | "
            f"{report_row.model_caught} | {report_row.disposition} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ReportPaths(json=json_path, csv=csv_path, markdown=markdown_path)
