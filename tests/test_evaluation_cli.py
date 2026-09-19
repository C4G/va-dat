import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Iterator

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
SNAPSHOT_BODY = (
    b'<!doctype html>\r\n<html lang="en"><head><title>Pristine</title></head>'
    b"<body>caf\xc3\xa9</body></html>\r\n"
)
SNAPSHOT_SHA256 = "aadf66066b05d9c8d8268ba7e28ebcef8a2ed81f672fc2e2285d9236be00e89d"
TEMPORAL_ASSUMPTION = (
    "Stakeholders report that the homepage has not changed since the workbook audit."
)


class SnapshotHTTPServer(ThreadingHTTPServer):
    """Serve one synthetic HTML response and record benchmark fetches."""

    request_count = 0


class SnapshotHandler(BaseHTTPRequestHandler):
    """Return a byte-sensitive local response without external network access."""

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        server = self.server
        assert isinstance(server, SnapshotHTTPServer)
        server.request_count += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(SNAPSHOT_BODY)))
        self.send_header("ETag", '"synthetic-v1"')
        self.send_header("Last-Modified", "Wed, 16 Sep 2026 14:00:00 GMT")
        self.end_headers()
        self.wfile.write(SNAPSHOT_BODY)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of local server access logs."""


@contextmanager
def local_snapshot_server() -> Iterator[tuple[str, SnapshotHTTPServer]]:
    """Run the synthetic benchmark source on an ephemeral loopback port."""
    server = SnapshotHTTPServer(("127.0.0.1", 0), SnapshotHandler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/pristine-homepage", server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


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


def test_prepare_anchors_default_private_paths_to_the_worktree_root(
    tmp_path: Path,
) -> None:
    """Invocation from a subdirectory still uses the root-level ignore rules."""
    worktree = tmp_path / "worktree"
    (worktree / ".git").mkdir(parents=True)
    (worktree / ".gitignore").write_text(
        "/Pristine Accessibility Defect Report.xlsx\n/.model-evaluation/\n",
        encoding="utf-8",
    )
    workbook = worktree / "Pristine Accessibility Defect Report.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")
    nested_directory = worktree / "nested"
    nested_directory.mkdir()

    result = run_cli("prepare", cwd=nested_directory)

    assert result.returncode == 0, result.stderr
    assert (worktree / ".model-evaluation").is_dir()
    assert not (nested_directory / ".model-evaluation").exists()


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


def test_prepare_rejects_an_unignored_workbook_inside_the_worktree(
    tmp_path: Path,
) -> None:
    """A workbook override cannot make private data visible to version control."""
    with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
        workbook = Path(temporary_directory) / "private-input.xlsx"
        workbook.write_bytes(b"synthetic workbook placeholder")

        result = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            cwd=tmp_path,
        )

    assert result.returncode == 2
    assert "would be visible to version control" in result.stderr
    assert "outside the repository" in result.stderr


def test_prepare_captures_exact_html_with_snapshot_provenance(tmp_path: Path) -> None:
    """Prepare freezes the HTTP body consumed by the audit pipeline."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")

    with local_snapshot_server() as (source_url, server):
        result = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )

    assert result.returncode == 0, result.stderr
    assert "Benchmark snapshot captured" in result.stdout
    assert server.request_count == 1

    snapshot_directory = tmp_path / ".model-evaluation" / "snapshots"
    html_path = snapshot_directory / "pristine-homepage.html"
    metadata_path = snapshot_directory / "pristine-homepage.json"
    assert html_path.read_bytes() == SNAPSHOT_BODY

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_url"] == source_url
    assert metadata["sha256"] == SNAPSHOT_SHA256
    assert metadata["byte_length"] == len(SNAPSHOT_BODY)
    assert metadata["temporal_assumption"] == TEMPORAL_ASSUMPTION
    assert metadata["html_file"] == html_path.name
    assert metadata["http"] == {
        "content_length": str(len(SNAPSHOT_BODY)),
        "content_type": "text/html; charset=utf-8",
        "etag": '"synthetic-v1"',
        "final_url": source_url,
        "last_modified": "Wed, 16 Sep 2026 14:00:00 GMT",
        "status_code": 200,
    }
    retrieved_at = datetime.fromisoformat(
        metadata["retrieved_at"].replace("Z", "+00:00")
    )
    assert retrieved_at.tzinfo is not None


def test_prepare_reuses_a_verified_snapshot_without_refetching(tmp_path: Path) -> None:
    """An existing benchmark is verified in place and never fetched again."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")

    with local_snapshot_server() as (source_url, server):
        first = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )
        second = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            "--snapshot-url",
            source_url,
            cwd=tmp_path,
        )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Benchmark snapshot reused" in second.stdout
    assert server.request_count == 1


def test_prepare_refuses_to_overwrite_a_changed_snapshot(tmp_path: Path) -> None:
    """Checksum drift fails closed without a network request or overwrite."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")

    with local_snapshot_server() as (source_url, server):
        first = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )
        assert first.returncode == 0, first.stderr
        html_path = (
            tmp_path
            / ".model-evaluation"
            / "snapshots"
            / "pristine-homepage.html"
        )
        html_path.write_bytes(b"changed benchmark")

        second = run_cli(
            "prepare",
            "--workbook",
            str(workbook),
            "--snapshot-url",
            source_url,
            cwd=tmp_path,
        )

    assert second.returncode == 2
    assert "checksum does not match" in second.stderr
    assert "will not be refetched or overwritten" in second.stderr
    assert html_path.read_bytes() == b"changed benchmark"
    assert server.request_count == 1


def test_prepare_rejects_the_dat_vision_aid_fixture_as_a_snapshot(
    tmp_path: Path,
) -> None:
    """The unrelated committed fixture cannot stand in for Pristine."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")

    result = run_cli(
        "prepare",
        "--workbook",
        str(workbook),
        "--snapshot-url",
        str(PROJECT_ROOT / "test_files" / "dat_visionaid_home.html"),
        "--temporal-assumption",
        TEMPORAL_ASSUMPTION,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "DAT Vision Aid fixture is not a Pristine benchmark input" in result.stderr


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
