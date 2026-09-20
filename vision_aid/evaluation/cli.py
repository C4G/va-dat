"""Command-line shell for the private model-evaluation lifecycle."""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ENV_LOADED = False


def _load_project_env() -> None:
    """Load local evaluation credentials once per CLI process."""
    global _PROJECT_ENV_LOADED
    if _PROJECT_ENV_LOADED:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    _PROJECT_ENV_LOADED = True


@dataclass(frozen=True)
class RequiredRunArtifact:
    """One conventional report input and its optional recovery review kind."""

    label: str
    path: Path
    review_kind: str | None = None


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
        "--auto-approve",
        action="store_true",
        help="deliberately approve live execution without a terminal prompt",
    )
    audit.add_argument(
        "--max-audit-cost-usd", help="required planning cost guardrail"
    )
    audit.add_argument(
        "--run-dir", type=Path, help="planned evaluation run to execute"
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
        "--run-dir", type=Path, help="evaluation run being reviewed"
    )
    review.add_argument(
        "--kind",
        choices=("audit", "programmatic"),
        help="finding collection being reviewed",
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
    review.add_argument(
        "--match-decisions",
        type=Path,
        help="validated match-decision JSON output override",
    )
    review.set_defaults(handler=_review)

    report = workflows.add_parser(
        "report",
        help="generate private evaluation reports",
    )
    report.add_argument(
        "--run-dir", type=Path, required=True, help="evaluation run to report"
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


def _render_execution_summary(
    plan: dict[str, object],
    run_directory: Path,
    approval_mode: str,
) -> str:
    """Render the complete billable intent for planning or live approval."""
    configuration = plan["configuration"]
    assert isinstance(configuration, dict)
    prompts = plan["prompts"]
    assert isinstance(prompts, list)
    prompt_names = ", ".join(str(item["name"]) for item in prompts)
    retry_policy = plan["retry_policy"]
    assert isinstance(retry_policy, dict)
    return "\n".join(
        (
            "Evaluation execution summary",
            f"  Model: {configuration['model']}",
            f"  Endpoint: {configuration['endpoint']}",
            f"  Reasoning effort: {configuration['reasoning_effort']}",
            f"  Benchmark snapshot SHA-256: {plan['snapshot_sha256']}",
            f"  Reference set: {plan['reference_set_version']}",
            f"  Reference identity: {plan['eligibility_identity']}",
            f"  Prompts ({plan['request_count']}): {prompt_names}",
            f"  Estimated input tokens: {plan['estimated_input_tokens']}",
            "  Retry policy: "
            f"{retry_policy['maximum_additional_attempts']} additional "
            f"attempts; backoff {retry_policy['backoff_seconds']}; "
            f"retryable {retry_policy['retryable']}",
            f"  Maximum audit cost: ${plan['maximum_audit_cost_usd']}",
            f"  Destination: {run_directory.resolve()}",
            f"  Approval mode: {approval_mode}",
        )
    )


def _approval_timestamp() -> str:
    """Return the UTC timestamp recorded for live-run approval."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _confirm_live_execution() -> str:
    """Require exact, terminal-originated point-of-use confirmation."""
    if not sys.stdin.isatty():
        raise PrivateInputError(
            "Interactive live-run approval requires a terminal. Use "
            "--auto-approve only for deliberate automation."
        )
    try:
        response = input("Type 'yes' to begin billable execution: ")
    except EOFError as error:
        raise PrivateInputError(
            "Live-run approval ended before confirmation; no request was made."
        ) from error
    if response.strip().casefold() != "yes":
        raise PrivateInputError(
            "Live-run approval was not 'yes'; no request was made."
        )
    return _approval_timestamp()


def _audit(arguments: argparse.Namespace) -> int:
    """Plan a no-cost evaluation run or execute one after explicit approval."""
    _load_project_env()

    from vision_aid.evaluation.audit import (
        build_audit_plan,
        ensure_live_destination_available,
        execute_audit_run,
        load_verified_audit_plan,
        normalize_audit_cost,
    )

    if arguments.auto_approve and not arguments.live:
        raise PrivateInputError("--auto-approve is accepted only with --live.")
    if arguments.live:
        if arguments.run_dir is None:
            raise PrivateInputError("--live requires --run-dir from planning.")
        if arguments.max_audit_cost_usd is not None:
            raise PrivateInputError(
                "Live execution reuses the saved cost guardrail; do not pass "
                "--max-audit-cost-usd."
            )
        run_directory = arguments.run_dir.resolve()
        plan = load_verified_audit_plan(run_directory)
        ensure_live_destination_available(run_directory)
        if not os.environ.get("OPENAI_API_KEY"):
            raise PrivateInputError(
                "Live execution requires OPENAI_API_KEY in addition to "
                "approval."
            )
        approval_mode = "auto" if arguments.auto_approve else "interactive"
        print(
            _render_execution_summary(plan, run_directory, approval_mode),
            flush=True,
        )
        approved_at = (
            _approval_timestamp()
            if arguments.auto_approve
            else _confirm_live_execution()
        )
        manifest = execute_audit_run(
            run_directory,
            live=True,
            api_key=os.environ.get("OPENAI_API_KEY"),
            approval_mode=approval_mode,
            approved_at=approved_at,
        )
        print(f"Live run complete: {manifest['complete']}")
        print(f"Estimated audit cost: ${manifest['estimated_audit_cost_usd']}")
        return 0
    if arguments.run_dir is not None:
        raise PrivateInputError("--run-dir is accepted only with --live.")
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    reference_path = workspace.root / "references" / "approved.json"
    snapshot_directory = workspace.root / "snapshots" / "pristine-homepage"
    snapshot_path = snapshot_directory / "source.html"
    metadata_path = snapshot_directory / "metadata.json"
    if (
        reference_path.is_file()
        and snapshot_path.is_file()
        and metadata_path.is_file()
    ):
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
        if arguments.max_audit_cost_usd is None:
            raise PrivateInputError(
                "Audit planning requires --max-audit-cost-usd as a positive "
                "spending guardrail."
            )
        maximum_cost = normalize_audit_cost(arguments.max_audit_cost_usd)
        eligibility_identity = reference_set_identity(reference_set)
        run_id, run_directory = workspace.create_evaluation_run()
        frozen_reference_path = run_directory / "reference-set.json"
        save_reference_set(frozen_reference_path, reference_set)
        plan = build_audit_plan(
            snapshot_path,
            run_directory,
            maximum_audit_cost_usd=maximum_cost,
            reference_set_path=frozen_reference_path,
            workbook_sha256=reference_set.workbook_sha256,
            snapshot_sha256=snapshot_metadata["sha256"],
            reference_set_version=reference_set.version,
            eligibility_identity=eligibility_identity,
            homepage_url=reference_set.homepage_url,
            run_id=run_id,
        )
        print(f"DRY RUN: {plan['request_count']} sequential requests planned.")
        print(_render_execution_summary(plan, run_directory, "pending"))
        print(f"Evaluation run: {run_directory.resolve()}")
        return 0
    print(
        "DRY RUN: No network requests were made and no API usage was incurred."
    )
    print(f"Private evaluation workspace: {workspace.root.resolve()}")
    return 0


def _review(arguments: argparse.Namespace) -> int:
    """Expose the private review workflow shell."""
    if arguments.eligibility_workbook:
        workspace = PrivateWorkspace.from_current_directory()
        workspace.require_initialized()
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
    match_workflow_requested = any(
        (
            arguments.run_dir,
            arguments.kind,
            arguments.reference_set,
            arguments.findings,
            arguments.matches_workbook,
            arguments.match_decisions,
            arguments.import_matches,
        )
    )
    if match_workflow_requested:
        if arguments.run_dir is None or arguments.kind is None:
            raise PrivateInputError(
                "Match review requires --run-dir and --kind "
                "(audit or programmatic)."
            )
        from vision_aid.evaluation.audit import load_audit_plan

        run_directory = arguments.run_dir.resolve()
        workspace = PrivateWorkspace.from_evaluation_run(run_directory)
        plan = load_audit_plan(run_directory)
        run_id = str(plan["run_id"])
        review_directory = workspace.root / "reviews" / run_id
        reference_path = arguments.reference_set or (
            run_directory / "reference-set.json"
        )
        findings_path = arguments.findings or (
            run_directory
            / (
                "canonical-audit-findings.json"
                if arguments.kind == "audit"
                else "canonical-programmatic.json"
            )
        )
        workbook_path = arguments.matches_workbook or (
            review_directory / f"{arguments.kind}-matches.xlsx"
        )
        decision_path = arguments.match_decisions or (
            review_directory / f"{arguments.kind}-match-decisions.json"
        )
        references = load_reference_set(reference_path).references
        findings = load_findings(findings_path)
        if arguments.import_matches:
            decisions = HumanMatchReviewer(workbook_path).review(
                references,
                findings,
            )
            save_match_decisions(decision_path, decisions)
            print(f"Validated match decisions: {decision_path.resolve()}")
        else:
            export_match_workbook(references, findings, workbook_path)
            print(f"Matches review workbook: {workbook_path.resolve()}")
        return 0
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    print(
        f"Private review workspace: {(workspace.root / 'reviews').resolve()}"
    )
    return 0


def _report(arguments: argparse.Namespace) -> int:
    """Discover verified run evidence and write every report projection."""
    from vision_aid.evaluation.audit import load_audit_plan

    run_directory = arguments.run_dir.resolve()
    workspace = PrivateWorkspace.from_evaluation_run(run_directory)
    plan = load_audit_plan(run_directory)
    run_id = str(plan["run_id"])
    review_directory = workspace.root / "reviews" / run_id
    artifacts = (
        RequiredRunArtifact(
            "frozen reference set", run_directory / "reference-set.json"
        ),
        RequiredRunArtifact(
            "audit findings", run_directory / "canonical-audit-findings.json"
        ),
        RequiredRunArtifact(
            "programmatic findings",
            run_directory / "canonical-programmatic.json",
        ),
        RequiredRunArtifact(
            "audit match decisions",
            review_directory / "audit-match-decisions.json",
            "audit",
        ),
        RequiredRunArtifact(
            "programmatic match decisions",
            review_directory / "programmatic-match-decisions.json",
            "programmatic",
        ),
        RequiredRunArtifact(
            "live manifest", run_directory / "live-manifest.json"
        ),
    )
    for artifact in artifacts:
        if artifact.path.is_file():
            continue
        if artifact.review_kind is not None:
            raise PrivateInputError(
                f"Missing {artifact.label} at {artifact.path}. Run "
                f"'visionaid-evaluate review --run-dir {run_directory} "
                f"--kind {artifact.review_kind}', complete the workbook, "
                "then rerun with "
                "--import-matches."
            )
        raise PrivateInputError(
            f"Missing {artifact.label} at {artifact.path}; complete the "
            "evaluation run before reporting."
        )
    inputs = {artifact.label: artifact.path for artifact in artifacts}
    reference_set = load_reference_set(inputs["frozen reference set"])
    live_manifest = json.loads(
        inputs["live manifest"].read_text(encoding="utf-8")
    )
    if (
        live_manifest.get("kind") != "model-evaluation-live-run"
        or live_manifest.get("run_id") != run_id
        or live_manifest.get("plan_digest") != plan.get("plan_digest")
    ):
        raise PrivateInputError(
            "The live manifest does not belong to the verified evaluation run."
        )
    score = score_evaluation(
        reference_set,
        load_findings(inputs["audit findings"]),
        load_findings(inputs["programmatic findings"]),
        load_match_decisions(inputs["audit match decisions"]),
        load_match_decisions(inputs["programmatic match decisions"]),
        load_verified_run_metadata(inputs["live manifest"], reference_set),
        parse_failures=tuple(live_manifest.get("format_failures", ())),
    )
    output_directory = arguments.output_dir or workspace.root / "reports"
    paths = write_reports(score, output_directory)
    print(f"JSON report: {paths.json.resolve()}")
    print(f"CSV report: {paths.csv.resolve()}")
    print(f"Markdown report: {paths.markdown.resolve()}")
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
