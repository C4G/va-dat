"""Run, review, and report Evaluation runs through the public CLI."""

import csv
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from processing_scripts.llm.registry import PROMPT_REGISTRY
from vision_aid.evaluation import llm_audit
from vision_aid.evaluation.cli import main

MODELS = ("claude-haiku-4-5-20251001", "claude-opus-5-5", "claude-sonnet-5-5")
CATEGORIES = [spec.name for spec in PROMPT_REGISTRY if not spec.is_summary]
RUN_ROOT = {"review.csv", "snapshot.html", "normalized-programmatic-findings.json",
            "run.json", "artifacts"}
REVIEWER = "Test reviewer"
# Synthetic markup that activates every non-summary prompt category.
HTML = (
    '<html lang="en"><head><title>Home</title></head><body>'
    '<header><nav><a href="/">Click here</a></nav></header><main><h1>Home</h1>'
    "<h3>News</h3><table><tr><th>Year</th></tr><tr><td>2026</td></tr></table>"
    '<iframe src="/v" title="Video"></iframe><form><label for="n">Name</label>'
    '<input id="n" required aria-describedby="h"><p id="h">Full name</p>'
    '<input placeholder="Email"><fieldset><legend>Plan</legend>'
    '<input type="radio" id="p" name="p"><label for="p">Basic</label></fieldset>'
    '</form><img src="team.png" alt="Team"><img src="line.png" alt="">'
    '<a href="/d"><img src="d.png" alt="Donate"></a>'
    '<img src="sales-chart.png" alt="Sales"><svg role="img"><title>Logo</title></svg>'
    '<i class="fa fa-star"></i><video src="v.mp4" controls></video></main>'
    "<footer>Footer</footer></body></html>"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a Human audit and Benchmark snapshot with credentials available."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Defect report"
    sheet.append([
        "Sr. #", "element name", "Browser Combination", "Page name", "Issue Title",
        "Steps to Reproduce", "actual result", "expected result",
        "Recommendation for Fix", "WCAG Sc", "Type of Change", "comment",
    ])
    sheet.append([1, "First link", "Chrome", "Home", "Unclear link", "Open page",
                  "Vague link\nfor everyone", "Descriptive", "Rename", "2.4.4", "Code", ""])
    for number, title, wcag in (
        (2, "Missing destination", "2.4.4"), (3, "Skipped heading", "1.3.1"),
        (4, "Hidden menu", "2.1.1"), (5, "Unclear claim", "4.1.2"),
        (6, "No captions", "1.2.2"),
    ):
        sheet.append([number, "Element", "Chrome", "Global", title, "", "", "", "", wcag])
    sheet.append([7, "Other", "Chrome", "Careers", "Outside scope"])
    book.save(tmp_path / "human-audit.xlsx")
    (tmp_path / "home.html").write_text(HTML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    return tmp_path


def run_cli(workspace: Path, *extra: str) -> int:
    """Invoke the public run command for the synthetic inputs."""
    return main([
        "run", "--human-audit", str(workspace / "human-audit.xlsx"),
        "--html", str(workspace / "home.html"),
        "--source-url", "https://example.test/", "--max-cost-usd", "1", *extra,
    ])


def report(run: Path) -> str:
    """Score a reviewed run and return the Markdown report."""
    assert main(["report", "--run-dir", str(run), "--reviewer", REVIEWER]) == 0
    return (run / "report.md").read_text(encoding="utf-8")


def refused(run: Path, capsys: pytest.CaptureFixture[str], reviewer: str = REVIEWER) -> str:
    """Assert reporting fails without writing a report, returning the error."""
    with pytest.raises(SystemExit) as error:
        main(["report", "--run-dir", str(run), "--reviewer", reviewer])
    assert error.value.code == 2
    assert not (run / "report.md").exists()
    return capsys.readouterr().err


def only_run(workspace: Path) -> Path:
    """Find the single run created under the workspace."""
    (run,) = (workspace / ".model-evaluation" / "runs").iterdir()
    return run


def load(run: Path, name: str):
    """Read one saved JSON artifact."""
    return json.loads((run / name).read_text())


def edit_review(run: Path, *decisions: dict[str, str]) -> None:
    """Apply reviewer decisions to review.csv rows in Human audit order."""
    path = run / "review.csv"
    with path.open(newline="") as stream:
        rows = sorted(csv.DictReader(stream), key=lambda row: int(row["source_row"]))
    for row, decision in zip(rows, decisions):
        row.update(decision)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(reversed(rows))


def fake_client(monkeypatch: pytest.MonkeyPatch, *responses: dict) -> list[str]:
    """Replace the request client, replaying responses and recording prompts."""
    prompts: list[str] = []
    default = {"success": True, "response": '[{"problem": "Vague link"}]',
               "usage": {"input_tokens": 1, "output_tokens": 1}}

    def call(prompt: str) -> dict:
        """Return the next scripted response."""
        prompts.append(prompt)
        return responses[len(prompts) - 1] if len(prompts) <= len(responses) else default

    monkeypatch.setattr(llm_audit, "LLMRequestClient",
                        lambda **_: SimpleNamespace(call=call))
    return prompts


@pytest.mark.parametrize("model", [None, "claude-opus-5-5", "claude-sonnet-5-5"])
def test_preview_preserves_evidence_without_provider_access(workspace, monkeypatch, model):
    """Credentials alone never buy requests, and all homepage rows survive."""
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("provider access"))
    assert run_cli(workspace, *(["--model", model] if model else [])) == 0
    run = only_run(workspace)
    assert {path.name for path in run.iterdir()} == RUN_ROOT
    assert {path.name for path in (run / "artifacts").iterdir()} == {
        "human-findings.json", "pricing.json", "raw-programmatic-findings.json",
        "prompts", "payloads",
    }
    manifest = load(run, "run.json")
    assert manifest["configuration"]["model"] == (model or MODELS[0])
    assert manifest["complete"] is False and manifest["incomplete_reason"] == "preview"
    assert len(CATEGORIES) == 18
    assert [prompt["name"] for prompt in manifest["prompts"]] == CATEGORIES
    assert (run / "snapshot.html").read_text(encoding="utf-8", errors="replace") == HTML
    audit = workspace / "human-audit.xlsx"
    assert manifest["human_audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
    assert manifest["snapshot_sha256"] == hashlib.sha256(HTML.encode()).hexdigest()
    raw = load(run, "artifacts/raw-programmatic-findings.json")
    normalized = load(run, "normalized-programmatic-findings.json")
    assert raw and [item["raw_source"] for item in normalized] == raw
    assert all(item["run_id"] == run.name for item in normalized)
    with (run / "review.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["source_row"] for row in rows] == ["2", "3", "4", "5", "6", "7"]
    assert rows[0]["actual result"] == "Vague link\nfor everyone"
    assert all(not row["classification"] for row in rows)


def test_live_run_without_approval_or_with_unsupported_model_buys_nothing(
    workspace, monkeypatch, capsys,
):
    """Declined approval prepares a preview; invalid models create no run."""
    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: pytest.fail("paid call"))
    with pytest.raises(SystemExit) as error:
        run_cli(workspace, "--model", "gpt-4o", "--live", "--approve-live")
    assert error.value.code == 2 and "invalid choice" in capsys.readouterr().err
    assert not (workspace / ".model-evaluation").exists()
    monkeypatch.setattr("builtins.input", lambda _: "no")
    for interactive in (False, True):
        monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: interactive))
        assert run_cli(workspace, "--live") == 0
    runs = list((workspace / ".model-evaluation" / "runs").iterdir())
    assert len(runs) == 2
    for run in runs:
        assert load(run, "run.json")["incomplete_reason"] == "preview"
        assert not (run / "artifacts" / "raw-llm-responses.json").exists()


@pytest.mark.parametrize("model,thinking,effort,cost", [
    (MODELS[0], {"type": "enabled", "budget_tokens": 16000}, None, "0.03915"),
    (MODELS[1], {"type": "adaptive"}, "medium", "0.1548"),
    (MODELS[2], {"type": "adaptive"}, "medium", "0.0783"),
])
def test_presets_stream_every_category_and_report_saved_prices(
    workspace, monkeypatch, model, thinking, effort, cost,
):
    """Each preset's request settings, final text, model, and costs persist."""
    requests, options = [], []

    def create(**kwargs):
        """Stream thinking, then final text, with cache usage."""
        requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=1,
                                cache_read_input_tokens=500, cache_creation_input_tokens=100)
        return nullcontext(iter([
            SimpleNamespace(type="message_start", message=SimpleNamespace(
                id="synthetic", model=model, type="message", usage=usage)),
            SimpleNamespace(type="content_block_start",
                            content_block=SimpleNamespace(type="thinking", thinking="SECRET")),
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(
                type="text", text='[{"problem": "Synthetic failure", "location": "body"}]')),
            SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"),
                            usage=SimpleNamespace(output_tokens=200)),
            SimpleNamespace(type="message_stop"),
        ]))

    def client(**kwargs):
        """Record client options and expose the fake Messages API."""
        options.append(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    monkeypatch.setattr("anthropic.Anthropic", client)
    assert run_cli(workspace, "--model", model, "--live", "--approve-live") == 0
    assert options == [{"api_key": "synthetic", "max_retries": 0}]
    assert len(requests) == len(CATEGORIES)
    for request in requests:
        assert request["model"] == model and request["thinking"] == thinking
        assert request["max_tokens"] == 24192 and request["stream"] is True
        assert "temperature" not in request
        assert request.get("output_config") == ({"effort": effort} if effort else None)
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True and manifest["estimated_cost_usd"] == cost
    assert manifest["configuration"]["reasoning_effort"] == effort
    raw = load(run, "artifacts/raw-llm-responses.json")
    assert all(item["result"]["provider"]["response_model"] == model for item in raw)
    assert "SECRET" not in json.dumps(raw)
    findings = load(run, "normalized-llm-findings.json")
    assert [finding["prompt"] for finding in findings] == CATEGORIES
    assert all(finding["model"] == model for finding in findings)
    assert all(finding["problem"] == "Synthetic failure" for finding in findings)
    assert all(finding["finding_id"].startswith("llm-") for finding in findings)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    text = report(run)
    assert model in text and run.name in text
    assert "published prices captured on 2026-10-01" in text
    assert "18000 input tokens" in text and "3600 output tokens" in text
    assert "9000 cached input tokens" in text and "1800 cache-creation input tokens" in text


def test_review_validation_and_report_metrics(workspace, monkeypatch, capsys):
    """Known decisions yield hand-calculated rates, cross-catches, and exclusions."""
    fake_client(
        monkeypatch,
        {"success": True, "response": "not JSON", "usage": {}},
        {"success": True, "response": "[]", "usage": {}},
    )
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True and manifest["format_failures"] == ["page_title"]
    llm = [item["finding_id"] for item in load(run, "normalized-llm-findings.json")]
    assert len(llm) == len(CATEGORIES) - 2
    programmatic = load(run, "normalized-programmatic-findings.json")[0]["finding_id"]
    assert "classification" in refused(run, capsys)
    decisions = [
        {"classification": "llm_eligible", "llm_finding_id": llm[0], "match_reason": "Full issue"},
        {"classification": "programmatic", "programmatic_finding_id": programmatic,
         "match_reason": "HTML check"},
        {"classification": "programmatic", "llm_finding_id": llm[1], "match_reason": "Cross-catch"},
        {"classification": "unavailable_evidence", "classification_reason": "Needs a browser",
         "llm_finding_id": "", "match_reason": ""},
        {"classification": "ambiguous", "classification_reason": "Needs judgment"},
        {"classification": "llm_eligible", "review_notes": "No full finding"},
    ]
    edit_review(run, *decisions)
    refused(run, capsys, reviewer=" ")
    edit_review(run, {"match_reason": ""})
    assert "needs a match reason" in refused(run, capsys)
    edit_review(run, {"llm_finding_id": programmatic, "match_reason": "Full issue"})
    assert "Unknown LLM finding ID" in refused(run, capsys)
    edit_review(run, *decisions[:3], {"llm_finding_id": llm[2], "match_reason": "Claimed"})
    assert "cannot claim coverage" in refused(run, capsys)
    edit_review(run, *decisions)
    text = report(run)
    assert ("Of the 2 Human findings the LLM could be expected to detect from the "
            "page's HTML, it caught 1 (50.0%)") in text
    assert "they caught 1 (50.0%)" in text
    assert "Of all 6 Human findings, either part of the tool caught 3 (50.0%)" in text
    assert "| Skipped heading | 1.3.1 | Programmatic checks | ✓ | ✗ |" in text
    assert "Why this counts: Full issue" in text
    missed = text.split("## Missed\n", 1)[1].split("## Not testable", 1)[0]
    assert "### No captions" in missed and "No full finding" in missed
    excluded = text.split("## Not testable from the page file\n", 1)[1]
    assert "### Hidden menu" in excluded and "Needs a browser" in excluded
    assert "### Unclear claim" in excluded and "Needs judgment" in excluded
    assert "The LLM returned unreadable output for 1 of 18 checks: page title check." in text
    assert all(finding_id not in text for finding_id in [*llm, programmatic])
    edit_review(run, *[{"classification": "ambiguous", "llm_finding_id": "",
                        "programmatic_finding_id": "", "match_reason": ""}] * 6)
    text = report(run)
    assert "No Human findings were expected to be detected by the LLM" in text
    assert "No Human findings were expected to be detected by the Programmatic checks" in text
    assert "Of all 6 Human findings, either part of the tool caught 0 (0.0%)" in text


@pytest.mark.parametrize("failure,calls,cost,reason", [
    (True, 2, "0.2002", "synthetic failure"),
    (False, 1, "0.1001", "cost guardrail exhausted"),
])
def test_failure_or_exhaustion_stops_and_keeps_partial_evidence(
    workspace, monkeypatch, capsys, failure, calls, cost, reason,
):
    """Requests stop, billed usage and findings remain, and reporting refuses."""
    usage = {"input_tokens": 100000, "output_tokens": 20}
    success = {"success": True, "response": '[{"problem": "Unclear title"}]', "usage": usage}
    stopped = {"success": False, "response": None, "error": "synthetic failure", "usage": usage}
    prompts = fake_client(monkeypatch, success, stopped if failure else success)
    limit = "1" if failure else "0.01"
    assert run_cli(workspace, "--max-cost-usd", limit, "--live", "--approve-live") == 1
    assert len(prompts) == calls
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is False and manifest["incomplete_reason"] == reason
    assert manifest["usage"]["input_tokens"] == calls * 100000
    assert manifest["estimated_cost_usd"] == cost
    assert len(load(run, "artifacts/raw-llm-responses.json")) == calls
    assert len(load(run, "normalized-llm-findings.json")) == 1
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    assert "Incomplete" in refused(run, capsys)


@pytest.mark.parametrize("name,field,message", [
    ("run.json", "run_id", "does not belong"),
    ("normalized-llm-findings.json", "run_id", "do not belong"),
    ("normalized-programmatic-findings.json", "page_url", "do not belong"),
    ("artifacts/human-findings.json", "human_audit_sha256", "identity differs"),
    ("artifacts/pricing.json", None, "pricing.json"),
])
def test_report_rejects_unrelated_or_missing_evidence(
    workspace, monkeypatch, capsys, name, field, message,
):
    """Reports cannot combine evidence from different or partial runs."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    if field is None:
        (run / name).unlink()
    else:
        evidence = load(run, name)
        (evidence[0] if isinstance(evidence, list) else evidence)[field] = "unrelated"
        (run / name).write_text(json.dumps(evidence))
    assert message in refused(run, capsys)
