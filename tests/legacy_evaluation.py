"""Construct historical review fixtures while exercising approved new-run execution.

Older scoring tests deliberately review responsibilities per run. Their fixtures
start through today's CLI with an explicit baseline, then remove that source to
represent an already-saved evaluation from before shared baselines existed.
Current baseline tests supply their own source and never use this conversion.
"""

import csv
import json

from vision_aid.evaluation import baseline
from vision_aid.evaluation.cli import main
from vision_aid.evaluation.inputs.human_audit import (
    import_all_human_findings,
    import_page_human_findings,
)


def _argument(arguments, name):
    """Respect the CLI's last occurrence of a repeated option."""
    return next(
        arguments[index + 1]
        for index in reversed(range(len(arguments)))
        if arguments[index] == name
    )


def _historical_review(run):
    """Represent an older saved run whose classifications were originally editable."""
    for manifest_path in [run / "full.json", *run.rglob("run.json")]:
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        manifest.pop("evaluation_baseline_sha256", None)
        manifest.pop("evaluation_baseline_approved_by", None)
        manifest_path.write_text(json.dumps(manifest))
        source = manifest_path.parent / baseline.BASELINE_ARTIFACT
        source.unlink(missing_ok=True)
    for path in run.rglob("review.csv"):
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            fields = [
                column
                for column in reader.fieldnames
                if column != "programmatic_match_reason"
            ]
            rows = list(reader)
        for row in rows:
            row.pop("programmatic_match_reason", None)
            row.update(
                classification="", classification_reason="", programmatic_finding_id=""
            )
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def historical_run_cli(workspace, arguments):
    """Run with approved fixture decisions, then simulate a historical source format."""
    if "--human-finding-mapping" in arguments or "--baseline" in arguments:
        return main(arguments)
    audit_path = workspace / _argument(arguments, "--human-audit")
    try:
        audits = (
            import_all_human_findings(audit_path)
            if arguments[0] == "run-all"
            else {
                _argument(arguments, "--source-url"): import_page_human_findings(
                    audit_path,
                    _argument(arguments, "--source-url"),
                ),
            }
        )
    except (OSError, ValueError, KeyError):
        return main(arguments)
    checksum = next(iter(audits.values())).human_audit_sha256
    if (baseline.BASELINE_DIRECTORY / f"{checksum}.json").is_file():
        return main(arguments)
    decisions = {}
    for url, audit in audits.items():
        for finding in audit.human_findings:
            decision = decisions.setdefault(
                finding.human_finding_id,
                {
                    "human_finding_id": finding.human_finding_id,
                    "classification": "llm_eligible",
                    "classification_reason": "Historical fixture setup",
                    "programmatic_by_page": {},
                },
            )
            decision["programmatic_by_page"][url] = {
                "expectations": [],
                "reason": "Historical fixture setup",
            }
    source = workspace / "historical-setup-baseline.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "human_audit_sha256": checksum,
                "approved_by": "Historical fixture setup",
                "decisions": list(decisions.values()),
            }
        )
    )
    root = (
        workspace
        / ".model-evaluation"
        / ("full-runs" if arguments[0] == "run-all" else "runs")
    )
    previous = set(root.iterdir()) if root.exists() else set()
    try:
        return main([*arguments, "--baseline", str(source)])
    finally:
        for run in (set(root.iterdir()) if root.exists() else set()) - previous:
            _historical_review(run)
