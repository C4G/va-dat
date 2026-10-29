"""Run CLI fixtures with approved mappings retained throughout execution and review."""

import json

from vision_aid.evaluation import human_finding_mapping
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


def run_with_mapping(workspace, arguments):
    """Supply approved fixture decisions unless the caller selects a mapping."""
    if "--human-finding-mapping" in arguments:
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
    if (human_finding_mapping.HUMAN_FINDING_MAPPING_DIRECTORY / f"{checksum}.json").is_file():
        return main(arguments)
    decisions = {}
    for url, audit in audits.items():
        for finding in audit.human_findings:
            decision = decisions.setdefault(
                finding.human_finding_id,
                {
                    "human_finding_id": finding.human_finding_id,
                    "classification": "llm_eligible",
                    "classification_reason": "Approved fixture decisions",
                    "programmatic_by_page": {},
                },
            )
            decision["programmatic_by_page"][url] = {
                "expectations": [],
                "reason": "Approved fixture decisions",
            }
    source = workspace / "fixture-human-finding-mapping.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "human_audit_sha256": checksum,
                "approved_by": "Approved fixture decisions",
                "decisions": list(decisions.values()),
            }
        )
    )
    return main([*arguments, "--human-finding-mapping", str(source)])
