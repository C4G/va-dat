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
    for row in (
        [1, "First link", "Chrome", "Home", "Unclear link", "Open page",
         "Vague link\nfor everyone", "Descriptive text", "Rename", "2.4.4", "Code", ""],
        [2, "Second link", "Chrome", "Global", "Missing destination", "Open page",
         "No href", "Working link", "Add href", "2.4.4", "Code", ""],
        [3, "Photo", "Chrome", "Home", "No alt text", "Open page",
         "Image lacks alt", "Alt text", "Add alt", "1.1.1", "Code", ""],
    ):
        sheet.append(row)
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
    assert {path.name for path in run.iterdir()} == {
        "review.csv", "snapshot.html", "normalized-programmatic-findings.json",
        "run.json", "artifacts",
    }
    artifacts = run / "artifacts"
    assert {path.name for path in artifacts.iterdir()} == {
        "human-findings.json", "pricing.json", "raw-programmatic-findings.json",
        "prompts", "payloads",
    }
    assert list((artifacts / "prompts").glob("*.json"))
    assert {path.name for path in (artifacts / "payloads").iterdir()} == {
        "cl01_payload.json", "cl02_payload.json", "cl03_payload.json",
    }
    assert "claude-haiku-4-5-20251001" in output
    assert "16000" in output and "24192" in output and "$0.01" in output
    assert (run / "snapshot.html").read_bytes() == html.read_bytes()
    raw = json.loads((run / "artifacts" / "raw-programmatic-findings.json").read_text())
    normalized = json.loads((run / "normalized-programmatic-findings.json").read_text())
    assert raw and [finding["raw_source"] for finding in normalized] == raw
    assert not (run / "programmatic_findings.json").exists()
    assert not (run / "programmatic-findings.json").exists()
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["run_id"] == run.name
    assert all(item["run_id"] == run.name for item in normalized)
    assert manifest["snapshot_sha256"] == hashlib.sha256(html.read_bytes()).hexdigest()
    assert manifest["human_audit_filename"] == human_audit.name
    assert manifest["human_audit_sha256"] == hashlib.sha256(human_audit.read_bytes()).hexdigest()
    imported = json.loads((run / "artifacts" / "human-findings.json").read_text())
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
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])


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
            if self.calls:
                saved = directory(tmp_path)
                responses = json.loads((saved / "artifacts" / "raw-llm-responses.json").read_text())
                findings = json.loads((saved / "normalized-llm-findings.json").read_text())
                manifest = json.loads((saved / "run.json").read_text())
                assert len(responses) == self.calls
                assert len(findings) == self.calls
                assert manifest["usage"]["input_tokens"] == self.calls * 1000
                assert manifest["complete"] is False
            self.calls += 1
            return {
                "success": True,
                "response": json.dumps(
                    [{"problem": "Unclear link", "location": "First link"}]
                ),
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cached_input_tokens": 500,
                    "cache_creation_input_tokens": 100,
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
    root_entries = {
        "review.csv", "snapshot.html", "normalized-llm-findings.json",
        "normalized-programmatic-findings.json", "run.json", "artifacts",
    }
    assert {path.name for path in run.iterdir()} == root_entries
    assert {path.name for path in (run / "artifacts").iterdir()} == {
        "human-findings.json", "pricing.json", "raw-llm-responses.json",
        "raw-programmatic-findings.json", "prompts", "payloads",
    }
    assert json.loads((run / "run.json").read_text())["run_id"] == run.name
    assert (
        json.loads((run / "run.json").read_text())["estimated_cost_usd"] == "0.006525"
    )
    assert (run / "artifacts" / "raw-llm-responses.json").exists()
    assert all(not (run / name).exists() for name in (
        "references.json", "raw-audit-responses.json", "normalized-audit-findings.json"
    ))
    findings = json.loads((run / "normalized-llm-findings.json").read_text())
    programmatic_file = run / "normalized-programmatic-findings.json"
    programmatic = json.loads(programmatic_file.read_text())
    assert findings and programmatic
    assert all(item["run_id"] == run.name for item in findings + programmatic)
    assert all(item["source"] == "llm" and item["finding_id"].startswith("llm-") for item in findings)
    assert all(item["finding_id"].startswith("programmatic-") for item in programmatic)
    review = run / "review.csv"
    rows = read_review(review)
    rows[0].update(
        classification="llm_eligible",
        classification_reason="Model can see link",
        llm_finding_id=findings[-1]["finding_id"],
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
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run)])
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", " "])
    write_review(review, list(reversed(rows)))
    assert main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"]) == 0
    assert {path.name for path in run.iterdir()} == root_entries | {"report.md"}
    report = (run / "report.md").read_text()
    assert "# LLM accessibility evaluation: https://example.test/" in report
    headings = ["How to read this report", "Summary", "Human findings", "What each part of the tool caught", "Missed", "Not testable from the page file"]
    assert [report.index("## " + heading + "\n") for heading in headings] == sorted(report.index("## " + heading + "\n") for heading in headings)
    assert all(text in report for text in (
        "benchmark is the Human audit", "This API uses LLM checks and Programmatic checks",
        "send extracted page content to the model", "apply fixed rules directly", "only saved HTML", "homepage only", "A reviewer decided",
        "fully cover the whole Human finding", "Partial coverage earns no credit",
    ))
    assert "Review decisions by: Codex agent (operator-directed)" in report
    assert "claude-haiku-4-5-20251001" in report and run.name in report
    assert "Of the 1 Human findings the LLM could be expected to detect from the page's HTML, it caught 1 (100.0%)" in report
    assert "Programmatic detection rate: Of the 1 Human findings the Programmatic checks could be expected to detect from the page's HTML, they caught 1 (100.0%)" in report
    assert "Of all 3 Human findings, either part of the tool caught 2 (66.7%)" in report
    assert "Estimated run cost: $0.01" in report
    assert "3000 input tokens" in report and "600 output tokens" in report
    assert "1500 cached input tokens" in report and "300 cache-creation input tokens" in report
    assert "2026-09-22" in report and "The actual bill may differ slightly." in report
    assert "unreadable output" not in report
    table = report.split("## Human findings\n", 1)[1].split("## What each part", 1)[0]
    assert table.index("Unclear link") < table.index("Missing destination") < table.index("No alt text")
    assert "| Unclear link | 2.4.4 | LLM | ✓ | ✗ |" in table
    assert "| Missing destination | 2.4.4 | Programmatic checks | ✗ | ✓ |" in table
    assert "LLM (link clarity check): Unclear link" in report
    assert "Programmatic check " + programmatic[0]["prompt"].replace("_", r"\_") in report
    assert "\n\n  - Why this counts: Full issue" in report
    assert "Visual context" in report
    assert all(row["human_finding_id"] not in report for row in rows)
    assert all(item["finding_id"] not in report for item in findings + programmatic)
    assert not any(text in report for text in ("source_element", "First link", "```", "<details>", "reasoning_tokens", "@ "))
    for row in rows:
        row["audit_finding_id"] = row.pop("llm_finding_id")
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
    imported = json.loads((run / "artifacts" / "human-findings.json").read_text())
    imported["human_audit_sha256"] = "changed"
    (run / "artifacts" / "human-findings.json").write_text(json.dumps(imported))
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])


def test_report_cross_catches_empty_misses_and_not_testable_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-catches count overall, blank misses survive, and text is escaped."""
    human_audit, html = inputs(tmp_path)
    book = openpyxl.load_workbook(human_audit)
    book.active["E2"] = "Unclear <main>|link"
    book.active.append([5, "Menu", "Chrome", "Home", "Hidden menu", "", "", "", "", "2.1.1"])
    book.active.append([6, "Widget", "Chrome", "Home", "Unclear claim", "", "", "", "", "4.1.2"])
    book.save(human_audit)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        calls = 0

        def call(self, prompt: str) -> dict:
            """One unreadable response and two findings with private locations."""
            self.calls += 1
            return {
                "success": True,
                "response": "not JSON" if self.calls == 1 else json.dumps([{"problem": "Use <main>|landmark", "location": "body > main"}]),
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    fake = FakeClient()
    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: fake)
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    run = directory(tmp_path)
    findings = json.loads((run / "normalized-llm-findings.json").read_text())
    manifest = json.loads((run / "run.json").read_text())
    responses = json.loads((run / "artifacts" / "raw-llm-responses.json").read_text())
    assert manifest["complete"] is True
    assert manifest["format_failures"] == ["page_title"]
    assert responses[0]["result"]["response"] == "not JSON"
    assert len(findings) == 2
    assert all(item["prompt"] != "page_title" for item in findings)
    review = run / "review.csv"
    rows = read_review(review)
    rows[0].update(classification="llm_eligible", llm_finding_id=findings[0]["finding_id"], match_reason="Full <main>|coverage")
    rows[1].update(classification="programmatic", llm_finding_id=findings[1]["finding_id"], match_reason="Cross-catch")
    rows[2].update(classification="programmatic")
    rows[3].update(classification="unavailable_evidence", classification_reason="Requires a live browser")
    rows[4].update(classification="ambiguous", classification_reason='An <img alt="">|needs judgment')
    write_review(review, list(reversed(rows)))
    assert main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"]) == 0
    report = (run / "report.md").read_text()
    assert r"Unclear \<main\>\|link" in report
    assert r"Use \<main\>\|landmark" in report
    assert "\n\n  - " + r"Why this counts: Full \<main\>\|coverage" in report
    assert "| Missing destination | 2.4.4 | Programmatic checks | ✓ | ✗ |" in report
    assert "it caught 1 (100.0%)" in report and "they caught 0 (0.0%)" in report
    assert "Of all 5 Human findings, either part of the tool caught 2 (40.0%)" in report
    assert "count only catches by the expected part" in report
    missed = report.split("## Missed\n", 1)[1].split("## Not testable", 1)[0]
    assert "### No alt text" in missed
    assert "Why it was expected to be caught" not in missed and "Why it was missed" not in missed
    excluded = report.split("## Not testable from the page file\n", 1)[1]
    assert "### Hidden menu" in excluded and "Requires a live browser" in excluded
    assert "### Unclear claim" in excluded and r'An \<img alt=""\>\|needs judgment' in excluded
    assert "remain in the Overall denominator" in excluded
    assert "3 input tokens" in report and "3 output tokens" in report
    assert "cached input" not in report and "cache-creation" not in report
    assert "The LLM returned unreadable output for 1 of 3 checks: page title check." in report
    assert all(row["human_finding_id"] not in report for row in rows)
    assert all(item["finding_id"] not in report for item in findings)
    assert not any(text in report for text in ("<main>", '<img alt="">', "body > main", "```", "source_element"))
    rows[2].update(classification_reason="The image is in the HTML", review_notes="No full finding")
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"]) == 0
    explained = (run / "report.md").read_text().split("## Missed\n", 1)[1]
    assert "\n- Why it was expected to be caught: The image is in the HTML" in explained
    assert "\n- Why it was missed: No full finding" in explained


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
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
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
    assert main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"]) == 0
    assert "Of all 3 Human findings, either part of the tool caught 1 (33.3%)" in (run / "report.md").read_text()
    rows[0]["match_reason"] = ""
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
    assert "needs a match reason" in capsys.readouterr().err
    rows[0]["match_reason"] = "Together cover the row"
    rows[1]["llm_finding_id"] = llm_ids[0]
    rows[1]["match_reason"] = "Conflicts"
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
    assert "Conflicting LLM finding ID" in capsys.readouterr().err
    rows[1]["llm_finding_id"] = "llm-unknown"
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
    assert "Unknown LLM finding ID" in capsys.readouterr().err
    rows[1]["llm_finding_id"] = programmatic_id
    write_review(review, rows)
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])
    assert "Unknown LLM finding ID" in capsys.readouterr().err
    rows[0]["llm_finding_id"] = ""
    rows[0]["programmatic_finding_id"] = ""
    rows[0]["match_reason"] = ""
    rows[0]["classification"] = "ambiguous"
    rows[1]["llm_finding_id"] = ""
    rows[1]["match_reason"] = ""
    rows[1]["classification"] = "ambiguous"
    rows[2]["classification"] = "unavailable_evidence"
    write_review(review, rows)
    assert main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"]) == 0
    assert (
        "No Human findings were expected to be detected by the LLM" in (run / "report.md").read_text()
    )
    assert "No Human findings were expected to be detected by the Programmatic checks" in (run / "report.md").read_text()
    assert "Of all 3 Human findings, either part of the tool caught 0 (0.0%)" in (run / "report.md").read_text()


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
    run = directory(tmp_path)
    manifest = json.loads((run / "run.json").read_text())
    assert manifest["complete"] is False
    assert manifest["incomplete_reason"] == "preview"
    assert {path.name for path in run.iterdir()} == {
        "review.csv", "snapshot.html", "normalized-programmatic-findings.json",
        "run.json", "artifacts",
    }
    assert (run / "artifacts" / "prompts").is_dir()
    assert not (run / "artifacts" / "raw-llm-responses.json").exists()


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
                "response": json.dumps([{"problem": "Unclear page title"}]) if not failure else None,
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
    assert manifest["incomplete_reason"] == (
        "synthetic failure" if failure else "cost guardrail exhausted"
    )
    assert {path.name for path in run.iterdir()} == {
        "review.csv", "snapshot.html", "normalized-llm-findings.json",
        "normalized-programmatic-findings.json", "run.json", "artifacts",
    }
    findings = json.loads((run / "normalized-llm-findings.json").read_text())
    assert len(findings) == (0 if failure else 1)
    assert all(item["run_id"] == run.name for item in findings)
    assert manifest["usage"]["input_tokens"] == 100000
    assert float(manifest["estimated_cost_usd"]) > 0
    assert len(json.loads((run / "artifacts" / "raw-llm-responses.json").read_text())) == 1
    with pytest.raises(SystemExit):
        main(["report", "--run-dir", str(run), "--reviewer", "Codex agent (operator-directed)"])


@pytest.mark.parametrize("filename", ["human-findings.json", "pricing.json"])
def test_report_requires_supporting_artifacts_without_reorganizing_old_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], filename: str,
) -> None:
    """Root-level evidence is neither a fallback nor an automatic migration."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        def call(self, prompt: str) -> dict:
            return {"success": True, "response": "[]", "usage": {}}

    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: FakeClient())
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    run = directory(tmp_path)
    rows = read_review(run / "review.csv")
    for row in rows:
        row.update(classification="llm_eligible")
    write_review(run / "review.csv", rows)
    (run / "artifacts" / filename).rename(run / filename)
    before = {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()}
    with pytest.raises(SystemExit) as error:
        main(["report", "--run-dir", str(run), "--reviewer", "Test reviewer"])
    assert error.value.code == 2
    assert str(run / "artifacts" / filename) in capsys.readouterr().err
    assert {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("filename,field", [
    ("run.json", "run_id"),
    ("artifacts/human-findings.json", "human_audit_sha256"),
    ("normalized-llm-findings.json", "run_id"),
    ("normalized-llm-findings.json", "source"),
    ("normalized-llm-findings.json", "page_url"),
    ("normalized-programmatic-findings.json", "run_id"),
    ("normalized-programmatic-findings.json", "source"),
    ("normalized-programmatic-findings.json", "page_url"),
])
def test_report_rejects_evidence_from_another_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], filename: str, field: str,
) -> None:
    """Moving supporting evidence preserves all provenance validation."""
    human_audit, html = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    class FakeClient:
        def call(self, prompt: str) -> dict:
            return {"success": True, "response": '[{"problem": "Unclear link"}]', "usage": {}}

    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: FakeClient())
    assert main(args(human_audit, html, "--live", "--approve-live")) == 0
    run = directory(tmp_path)
    path = run / filename
    evidence = json.loads(path.read_text())
    record = evidence[0] if isinstance(evidence, list) else evidence
    record[field] = "unrelated"
    path.write_text(json.dumps(evidence))
    with pytest.raises(SystemExit) as error:
        main(["report", "--run-dir", str(run), "--reviewer", "Test reviewer"])
    assert error.value.code == 2
    message = capsys.readouterr().err
    if field == "human_audit_sha256":
        assert "identity differs" in message
    else:
        assert "do not belong" in message or "does not belong" in message
    assert not (run / "report.md").exists()
