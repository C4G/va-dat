"""End-to-end checks of the evaluator CLI, with a fake model and no network."""

import csv
import json
from types import SimpleNamespace

import openpyxl
import pytest

from vision_aid.evaluation.cli import main
from vision_aid.evaluation.inputs.human_audit import HEADERS

URLS = ["https://example.test/", "https://example.test/contact/"]
HTML = '<html><head><title>Test</title></head><body><img src="x"></body></html>'
MODEL = "gpt-6-luna"


def read_csv(path):
    """Read a CSV the evaluator wrote."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    """Save edited rows back to a CSV."""
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Create a small audit spreadsheet and saved snapshots, and block real requests."""
    workbook = openpyxl.Workbook()
    defects = workbook.active
    defects.title = "Defect report"
    defects.append(HEADERS)
    for number, page, title, steps in (
        (1, "Home", "Home defect", f"Open {URLS[0]}"),
        (2, "Contact", "Contact defect", f"Open {URLS[1]}"),
        (3, "Global", "Shared defect", f"Open {URLS[0]}"),
    ):
        defects.append([number, "img", "Chrome", page, title, steps,
                        "Actual", "Expected", "Fix it", "1.1.1"])
    url_list = workbook.create_sheet("URL list")
    url_list.append(["URL"])
    for url in URLS:
        url_list.append([url])
    workbook.save(tmp_path / "audit.xlsx")

    responses = iter([b"<html>first</html>", b"<html>second</html>"])
    monkeypatch.setattr(
        "requests.get",
        lambda *_, **__: SimpleNamespace(content=next(responses), raise_for_status=lambda: None),
    )
    assert main(["capture", "--human-audit", str(tmp_path / "audit.xlsx"),
                 "--output-dir", str(tmp_path / "snapshots")]) == 0
    for name in ("page-001.html", "page-002.html"):
        (tmp_path / "snapshots" / name).write_text(HTML)

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("model request"))
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("model request"))
    return tmp_path


def fake_model(monkeypatch, completion_tokens=0):
    """Answer every prompt with one issue and record each request."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    requests = []

    def create(**kwargs):
        """Return a Chat Completions-shaped response."""
        requests.append(kwargs)
        return SimpleNamespace(
            id="fake", model=MODEL,
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"issues": ["Fake issue"]}'),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(
                prompt_tokens=0, completion_tokens=completion_tokens,
                total_tokens=completion_tokens,
                prompt_tokens_details=None, completion_tokens_details=None,
            ),
        )

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return requests


def approve_mapping(workspace):
    """Prepare the mapping review, mark everything LLM eligible, and approve it."""
    review = workspace / "mapping-review"
    inputs = ["--human-audit", str(workspace / "audit.xlsx"),
              "--snapshots", str(workspace / "snapshots/snapshots.json")]
    assert main(["human-finding-mapping-prepare", *inputs, "--output-dir", str(review)]) == 0
    rows = read_csv(review / "classifications.csv")
    for row in rows:
        row.update(classification="llm_eligible", classification_reason="Needs judgment")
    write_csv(review / "classifications.csv", rows)
    rows = read_csv(review / "programmatic-review.csv")
    for row in rows:
        row["programmatic_reason"] = "No checker covers it"
    write_csv(review / "programmatic-review.csv", rows)
    assert main(["human-finding-mapping-approve", *inputs,
                 "--review-dir", str(review), "--reviewer", "Tester"]) == 0
    return review / "human-finding-mapping.json"


def run_all(workspace, mapping, *extra):
    """Run run-all and return its exit code and full.json."""
    code = main(["run-all", "--model", MODEL,
                 "--human-audit", str(workspace / "audit.xlsx"),
                 "--snapshots", str(workspace / "snapshots/snapshots.json"),
                 "--human-finding-mapping", str(mapping), *extra])
    (run,) = (workspace / ".model-evaluation/full-runs").iterdir()
    return code, run, json.loads((run / "full.json").read_text())


def test_capture_saves_every_listed_page(workspace):
    """Capture writes one HTML file per listed URL, in order."""
    saved = json.loads((workspace / "snapshots/snapshots.json").read_text())
    assert [entry["source_url"] for entry in saved["snapshots"]] == URLS


def test_preview_makes_no_model_requests(workspace):
    """Without --live, run-all prepares every page and calls no model."""
    code, run, manifest = run_all(workspace, approve_mapping(workspace), "--max-cost-usd", "1")
    assert code == 0
    assert not manifest["complete"]
    for page in manifest["pages"]:
        assert (run / page["run_dir"] / "review.csv").is_file()


def test_full_workflow_produces_reports(workspace, monkeypatch):
    """Capture, mapping, live run, review, and report-all work together."""
    mapping = approve_mapping(workspace)
    requests = fake_model(monkeypatch)
    code, run, manifest = run_all(workspace, mapping, "--max-cost-usd", "1",
                                  "--live", "--approve-live")
    assert code == 0 and manifest["complete"] and requests

    page = run / manifest["pages"][0]["run_dir"]
    llm = json.loads((page / "normalized-llm-findings.json").read_text())
    rows = read_csv(page / "review.csv")
    rows[0].update(llm_finding_id=llm[0]["finding_id"], match_reason="Same defect")
    write_csv(page / "review.csv", rows)

    assert main(["report-all", "--run-dir", str(run), "--reviewer", "Tester"]) == 0
    assert (run / "report.html").is_file()
    assert (page / "report.html").is_file()


def test_cost_limit_stops_execution(workspace, monkeypatch):
    """Execution stops once the spending limit is used up."""
    mapping = approve_mapping(workspace)
    fake_model(monkeypatch, completion_tokens=1_000_000)
    code, _, manifest = run_all(workspace, mapping, "--max-cost-usd", "0.01",
                                "--live", "--approve-live")
    assert code == 1
    assert not manifest["complete"]
    assert "exhausted" in manifest["incomplete_reason"]


def test_report_refuses_an_unfinished_run(workspace, capsys):
    """A preview can't produce a report."""
    _, run, _ = run_all(workspace, approve_mapping(workspace), "--max-cost-usd", "1")
    with pytest.raises(SystemExit):
        main(["report-all", "--run-dir", str(run), "--reviewer", "Tester"])
    assert "Incomplete" in capsys.readouterr().err


def test_review_cannot_change_approved_classification(workspace, monkeypatch, capsys):
    """Editing a mapping decision in review.csv blocks the report."""
    mapping = approve_mapping(workspace)
    fake_model(monkeypatch)
    _, run, manifest = run_all(workspace, mapping, "--max-cost-usd", "1",
                               "--live", "--approve-live")
    page = run / manifest["pages"][0]["run_dir"]
    rows = read_csv(page / "review.csv")
    rows[0]["classification"] = "ambiguous"
    write_csv(page / "review.csv", rows)
    with pytest.raises(SystemExit):
        main(["report-all", "--run-dir", str(run), "--reviewer", "Tester"])
    assert "decision changed" in capsys.readouterr().err
