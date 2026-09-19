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


def require_private_workbook(path: Path) -> Path:
    """Resolve a local workbook or explain how an authorized user supplies it."""
    if not path.is_file():
        raise PrivateInputError(
            f"Private source workbook not found at {path.resolve()}. Obtain "
            f"'{DEFAULT_WORKBOOK_FILENAME}' from an authorized project source "
            "and place it at the repository root, or pass --workbook PATH. "
            "The evaluation CLI will not download or substitute private inputs."
        )
    return path.resolve()
