"""Command-line shell for the private model-evaluation lifecycle."""

import argparse
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from vision_aid.evaluation.matching import (
    HumanMatchReviewer,
    MatchValidationError,
    export_match_workbook,
)
from vision_aid.evaluation.references import (
    HumanEligibilityReviewer,
    ReferenceSetError,
    export_eligibility_workbook,
    import_homepage_references,
)
from vision_aid.evaluation.reporting import write_reports
from vision_aid.evaluation.scoring import score_evaluation
from vision_aid.evaluation.serialization import (
    load_findings,
    load_match_decisions,
    load_reference_set,
    load_verified_run_metadata,
    reference_set_identity,
    save_match_decisions,
    save_reference_set,
)
from vision_aid.evaluation.snapshot import prepare_benchmark_snapshot
from vision_aid.evaluation.workspace import (
    DEFAULT_WORKBOOK_FILENAME,
    PrivateInputError,
    PrivateWorkspace,
    require_private_workbook,
)

CommandHandler = Callable[[argparse.Namespace], int]


def build_parser() -> argparse.ArgumentParser:
    """Build the discoverable evaluation command hierarchy."""
    parser = argparse.ArgumentParser(
        prog="visionaid-evaluate",
        description=(
            "Prepare, audit, review, and report private model evaluations "
            "without committing private data or spending money by default."
        ),
    )
    workflows = parser.add_subparsers(
        title="workflows",
        dest="workflow",
        required=True,
    )

    prepare = workflows.add_parser(
        "prepare",
        help="initialize private inputs and artifact directories",
    )
    prepare.add_argument(
        "--workbook",
        type=Path,
        default=Path(DEFAULT_WORKBOOK_FILENAME),
        help=(
            "authorized local source workbook "
            f"(default: ./{DEFAULT_WORKBOOK_FILENAME})"
        ),
    )
    prepare.add_argument(
        "--workbook-sha256",
        help="authorized SHA-256 required to import homepage reference rows",
    )
    prepare.add_argument(
        "--homepage-url",
        help=(
            "canonical Pristine homepage URL used to select Home and Global "
            "rows"
        ),
    )
    prepare.add_argument(
        "--reference-set-version",
        default="pristine-homepage-v1",
        help="curator-assigned version for the imported reference set",
    )
    prepare.add_argument(
        "--snapshot-url",
        help="HTTP(S) source URL for an immutable Pristine homepage capture",
    )
    prepare.add_argument(
        "--temporal-assumption",
        help=(
            "stakeholder-supported statement relating a new capture to the "
            "workbook audit"
        ),
    )
    prepare.set_defaults(handler=_prepare)

    audit = workflows.add_parser(
        "audit",
        help="inspect the prepared audit plan in network-free dry-run mode",
    )
    audit.add_argument(
        "--live", action="store_true", help="enable billable execution"
    )
    audit.add_argument(
        "--plan", type=Path, help="exact dry-run manifest to execute"
    )
    audit.add_argument(
        "--authorize", help="authorization digest shown by dry run"
    )
    audit.add_argument(
        "--max-audit-cost-usd", help="required live cost guardrail"
    )
    audit.add_argument(
        "--reference-set", type=Path, help="approved reference-set JSON"
    )
    audit.add_argument(
        "--run-dir", type=Path, help="private output directory for the plan"
    )
    audit.set_defaults(handler=_audit)

    review = workflows.add_parser(
        "review",
        help="work with private eligibility and match review artifacts",
    )
    review.add_argument(
        "--eligibility-workbook",
        type=Path,
        help="apply a completed Eligibility workbook",
    )
    review.add_argument(
        "--reference-set", type=Path, help="reference-set JSON input"
    )
    review.add_argument(
        "--findings", type=Path, help="canonical findings JSON"
    )
    review.add_argument(
        "--matches-workbook",
        type=Path,
        help="generate or apply a Matches workbook",
    )
    review.add_argument(
        "--import-matches",
        action="store_true",
        help=(
            "import decisions from --matches-workbook instead of generating it"
        ),
    )
    review.set_defaults(handler=_review)

    report = workflows.add_parser(
        "report",
        help="generate private evaluation reports",
    )
    report.add_argument(
        "--bundle",
        type=Path,
        help="private JSON bundle containing score inputs",
    )
    report.add_argument(
        "--output-dir", type=Path, help="private report directory"
    )
    report.set_defaults(handler=_report)
    return parser


def _prepare(arguments: argparse.Namespace) -> int:
    """Validate the private workbook before creating the workspace layout."""
    workbook = require_private_workbook(arguments.workbook)
    workspace = PrivateWorkspace.from_current_directory()
    workspace.initialize()
    resolved_workspace = workspace.root.resolve()
    print(f"Private evaluation workspace initialized at {resolved_workspace}")
    print(f"Private source workbook: {workbook}")
    if bool(arguments.workbook_sha256) != bool(arguments.homepage_url):
        raise PrivateInputError(
            "Reference import requires both --workbook-sha256 and "
            "--homepage-url."
        )
    if arguments.workbook_sha256:
        reference_set = import_homepage_references(
            workbook,
            expected_sha256=arguments.workbook_sha256,
            homepage_url=arguments.homepage_url,
            version=arguments.reference_set_version,
        )
        imported_path = workspace.root / "references" / "imported.json"
        review_path = workspace.root / "reviews" / "eligibility.xlsx"
        save_reference_set(imported_path, reference_set)
        export_eligibility_workbook(reference_set, review_path)
        print(f"Imported reference set: {imported_path.resolve()}")
        print(f"Eligibility review workbook: {review_path.resolve()}")
    if arguments.temporal_assumption and not arguments.snapshot_url:
        raise PrivateInputError(
            "--temporal-assumption requires --snapshot-url."
        )
    if arguments.snapshot_url:
        snapshot = prepare_benchmark_snapshot(
            workspace,
            source_url=arguments.snapshot_url,
            temporal_assumption=arguments.temporal_assumption,
        )
        action = "reused" if snapshot.reused else "captured"
        print(f"Benchmark snapshot {action}: {snapshot.html_path.resolve()}")
        print(f"Benchmark SHA-256: {snapshot.metadata.sha256}")
    return 0


def _audit(arguments: argparse.Namespace) -> int:
    """Build a no-cost plan or execute its exact authorized configuration."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    if arguments.live:
        from vision_aid.evaluation.audit import execute_authorized_audit

        if arguments.plan is None:
            raise PrivateInputError(
                "--live requires --plan from a reviewed dry run."
            )
        manifest = execute_authorized_audit(
            arguments.plan,
            live=True,
            authorization=arguments.authorize,
            api_key=os.environ.get("OPENAI_API_KEY"),
            max_audit_cost_usd=arguments.max_audit_cost_usd,
        )
        print(f"Live run complete: {manifest['complete']}")
        print(f"Estimated audit cost: ${manifest['estimated_audit_cost_usd']}")
        return 0
    reference_path = arguments.reference_set or (
        workspace.root / "references" / "approved.json"
    )
    snapshot_directory = workspace.root / "snapshots" / "pristine-homepage"
    snapshot_path = snapshot_directory / "source.html"
    metadata_path = snapshot_directory / "metadata.json"
    if (
        reference_path.is_file()
        and snapshot_path.is_file()
        and metadata_path.is_file()
    ):
        from vision_aid.evaluation.audit import (
            build_audit_plan,
            live_authorization_digest,
        )

        reference_set = load_reference_set(reference_path)
        if any(
            item.eligibility_state != "accepted"
            for item in reference_set.references
        ):
            raise PrivateInputError(
                "The reference set has unresolved eligibility decisions."
            )
        snapshot_metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        eligibility_identity = reference_set_identity(reference_set)
        run_directory = (
            arguments.run_dir or workspace.root / "runs" / "dry-run"
        )
        plan = build_audit_plan(
            snapshot_path,
            run_directory,
            workbook_sha256=reference_set.workbook_sha256,
            snapshot_sha256=snapshot_metadata["sha256"],
            reference_set_version=reference_set.version,
            eligibility_identity=eligibility_identity,
            homepage_url=reference_set.homepage_url,
        )
        print(f"DRY RUN: {plan['request_count']} sequential requests planned.")
        print(f"Estimated input tokens: {plan['estimated_input_tokens']}")
        print(f"Plan digest: {plan['plan_digest']}")
        if arguments.max_audit_cost_usd:
            authorization = live_authorization_digest(
                plan["plan_digest"],
                arguments.max_audit_cost_usd,
            )
            print(f"Live authorization digest: {authorization}")
        print(
            f"Plan: {(run_directory / 'evaluation-manifest.json').resolve()}"
        )
        return 0
    print(
        "DRY RUN: No network requests were made and no API usage was incurred."
    )
    print(f"Private evaluation workspace: {workspace.root.resolve()}")
    return 0


def _review(arguments: argparse.Namespace) -> int:
    """Expose the private review workflow shell."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    if arguments.eligibility_workbook:
        reference_path = arguments.reference_set or (
            workspace.root / "references" / "imported.json"
        )
        reviewed = HumanEligibilityReviewer(
            arguments.eligibility_workbook
        ).review(load_reference_set(reference_path))
        approved_path = workspace.root / "references" / "approved.json"
        save_reference_set(approved_path, reviewed)
        print(f"Validated reference set: {approved_path.resolve()}")
        return 0
    if arguments.matches_workbook:
        if not arguments.reference_set or not arguments.findings:
            raise PrivateInputError(
                "Match review requires --reference-set and --findings."
            )
        references = load_reference_set(arguments.reference_set).references
        findings = load_findings(arguments.findings)
        if arguments.import_matches:
            decisions = HumanMatchReviewer(arguments.matches_workbook).review(
                references,
                findings,
            )
            output = workspace.root / "reviews" / "match-decisions.json"
            save_match_decisions(output, decisions)
            print(f"Validated match decisions: {output.resolve()}")
        else:
            export_match_workbook(
                references, findings, arguments.matches_workbook
            )
            resolved_review = arguments.matches_workbook.resolve()
            print(f"Matches review workbook: {resolved_review}")
        return 0
    print(
        f"Private review workspace: {(workspace.root / 'reviews').resolve()}"
    )
    return 0


def _report(arguments: argparse.Namespace) -> int:
    """Expose the private report workflow shell."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    if arguments.bundle:
        bundle = json.loads(arguments.bundle.read_text(encoding="utf-8"))
        base = arguments.bundle.parent
        reference_set = load_reference_set(base / bundle["reference_set"])
        if "run_manifest" not in bundle:
            raise PrivateInputError(
                "Report bundles require run_manifest so benchmark identities "
                "can be verified."
            )
        score = score_evaluation(
            reference_set,
            load_findings(base / bundle["audit_findings"]),
            load_findings(base / bundle["programmatic_findings"]),
            load_match_decisions(base / bundle["audit_matches"]),
            load_match_decisions(base / bundle["programmatic_matches"]),
            load_verified_run_metadata(
                base / bundle["run_manifest"],
                reference_set,
            ),
            parse_failures=tuple(bundle.get("parse_failures", ())),
        )
        output_directory = arguments.output_dir or workspace.root / "reports"
        paths = write_reports(score, output_directory)
        print(f"JSON report: {paths.json.resolve()}")
        print(f"CSV report: {paths.csv.resolve()}")
        print(f"Markdown report: {paths.markdown.resolve()}")
        return 0
    print(
        f"Private report workspace: {(workspace.root / 'reports').resolve()}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested evaluation workflow and render actionable errors."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    handler: CommandHandler = arguments.handler
    try:
        return handler(arguments)
    except (
        MatchValidationError,
        PrivateInputError,
        ReferenceSetError,
        OSError,
        ValueError,
    ) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
