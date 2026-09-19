"""Private filesystem conventions for model evaluation artifacts."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_WORKBOOK_FILENAME = "Pristine Accessibility Defect Report.xlsx"
DEFAULT_WORKSPACE = Path(".model-evaluation")
WORKSPACE_PARTITIONS = (
    "references",
    "reviews",
    "snapshots",
    "runs",
    "reports",
)


class PrivateInputError(ValueError):
    """Report a missing local input without attempting to replace it."""


@dataclass(frozen=True)
class PrivateWorkspace:
    """Paths reserved for private evaluation inputs and derived artifacts."""

    root: Path

    @classmethod
    def from_current_directory(cls) -> "PrivateWorkspace":
        """Anchor artifacts at the worktree root or the non-versioned CWD."""
        current_directory = Path.cwd().resolve()
        worktree = find_worktree_root(current_directory)
        return cls((worktree or current_directory) / DEFAULT_WORKSPACE)

    @property
    def partitions(self) -> tuple[Path, ...]:
        """Return every required private artifact partition."""
        return tuple(self.root / name for name in WORKSPACE_PARTITIONS)

    def initialize(self) -> None:
        """Create the private workspace and all of its artifact partitions."""
        for partition in self.partitions:
            partition.mkdir(parents=True, exist_ok=True)

    def require_initialized(self) -> None:
        """Fail with recovery instructions unless every partition exists."""
        missing = [path.name for path in self.partitions if not path.is_dir()]
        if missing:
            raise PrivateInputError(
                f"Private evaluation workspace is not initialized at "
                f"{self.root.resolve()}. Run 'visionaid-evaluate prepare' "
                "with an authorized local workbook first."
            )


def find_worktree_root(start: Path) -> Path | None:
    """Find the containing Git worktree without invoking Git."""
    resolved_start = start.resolve()
    for directory in (resolved_start, *resolved_start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def require_private_workbook(path: Path) -> Path:
    """Resolve a local workbook or explain how an authorized user supplies it."""
    candidate = path
    current_worktree = find_worktree_root(Path.cwd())
    if path == Path(DEFAULT_WORKBOOK_FILENAME) and current_worktree is not None:
        candidate = current_worktree / path

    if not candidate.is_file():
        raise PrivateInputError(
            f"Private source workbook not found at {candidate.resolve()}. Obtain "
            f"'{DEFAULT_WORKBOOK_FILENAME}' from an authorized project source "
            "and place it at the repository root, or pass --workbook PATH. "
            "The evaluation CLI will not download or substitute private inputs."
        )
    workbook = candidate.resolve()
    worktree = find_worktree_root(workbook.parent)
    if worktree is None or not workbook.is_relative_to(worktree):
        return workbook

    default_workbook = (worktree / DEFAULT_WORKBOOK_FILENAME).resolve()
    private_workspace = (worktree / DEFAULT_WORKSPACE).resolve()
    if workbook != default_workbook and not workbook.is_relative_to(private_workspace):
        raise PrivateInputError(
            f"Private source workbook at {workbook} would be visible to "
            "version control. Keep the exact default filename at the repository "
            "root, store the override inside .model-evaluation, or pass a path "
            "outside the repository."
        )
    return workbook
