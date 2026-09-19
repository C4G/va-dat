import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


def run_cli(
    *arguments: str,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the installed evaluation module through its public CLI boundary."""
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "vision_aid.evaluation.cli", *arguments],
        cwd=cwd,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_exposes_the_evaluation_workflows() -> None:
    """The CLI makes every evaluation lifecycle workflow discoverable."""
    result = run_cli("--help")

    assert result.returncode == 0
    for workflow in ("prepare", "audit", "review", "report"):
        assert workflow in result.stdout


def test_prepare_initializes_one_partitioned_private_workspace(tmp_path: Path) -> None:
    """Prepare creates all private artifact partitions around a local workbook."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")
    workspace = tmp_path / ".model-evaluation"

    result = run_cli(
        "prepare",
        "--workbook",
        str(workbook),
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Private evaluation workspace initialized" in result.stdout
    assert str(workbook.resolve()) in result.stdout
    assert sorted(path.name for path in workspace.iterdir()) == [
        "references",
        "reports",
        "reviews",
        "runs",
        "snapshots",
    ]


def test_prepare_explains_how_to_supply_a_missing_private_workbook(
    tmp_path: Path,
) -> None:
    """A missing workbook fails with authorized, local recovery instructions."""
    missing_workbook = tmp_path / "missing.xlsx"
    workspace = tmp_path / ".model-evaluation"

    result = run_cli(
        "prepare",
        "--workbook",
        str(missing_workbook),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "Private source workbook not found" in result.stderr
    assert "authorized project source" in result.stderr
    assert "--workbook PATH" in result.stderr
    assert not workspace.exists()


def test_prepare_rejects_an_unignored_workbook_inside_the_worktree() -> None:
    """A workbook override cannot make private data visible to version control."""
    with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
        workbook = Path(temporary_directory) / "private-input.xlsx"
        workbook.write_bytes(b"synthetic workbook placeholder")

        result = run_cli("prepare", "--workbook", str(workbook))

    assert result.returncode == 2
    assert "would be visible to version control" in result.stderr
    assert "outside the repository" in result.stderr


@pytest.mark.parametrize("api_key_name", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
def test_audit_defaults_to_a_network_free_dry_run_even_with_an_api_key(
    tmp_path: Path, api_key_name: str
) -> None:
    """Environment credentials alone can never make evaluation billable."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")
    prepared = run_cli(
        "prepare",
        "--workbook",
        str(workbook),
        cwd=tmp_path,
    )
    assert prepared.returncode == 0, prepared.stderr

    network_guard = tmp_path / "network_guard"
    network_guard.mkdir()
    (network_guard / "sitecustomize.py").write_text(
        "import socket\n"
        "def blocked_socket(*args, **kwargs):\n"
        "    raise AssertionError('evaluation CLI attempted network access')\n"
        "socket.socket = blocked_socket\n",
        encoding="utf-8",
    )

    result = run_cli(
        "audit",
        cwd=tmp_path,
        env={
            api_key_name: "must-not-be-used",
            "PYTHONPATH": str(network_guard),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "No network requests were made" in result.stdout
