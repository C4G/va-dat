import hashlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import openpyxl
import pytest

from vision_aid.evaluation import audit as evaluation_audit
from vision_aid.evaluation.cli import main as evaluation_main
from vision_aid.evaluation.schemas import ReferenceSet
from vision_aid.evaluation.serialization import save_reference_set
from vision_aid.evaluation.workspace import PrivateWorkspace

PROJECT_ROOT = Path(__file__).parents[1]
SNAPSHOT_BODY = (
    b'<!doctype html>\r\n<html lang="en"><head><title>Pristine</title></head>'
    b"<body>caf\xc3\xa9</body></html>\r\n"
)
SNAPSHOT_SHA256 = (
    "aadf66066b05d9c8d8268ba7e28ebcef8a2ed81f672fc2e2285d9236be00e89d"
)
TEMPORAL_ASSUMPTION = (
    "Stakeholders report that the homepage has not changed since the "
    "workbook audit."
)


class SnapshotHTTPServer(ThreadingHTTPServer):
    """Serve one synthetic HTML response and record benchmark fetches."""

    request_count = 0
    request_user_agents: list[str | None]
    on_request: Callable[[], None] | None


class SnapshotHandler(BaseHTTPRequestHandler):
    """Return a byte-sensitive local response without external network access."""

    def do_GET(self) -> None:
        """Serve the synthetic homepage and record acquisition metadata."""
        server = self.server
        assert isinstance(server, SnapshotHTTPServer)
        server.request_count += 1
        server.request_user_agents.append(self.headers.get("User-Agent"))
        if server.on_request is not None:
            server.on_request()
        body = SNAPSHOT_BODY
        content_type = "text/html; charset=utf-8"
        if self.path == "/non-utf8":
            body = b"<html><body>caf\xe9</body></html>"
            content_type = "text/html; charset=iso-8859-1"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", '"synthetic-v1"')
        self.send_header("Last-Modified", "Wed, 16 Sep 2026 14:00:00 GMT")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of local server access logs."""


@contextmanager
def local_snapshot_server(
    on_request: Callable[[], None] | None = None,
) -> Iterator[tuple[str, SnapshotHTTPServer]]:
    """Run the synthetic benchmark source on an ephemeral loopback port."""
    server = SnapshotHTTPServer(("127.0.0.1", 0), SnapshotHandler)
    server.request_user_agents = []
    server.on_request = on_request
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


class TerminalInput(io.StringIO):
    """Provide controlled input with an explicit terminal capability."""

    def __init__(self, value: str, *, terminal: bool = True) -> None:
        super().__init__(value)
        self.terminal = terminal

    def isatty(self) -> bool:
        """Report whether interactive confirmation is available."""
        return self.terminal


def create_planned_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Plan a minimal evaluation run through the public CLI boundary."""
    monkeypatch.chdir(tmp_path)
    workspace = PrivateWorkspace.from_current_directory()
    workspace.initialize()
    references = ReferenceSet(
        version="synthetic-v1",
        workbook_filename="synthetic.xlsx",
        workbook_sha256="a" * 64,
        homepage_url="https://example.test/",
        references=(),
    )
    save_reference_set(workspace.root / "references" / "approved.json", references)
    snapshot_directory = workspace.root / "snapshots" / "pristine-homepage"
    snapshot_directory.mkdir(parents=True)
    snapshot = snapshot_directory / "source.html"
    snapshot.write_text("<html><body>synthetic</body></html>", encoding="utf-8")
    (snapshot_directory / "metadata.json").write_text(
        json.dumps({"sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )
    assert evaluation_main(["audit", "--max-audit-cost-usd", "0.01"]) == 0
    capsys.readouterr()
    return next((workspace.root / "runs").iterdir())


@pytest.fixture
def synthetic_workbook(tmp_path: Path) -> Path:
    """Create the minimal authorized workbook placeholder used by CLI tests."""
    workbook = tmp_path / "synthetic-reference.xlsx"
    workbook.write_bytes(b"synthetic workbook placeholder")
    return workbook


def test_help_exposes_the_evaluation_workflows() -> None:
    """The CLI makes every evaluation lifecycle workflow discoverable."""
    result = run_cli("--help")

    assert result.returncode == 0
    for workflow in ("prepare", "audit", "review", "report"):
        assert workflow in result.stdout


def test_prepare_initializes_one_partitioned_private_workspace(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """Prepare creates all private artifact partitions around a local workbook."""
    workspace = tmp_path / ".model-evaluation"

    result = run_cli(
        "prepare",
        "--workbook",
        str(synthetic_workbook),
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Private evaluation workspace initialized" in result.stdout
    assert str(synthetic_workbook.resolve()) in result.stdout
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


def test_prepare_captures_exact_html_with_snapshot_provenance(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """Prepare freezes the HTTP body consumed by the audit pipeline."""
    with local_snapshot_server() as (source_url, server):
        result = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )

    assert result.returncode == 0, result.stderr
    assert "Benchmark snapshot captured" in result.stdout
    assert server.request_count == 1
    assert server.request_user_agents == ["Mozilla/5.0"]

    snapshot_directory = (
        tmp_path / ".model-evaluation" / "snapshots" / "pristine-homepage"
    )
    html_path = snapshot_directory / "source.html"
    metadata_path = snapshot_directory / "metadata.json"
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
        "request_user_agent": "Mozilla/5.0",
        "status_code": 200,
    }
    retrieved_at = datetime.fromisoformat(metadata["retrieved_at"])
    assert retrieved_at.tzinfo is not None


def test_prepare_reuses_a_verified_snapshot_without_refetching(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """An existing benchmark is verified in place and never fetched again."""
    with local_snapshot_server() as (source_url, server):
        first = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )
        second = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url,
            cwd=tmp_path,
        )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Benchmark snapshot reused" in second.stdout
    assert server.request_count == 1


def test_prepare_rejects_html_the_audit_pipeline_cannot_decode(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """A snapshot must satisfy the pipeline's UTF-8 file contract."""
    with local_snapshot_server() as (source_url, _server):
        result = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url.replace("/pristine-homepage", "/non-utf8"),
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )

    assert result.returncode == 2
    assert "not valid UTF-8" in result.stderr
    snapshot_directory = tmp_path / ".model-evaluation" / "snapshots"
    assert list(snapshot_directory.iterdir()) == []


def test_prepare_refuses_to_overwrite_a_changed_snapshot(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """Checksum drift fails closed without a network request or overwrite."""
    with local_snapshot_server() as (source_url, server):
        first = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
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
            / "pristine-homepage"
            / "source.html"
        )
        html_path.write_bytes(b"changed benchmark")

        second = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url,
            cwd=tmp_path,
        )

    assert second.returncode == 2
    assert "checksum does not match" in second.stderr
    assert "will not be refetched or overwritten" in second.stderr
    assert html_path.read_bytes() == b"changed benchmark"
    assert server.request_count == 1


def test_prepare_publishes_the_snapshot_as_one_immutable_bundle(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """A competing snapshot cannot be mixed with a capture in progress."""
    snapshot_directory = (
        tmp_path / ".model-evaluation" / "snapshots" / "pristine-homepage"
    )

    def publish_competing_snapshot() -> None:
        """Simulate another prepare process winning the publication race."""
        snapshot_directory.mkdir()
        (snapshot_directory / "race-marker").write_text(
            "winner",
            encoding="utf-8",
        )

    with local_snapshot_server(publish_competing_snapshot) as (
        source_url,
        _server,
    ):
        result = run_cli(
            "prepare",
            "--workbook",
            str(synthetic_workbook),
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )

    assert result.returncode == 2
    assert "appeared during capture" in result.stderr
    assert [path.name for path in snapshot_directory.iterdir()] == [
        "race-marker"
    ]


def test_prepare_rejects_the_dat_vision_aid_fixture_as_a_snapshot(
    tmp_path: Path,
    synthetic_workbook: Path,
) -> None:
    """The unrelated committed fixture cannot stand in for Pristine."""
    result = run_cli(
        "prepare",
        "--workbook",
        str(synthetic_workbook),
        "--snapshot-url",
        str(PROJECT_ROOT / "test_files" / "dat_visionaid_home.html"),
        "--temporal-assumption",
        TEMPORAL_ASSUMPTION,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert (
        "DAT Vision Aid fixture is not a Pristine benchmark input"
        in result.stderr
    )


@pytest.mark.parametrize(
    "api_key_name", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
)
def test_audit_defaults_to_a_network_free_dry_run_even_with_an_api_key(
    tmp_path: Path,
    synthetic_workbook: Path,
    api_key_name: str,
) -> None:
    """Environment credentials alone can never make evaluation billable."""
    prepared = run_cli(
        "prepare",
        "--workbook",
        str(synthetic_workbook),
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


@pytest.mark.parametrize("option", ("--plan", "--authorize", "--bundle"))
def test_obsolete_workflow_options_are_rejected(option: str) -> None:
    """Removed plan, authorization, and report-bundle flags stay removed."""
    workflow = "report" if option == "--bundle" else "audit"
    prefix = ("--run-dir", "obsolete-run") if workflow == "report" else ()
    result = run_cli(workflow, *prefix, option, "obsolete.json")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_interactive_live_approval_accepts_trimmed_case_insensitive_yes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A terminal operator can approve the displayed run by typing yes."""
    run_directory = create_planned_run(tmp_path, monkeypatch, capsys)

    class SyntheticClient:
        """Return empty successful findings without provider access."""

        def __init__(self, **_kwargs: object) -> None:
            pass

        def call(self, _prompt: str) -> dict[str, object]:
            return {
                "success": True,
                "response": "[]",
                "usage": {},
                "duration_seconds": 0,
            }

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(sys, "stdin", TerminalInput("  YeS  \n"))
    monkeypatch.setattr(evaluation_audit, "AuditRequestClient", SyntheticClient)

    assert (
        evaluation_main(
            ["audit", "--live", "--run-dir", str(run_directory)]
        )
        == 0
    )

    output = capsys.readouterr().out
    manifest = json.loads(
        (run_directory / "live-manifest.json").read_text(encoding="utf-8")
    )
    assert "Evaluation execution summary" in output
    assert "Approval mode: interactive" in output
    assert manifest["approval"]["mode"] == "interactive"


@pytest.mark.parametrize(
    ("response", "terminal", "message"),
    (
        ("no\n", True, "was not 'yes'"),
        ("\n", True, "was not 'yes'"),
        ("", True, "ended before confirmation"),
        ("yes\n", False, "requires a terminal"),
    ),
)
def test_failed_live_approval_stops_before_client_or_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    response: str,
    terminal: bool,
    message: str,
) -> None:
    """Ambiguous, missing, or non-terminal input cannot begin a live run."""
    run_directory = create_planned_run(tmp_path, monkeypatch, capsys)

    class ForbiddenClient:
        """Fail if approval rejection constructs a provider client."""

        def __init__(self, **_kwargs: object) -> None:
            raise AssertionError("provider client was constructed")

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        sys,
        "stdin",
        TerminalInput(response, terminal=terminal),
    )
    monkeypatch.setattr(evaluation_audit, "AuditRequestClient", ForbiddenClient)

    with pytest.raises(SystemExit) as raised:
        evaluation_main(
            ["audit", "--live", "--run-dir", str(run_directory)]
        )

    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert "Evaluation execution summary" in captured.out
    assert message in captured.err
    for name in (
        "raw-attempts.json",
        "canonical-audit-findings.json",
        "live-manifest.json",
    ):
        assert not (run_directory / name).exists()


def test_live_option_combinations_keep_every_spending_gate_mandatory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Automation cannot blur planning, live intent, credentials, or cost."""
    run_directory = create_planned_run(tmp_path, monkeypatch, capsys)

    with pytest.raises(SystemExit):
        evaluation_main(["audit", "--auto-approve"])
    assert "only with --live" in capsys.readouterr().err

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    with pytest.raises(SystemExit):
        evaluation_main(
            [
                "audit",
                "--live",
                "--run-dir",
                str(run_directory),
                "--auto-approve",
                "--max-audit-cost-usd",
                "1",
            ]
        )
    assert "reuses the saved cost guardrail" in capsys.readouterr().err

    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(SystemExit):
        evaluation_main(
            [
                "audit",
                "--live",
                "--run-dir",
                str(run_directory),
                "--auto-approve",
            ]
        )
    assert "requires OPENAI_API_KEY" in capsys.readouterr().err
    assert not (run_directory / "live-manifest.json").exists()


def test_cli_completes_the_synthetic_private_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prepare, review, audit, and report compose without provider access."""
    workbook_path = tmp_path / "synthetic.xlsx"
    workbook = openpyxl.Workbook()
    source = workbook.active
    source.title = "Defects"
    source.append(["Page", "URL", "Problem", "Location", "WCAG"])
    source.append(
        [
            "Home",
            "https://example.test/",
            "Hero alternative text is misleading",
            "Hero image",
            "1.1.1",
        ]
    )
    workbook.save(workbook_path)
    workbook_sha256 = hashlib.sha256(workbook_path.read_bytes()).hexdigest()

    with local_snapshot_server() as (source_url, _server):
        prepared = run_cli(
            "prepare",
            "--workbook",
            str(workbook_path),
            "--workbook-sha256",
            workbook_sha256,
            "--homepage-url",
            "https://example.test/",
            "--snapshot-url",
            source_url,
            "--temporal-assumption",
            TEMPORAL_ASSUMPTION,
            cwd=tmp_path,
        )
    assert prepared.returncode == 0, prepared.stderr

    workspace = tmp_path / ".model-evaluation"
    eligibility_path = workspace / "reviews" / "eligibility.xlsx"
    review = openpyxl.load_workbook(eligibility_path)
    eligibility = review["Eligibility"]
    columns = {cell.value: cell.column for cell in eligibility[1]}
    for name, value in {
        "classification": "llm_eligible",
        "decision": "accepted",
        "rationale": "The model receives the image context.",
        "reviewer": "reviewer@example.test",
        "confidence": 0.9,
        "timestamp": "2026-09-19T12:00:00Z",
    }.items():
        eligibility.cell(2, columns[name], value)
    review.save(eligibility_path)

    reviewed = run_cli(
        "review",
        "--eligibility-workbook",
        str(eligibility_path),
        cwd=tmp_path,
    )
    assert reviewed.returncode == 0, reviewed.stderr

    planned = run_cli(
        "audit",
        "--max-audit-cost-usd",
        "0.01",
        cwd=tmp_path,
    )
    assert planned.returncode == 0, planned.stderr
    assert "DRY RUN" in planned.stdout
    assert "Evaluation execution summary" in planned.stdout
    assert "Maximum audit cost: $0.01" in planned.stdout
    assert "Evaluation run:" in planned.stdout

    approved_path = workspace / "references" / "approved.json"
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    run_directories = list((workspace / "runs").iterdir())
    assert len(run_directories) == 1
    run_directory = run_directories[0]
    plan_path = run_directory / "evaluation-manifest.json"
    run_manifest = json.loads(plan_path.read_text(encoding="utf-8"))
    assert run_directory.name == run_manifest["run_id"]
    assert run_manifest["maximum_audit_cost_usd"] == "0.01"
    frozen_reference = run_directory / "reference-set.json"
    assert frozen_reference.read_bytes() == approved_path.read_bytes()
    first_plan_bytes = plan_path.read_bytes()
    repeated_plan = run_cli(
        "audit",
        "--max-audit-cost-usd",
        "0.01",
        cwd=tmp_path,
    )
    assert repeated_plan.returncode == 0, repeated_plan.stderr
    repeated_directories = list((workspace / "runs").iterdir())
    assert len(repeated_directories) == 2
    assert len({path.name for path in repeated_directories}) == 2
    assert plan_path.read_bytes() == first_plan_bytes

    class SyntheticClient:
        """Return deterministic successful responses without network access."""

        def __init__(self, **_kwargs: object) -> None:
            pass

        def call(self, _prompt: str) -> dict[str, object]:
            return {
                "success": True,
                "response": json.dumps(
                    {
                        "problem": "Hero alternative text is misleading",
                        "element": "img",
                        "location": "Hero image",
                        "wcag": "1.1.1",
                    }
                ),
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "duration_seconds": 0.01,
                "stop_reason": "stop",
            }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(evaluation_audit, "AuditRequestClient", SyntheticClient)
    assert (
        evaluation_main(
            [
                "audit",
                "--live",
                "--run-dir",
                str(run_directory),
                "--auto-approve",
            ]
        )
        == 0
    )
    live_output = capsys.readouterr().out
    for expected in (
        "Model: gpt-5.6-luna",
        "Endpoint: chat.completions",
        "Reasoning effort: medium",
        "Benchmark snapshot SHA-256:",
        "Reference set:",
        "Prompts (",
        "Estimated input tokens:",
        "Retry policy:",
        "Maximum audit cost: $0.01",
        f"Destination: {run_directory}",
        "Approval mode: auto",
    ):
        assert expected in live_output
    live_manifest = json.loads(
        (run_directory / "live-manifest.json").read_text(encoding="utf-8")
    )
    assert live_manifest["approval"]["mode"] == "auto"
    assert "approved_at" in live_manifest["approval"]
    assert "authorization_digest" not in live_manifest
    assert "authorized_plan_digest" not in live_manifest
    live_artifacts = {
        name: (run_directory / name).read_bytes()
        for name in (
            "raw-attempts.json",
            "canonical-audit-findings.json",
            "live-manifest.json",
        )
    }
    with pytest.raises(SystemExit) as occupied:
        evaluation_main(
            [
                "audit",
                "--live",
                "--run-dir",
                str(run_directory),
                "--auto-approve",
            ]
        )
    assert occupied.value.code == 2
    assert "fresh evaluation run" in capsys.readouterr().err
    for name, original_bytes in live_artifacts.items():
        assert (run_directory / name).read_bytes() == original_bytes

    finding_path = run_directory / "canonical-audit-findings.json"
    review_directory = workspace / "reviews" / run_manifest["run_id"]
    matches_workbook = review_directory / "audit-matches.xlsx"
    generated = run_cli(
        "review",
        "--run-dir",
        str(run_directory),
        "--kind",
        "audit",
        cwd=tmp_path,
    )
    assert generated.returncode == 0, generated.stderr
    match_review = openpyxl.load_workbook(matches_workbook)
    matches = match_review["Matches"]
    match_columns = {cell.value: cell.column for cell in matches[1]}
    for row in range(2, matches.max_row + 1):
        values = {
            "decision": "accepted" if row == 2 else "rejected",
            "page_compatible": True,
            "failure_compatible": True,
            "location_compatible": True,
            "rationale": "Same reviewed homepage evidence.",
            "reviewer": "reviewer@example.test",
            "confidence": 0.9,
            "timestamp": "2026-09-19T12:30:00Z",
        }
        for name, value in values.items():
            matches.cell(row, match_columns[name], value)
    match_review.save(matches_workbook)
    imported = run_cli(
        "review",
        "--run-dir",
        str(run_directory),
        "--kind",
        "audit",
        "--import-matches",
        cwd=tmp_path,
    )
    assert imported.returncode == 0, imported.stderr
    programmatic_generated = run_cli(
        "review",
        "--run-dir",
        str(run_directory),
        "--kind",
        "programmatic",
        cwd=tmp_path,
    )
    assert programmatic_generated.returncode == 0, programmatic_generated.stderr
    programmatic_workbook = review_directory / "programmatic-matches.xlsx"
    programmatic_review = openpyxl.load_workbook(programmatic_workbook)
    programmatic_matches = programmatic_review["Matches"]
    programmatic_columns = {
        cell.value: cell.column for cell in programmatic_matches[1]
    }
    for row in range(2, programmatic_matches.max_row + 1):
        for name, value in {
            "decision": "rejected",
            "rationale": "The deterministic finding is not the same defect.",
            "reviewer": "reviewer@example.test",
            "confidence": 0.9,
            "timestamp": "2026-09-19T12:35:00Z",
        }.items():
            programmatic_matches.cell(row, programmatic_columns[name], value)
    programmatic_review.save(programmatic_workbook)
    programmatic_imported = run_cli(
        "review",
        "--run-dir",
        str(run_directory),
        "--kind",
        "programmatic",
        "--import-matches",
        cwd=tmp_path,
    )
    assert programmatic_imported.returncode == 0, programmatic_imported.stderr
    assert (review_directory / "audit-match-decisions.json").is_file()
    assert (
        review_directory / "programmatic-match-decisions.json"
    ).is_file()
    live_manifest["format_failures"] = ["synthetic-format"]
    (run_directory / "live-manifest.json").write_text(
        json.dumps(live_manifest),
        encoding="utf-8",
    )

    reported = run_cli(
        "report", "--run-dir", str(run_directory), cwd=tmp_path
    )

    assert reported.returncode == 0, reported.stderr
    json_report = workspace / "reports" / f"{run_manifest['run_id']}.json"
    assert json_report.is_file()
    report_data = json.loads(json_report.read_text(encoding="utf-8"))
    assert report_data["parse_failures"] == ["synthetic-format"]

    programmatic_decisions = (
        review_directory / "programmatic-match-decisions.json"
    )
    decision_bytes = programmatic_decisions.read_bytes()
    programmatic_decisions.unlink()
    unresolved = run_cli(
        "report", "--run-dir", str(run_directory), cwd=tmp_path
    )
    assert unresolved.returncode == 2
    assert "--kind programmatic" in unresolved.stderr
    assert "--import-matches" in unresolved.stderr
    programmatic_decisions.write_bytes(decision_bytes)

    findings = json.loads(finding_path.read_text(encoding="utf-8"))
    findings[0]["run_id"] = "different-run"
    finding_path.write_text(json.dumps(findings), encoding="utf-8")
    rejected_finding = run_cli(
        "report", "--run-dir", str(run_directory), cwd=tmp_path
    )
    assert rejected_finding.returncode == 2
    assert "do not belong to the verified run" in rejected_finding.stderr

    findings[0]["run_id"] = run_manifest["run_id"]
    finding_path.write_text(json.dumps(findings), encoding="utf-8")
    approved["references"][0]["eligibility_review"]["rationale"] = "Changed"
    frozen_reference.write_text(json.dumps(approved), encoding="utf-8")
    rejected_eligibility = run_cli(
        "report", "--run-dir", str(run_directory), cwd=tmp_path
    )
    assert rejected_eligibility.returncode == 2
    assert "reference-set" in rejected_eligibility.stderr
