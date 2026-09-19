"""Command-line shell for the private model-evaluation lifecycle."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

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
            f"authorized local source workbook (default: ./{DEFAULT_WORKBOOK_FILENAME})"
        ),
    )
    prepare.set_defaults(handler=_prepare)

    audit = workflows.add_parser(
        "audit",
        help="inspect the prepared audit plan in network-free dry-run mode",
    )
    audit.set_defaults(handler=_audit)

    review = workflows.add_parser(
        "review",
        help="work with private eligibility and match review artifacts",
    )
    review.set_defaults(handler=_review)

    report = workflows.add_parser(
        "report",
        help="generate private evaluation reports",
    )
    report.set_defaults(handler=_report)
    return parser


def _prepare(arguments: argparse.Namespace) -> int:
    """Validate the private workbook before creating the workspace layout."""
    workbook = require_private_workbook(arguments.workbook)
    workspace = PrivateWorkspace.from_current_directory()
    workspace.initialize()
    print(f"Private evaluation workspace initialized at {workspace.root.resolve()}")
    print(f"Private source workbook: {workbook}")
    return 0


def _audit(arguments: argparse.Namespace) -> int:
    """Expose the safe audit shell without enabling live execution yet."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    print("DRY RUN: No network requests were made and no API usage was incurred.")
    print(f"Private evaluation workspace: {workspace.root.resolve()}")
    return 0


def _review(arguments: argparse.Namespace) -> int:
    """Expose the private review workflow shell."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    print(f"Private review workspace: {(workspace.root / 'reviews').resolve()}")
    return 0


def _report(arguments: argparse.Namespace) -> int:
    """Expose the private report workflow shell."""
    workspace = PrivateWorkspace.from_current_directory()
    workspace.require_initialized()
    print(f"Private report workspace: {(workspace.root / 'reports').resolve()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested evaluation workflow and render actionable errors."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    handler: CommandHandler = arguments.handler
    try:
        return handler(arguments)
    except PrivateInputError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
