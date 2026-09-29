"""Run, review, and report through the CLI and its saved artifacts."""

import csv
import hashlib
import json
from pathlib import Path

import openpyxl
import pytest

from vision_aid.evaluation import llm_audit
from vision_aid.evaluation.cli import main


def inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Build a small Human audit with the exact supported source columns."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Defect report"
    sheet.append(
        [
            "Sr. #",
            "element name",
            "Browser Combination",
            "Page name",
            "Issue Title",
            "Steps to Reproduce",
            "actual result",
            "expected result",
            "Recommendation for Fix",
            "WCAG Sc",
            "Type of Change",
            "comment",
        ]
    )
    sheet.append(
        [
            1,
            "First link",
            "Chrome",
            "Home",
            "Unclear link",
            "Open page",
            "Vague link\nfor everyone",
            "Descriptive text",
            "Rename",
            "2.4.4",
            "Code",
            "",
        ]
    )
    sheet.append(
        [
            2,
            "Second link",
            "Chrome",
            "Global",
            "Missing destination",
            "Open page",
            "No href",
            "Working link",
            "Add href",
            "2.4.4",
            "Code",
            "",
        ]
    )
    sheet.append(
        [
            3,
            "Photo",
            "Chrome",
            "Home",
            "No alt text",
            "Open page",
            "Image lacks alt",
            "Alt text",
            "Add alt",
            "1.1.1",
            "Code",
            "",
        ]
    )
    sheet.append([4, "Other", "Chrome", "Careers", "Outside scope"])
    human_audit = tmp_path / "human-audit.xlsx"
    book.save(human_audit)
    html = tmp_path / "home.html"
    html.write_text(
        '<html lang="en"><head><title>Home</title></head><body>'
        '<h1>Home</h1><a href="/">Click here</a><img src="x.png"></body></html>'
    )
    return human_audit, html


def args(human_audit: Path, html: Path, *extra: str) -> list[str]:
    """Assemble the public run command for the synthetic inputs."""
    return [
        "run",
        "--human-audit",
        str(human_audit),
        "--html",
        str(html),
        "--source-url",
        "https://example.test/",
        "--max-cost-usd",
        "0.01",
        *extra,
    ]


def directory(tmp_path: Path) -> Path:
    """Find the single run created under a temporary workspace."""
    return next((tmp_path / ".model-evaluation" / "runs").iterdir())


def read_review(path: Path) -> list[dict[str, str]]:
    """Read reviewer decisions using standard CSV quoting."""
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_review(path: Path, rows: list[dict[str, str]]) -> None:
    """Save edited reviewer decisions using standard CSV quoting."""
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_preview_preserves_human_findings_and_never_calls_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Credentials alone never buy requests, and all source rows survive."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "available")
    monkeypatch.setattr(
        llm_audit, "LLMRequestClient", lambda **_: pytest.fail("paid call")
    )
    assert main(args(human_audit, html)) == 0
    output = capsys.readouterr().out
    run = directory(tmp_path)
    assert "claude-haiku-4-5-20251001" in output
    assert "16000" in output and "24192" in output and "$0.01" in output
    assert (run / "snapshot.html").read_bytes() == html.read_bytes()
    raw = json.loads((run / "raw-programmatic-findings.json").read_text())
    normalized = json.loads((run / "normalized-programmatic-findings.json").read_text())
    assert raw and [finding["raw_source"] for finding in normalized] == raw
    assert not (run / "programmatic_findings.json").exists()
    assert not (run / "programmatic-findings.json").exists()
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["snapshot_sha256"] == hashlib.sha256(html.read_bytes()).hexdigest()
    assert manifest["human_audit_filename"] == human_audit.name
    assert manifest["human_audit_sha256"] == hashlib.sha256(human_audit.read_bytes()).hexdigest()
    imported = json.loads((run / "human-findings.json").read_text())
    assert imported["human_audit_sha256"] == manifest["human_audit_sha256"]
    assert all(item["human_finding_id"].startswith("human-") for item in imported["human_findings"])
    rows = read_review(run / "review.csv")
    assert [row["source_row"] for row in rows] == ["2", "3", "4"]
    assert rows[0]["source_element"] == "First link"
    assert rows[0]["actual result"] == "Vague link\nfor everyone"
    assert all(not row["classification"] for row in rows)
    assert {"human_finding_id", "llm_finding_id"} <= rows[0].keys()
    assert not {"reference_id", "audit_finding_id"} & rows[0].keys()
    with pytest.raises(SystemExit) as help_exit:
        main(["run", "--help"])
    assert help_exit.value.code == 0
    assert "Human audit" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main([*args(human_audit, html), "--workbook", str(human_audit)])
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])


def test_subdirectory_invocation_uses_ignored_worktree_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run from a repository subdirectory stays under the root ignore rule."""
    human_audit, html = inputs(tmp_path)
    (tmp_path / ".git").mkdir()
    child = tmp_path / "entry_points"
    child.mkdir()
    monkeypatch.chdir(child)
    assert main(args(human_audit, html)) == 0
    assert (tmp_path / ".model-evaluation" / "runs").is_dir()
    assert not (child / ".model-evaluation").exists()


def test_live_csv_review_and_report_full_row_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One fake live run yields hand-calculated metrics and source evidence."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        calls = 0

        def call(self, prompt: str) -> dict:
            """Return a successful fake provider response with usage."""
            self.calls += 1
            return {
                "success": True,
                "response": json.dumps(
                    [{"problem": "Unclear link", "location": "First link"}]
                ),
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cached_input_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "reasoning_tokens": None,
                },
            }

    fake = FakeClient()
    client_options: list[dict] = []

    def client(**options: object) -> FakeClient:
        """Record the evaluator's request-client configuration."""
        client_options.append(options)
        return fake

    monkeypatch.setattr(llm_audit, "LLMRequestClient", client)
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    assert client_options[0]["max_retries"] == 0
    run = directory(tmp_path)
    assert fake.calls == 3
    assert (
        json.loads((run / "run.json").read_text())["estimated_cost_usd"] == "0.0006525"
    )
    assert (run / "raw-llm-responses.json").exists()
    assert all(not (run / name).exists() for name in (
        "references.json", "raw-audit-responses.json", "normalized-audit-findings.json"
    ))
    findings = json.loads((run / "normalized-llm-findings.json").read_text())
    programmatic_file = run / "normalized-programmatic-findings.json"
    programmatic = json.loads(programmatic_file.read_text())
    assert findings and programmatic
    assert all(item["source"] == "llm" and item["finding_id"].startswith("llm-") for item in findings)
    assert all(item["finding_id"].startswith("programmatic-") for item in programmatic)
    review = run / "review.csv"
    rows = read_review(review)
    rows[0].update(
        classification="llm_eligible",
        classification_reason="Model can see link",
        llm_finding_id=findings[0]["finding_id"],
        match_reason="Full issue",
    )
    rows[1].update(
        classification="programmatic",
        classification_reason="HTML check",
        programmatic_finding_id=programmatic[0]["finding_id"],
        match_reason="Full issue",
    )
    rows[2].update(
        classification="unavailable_evidence", classification_reason="Visual context"
    )
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run)]) == 0
    report = (run / "report.md").read_text()
    assert "LLM detection rate: 1/1" in report
    assert "Programmatic detection rate: 1/1" in report
    assert "Overall detection rate: 2/3" in report
    assert "Vague link" in report and "First link" in report
    for row in rows:
        row["audit_finding_id"] = row.pop("llm_finding_id")
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    imported = json.loads((run / "human-findings.json").read_text())
    imported["human_audit_sha256"] = "changed"
    (run / "human-findings.json").write_text(json.dumps(imported))
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])


def test_report_shows_evidence_verbatim_and_escapes_inline_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fenced evidence stays verbatim and inline fields escape raw HTML."""
    human_audit, html = inputs(tmp_path)
    book = openpyxl.load_workbook(human_audit)
    actual = 'Use <main> tag.\nSay "Main" ```here```'
    book.active["G2"] = actual
    book.save(human_audit)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        def call(self, prompt: str) -> dict:
            """Return one normalized finding for applicable prompts."""
            return {
                "success": True,
                "response": json.dumps([{"problem": "Vague link"}]),
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: FakeClient())
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    run = directory(tmp_path)
    review = run / "review.csv"
    rows = read_review(review)
    for row in rows:
        row.update(classification="ambiguous", classification_reason="Unclear")
    rows[0]["classification_reason"] = 'An <img alt=""> needs judgment'
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run)]) == 0
    report = (run / "report.md").read_text()
    evidence = (
        "<details><summary>Original defect evidence</summary>\n\n"
        "````json\n"
        "{\n"
        '  "Browser Combination": "Chrome",\n'
        '  "Issue Title": "Unclear link",\n'
        '  "Page name": "Home",\n'
        '  "Recommendation for Fix": "Rename",\n'
        '  "Sr. #": "1",\n'
        '  "Steps to Reproduce": "Open page",\n'
        '  "Type of Change": "Code",\n'
        '  "WCAG Sc": "2.4.4",\n'
        '  "actual result": "Use <main> tag.\\nSay \\"Main\\" ```here```",\n'
        '  "comment": "",\n'
        '  "element name": "First link",\n'
        '  "expected result": "Descriptive text"\n'
        "}\n"
        "````\n\n"
        "</details>\n"
    )
    assert evidence in report
    assert "Original defect evidence:" not in report
    assert 'An \\<img alt=""\\> needs judgment' in report


def test_review_requires_classification_and_rejects_invalid_finding_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Review validation blocks missing decisions, wrong kinds, and reuse."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        def call(self, prompt: str) -> dict:
            """Return one normalized finding for applicable prompts."""
            return {
                "success": True,
                "response": json.dumps([{"problem": "Vague link"}]),
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: FakeClient())
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    run = directory(tmp_path)
    review = run / "review.csv"
    llm_ids = [
        item["finding_id"]
        for item in json.loads((run / "normalized-llm-findings.json").read_text())
    ]
    programmatic_id = json.loads(
        (run / "normalized-programmatic-findings.json").read_text()
    )[0]["finding_id"]
    rows = read_review(review)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    rows[0].update(
        classification="llm_eligible",
        classification_reason="Visible",
        llm_finding_id="; ".join(llm_ids[:2]),
        programmatic_finding_id=programmatic_id,
        match_reason="Together cover the row",
        review_notes="Partial alone",
    )
    rows[1].update(classification="programmatic", classification_reason="Markup")
    rows[2].update(classification="ambiguous", classification_reason="Unclear claim")
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run)]) == 0
    assert "Overall detection rate: 1/3" in (run / "report.md").read_text()
    rows[1]["llm_finding_id"] = llm_ids[0]
    rows[1]["match_reason"] = "Conflicts"
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    assert "Conflicting LLM finding ID" in capsys.readouterr().err
    rows[1]["llm_finding_id"] = "llm-unknown"
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    assert "Unknown LLM finding ID" in capsys.readouterr().err
    rows[1]["llm_finding_id"] = programmatic_id
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    assert "Unknown LLM finding ID" in capsys.readouterr().err
    rows[0]["llm_finding_id"] = ""
    rows[0]["programmatic_finding_id"] = ""
    rows[0]["match_reason"] = ""
    rows[0]["classification"] = "ambiguous"
    rows[1]["llm_finding_id"] = ""
    rows[1]["match_reason"] = ""
    rows[2]["classification"] = "unavailable_evidence"
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run)]) == 0
    assert (
        "LLM detection rate: N/A (0 eligible rows)" in (run / "report.md").read_text()
    )
    assert "Overall detection rate: 0/3" in (run / "report.md").read_text()


def test_live_execution_needs_explicit_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A noninteractive live flag without approval makes no paid request."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "available")
    monkeypatch.setattr(
        llm_audit, "LLMRequestClient", lambda **_: pytest.fail("paid call")
    )

    class DeclinedInput:
        def isatty(self) -> bool:
            """Represent an unattended input stream."""
            return False

    monkeypatch.setattr("sys.stdin", DeclinedInput())
    assert main(args(human_audit, html, "--live")) == 0
    assert (
        json.loads((directory(tmp_path) / "run.json").read_text())["complete"] is False
    )


@pytest.mark.parametrize("failure", [True, False])
def test_failed_or_over_budget_runs_keep_usage_and_cannot_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    """Failure and budget exhaustion stop after one request and remain inspectable."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        calls = 0

        def call(self, prompt: str) -> dict:
            """Return either a failure or an expensive successful response."""
            self.calls += 1
            return {
                "success": not failure,
                "response": "[]" if not failure else None,
                "error": "synthetic failure" if failure else None,
                "usage": {"input_tokens": 100000, "output_tokens": 20},
            }

    fake = FakeClient()
    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: fake)
    assert main(args(human_audit, html, "--live", "--approve-live")) == 1
    run = directory(tmp_path)
    manifest = json.loads((run / "run.json").read_text())
    assert fake.calls == 1
    assert manifest["complete"] is False
    assert manifest["usage"]["input_tokens"] == 100000
    assert float(manifest["estimated_cost_usd"]) > 0
    assert len(json.loads((run / "raw-llm-responses.json").read_text())) == 1
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
