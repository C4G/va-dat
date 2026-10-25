"""Report pooled Full evaluation results through the public CLI."""

import csv
import hashlib
import json

import openpyxl
import pytest
from bs4 import BeautifulSoup
from test_evaluation import recording_provider_usage
from test_full_execution import children
from test_full_preview import URLS, full_workspace, only_full, preview

from vision_aid.evaluation.cli import main

# Re-export the shared fixture for pytest discovery.
__all__ = ["full_workspace"]


def save_json(path, value):
    """Save a deliberate evidence mutation or synthetic input."""
    path.write_text(json.dumps(value), encoding="utf-8")


def review_rows(child):
    """Read the operator-editable decisions for one page."""
    with (child / "review.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def save_review(child, rows):
    """Save reviewer decisions while keeping all original columns."""
    path = child / "review.csv"
    with path.open(newline="") as stream:
        fields = csv.DictReader(stream).fieldnames
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def report_all(run, reviewer="Combined reviewer"):
    """Invoke deterministic combined reporting with reviewer attribution."""
    return main(["report-all", "--run-dir", str(run), "--reviewer", reviewer])


def refused_report(run, capsys, reviewer="Combined reviewer"):
    """Assert invalid evidence cannot publish a final combined report."""
    with pytest.raises(SystemExit) as error:
        report_all(run, reviewer)
    assert error.value.code == 2
    assert not (run / "report.md").exists()
    assert not (run / "report.html").exists()
    return capsys.readouterr().err


@pytest.fixture
def completed_review(full_workspace, monkeypatch):
    """Complete an approved run and record only its LLM match decisions."""
    recording_provider_usage(monkeypatch, "gpt-6-luna", {
        "prompt_tokens": 1000, "completion_tokens": 100,
    })
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    for child, _ in children(run, manifest):
        findings = json.loads((child / "normalized-llm-findings.json").read_text())
        rows = review_rows(child)
        for row, finding in zip(rows, findings):
            row.update(llm_finding_id=finding["finding_id"], match_reason="Complete fixture match")
        save_review(child, rows)
    return run, manifest


@pytest.mark.parametrize("problem", [
    "parent_incomplete", "parent_id", "missing_page", "duplicate_page", "reordered_pages",
    "child_parent_id", "expected_ids", "child_configuration", "human_evidence",
    "missing_snapshot", "snapshot_bytes", "pricing_bytes", "missing_raw_llm",
    "parent_cost", "parent_usage",
])
def test_report_requires_complete_membership_and_owned_evidence(completed_review, problem, capsys):
    """Completed flags cannot hide omitted pages or altered child evidence."""
    run, manifest = completed_review
    first = run / manifest["pages"][0]["run_dir"]
    if problem == "parent_incomplete":
        manifest["complete"] = False
    elif problem == "parent_id":
        manifest["run_id"] = "foreign-full-evaluation"
    elif problem == "missing_page":
        manifest["pages"].pop()
    elif problem == "duplicate_page":
        manifest["pages"].append(manifest["pages"][0])
    elif problem == "reordered_pages":
        manifest["pages"].reverse()
    elif problem == "child_parent_id":
        manifest["pages"][0]["run_id"] = "foreign-child"
    elif problem == "expected_ids":
        manifest["pages"][0]["human_finding_ids"].pop()
    elif problem == "child_configuration":
        saved = json.loads((first / "run.json").read_text())
        saved["configuration"]["model"] = "claude-haiku-5-5"
        save_json(first / "run.json", saved)
    elif problem == "human_evidence":
        path = first / "artifacts/human-findings.json"
        saved = json.loads(path.read_text())
        saved["human_findings"][0]["problem"] = "Replaced Human finding evidence"
        save_json(path, saved)
    elif problem == "missing_snapshot":
        (first / "snapshot.html").unlink()
    elif problem == "snapshot_bytes":
        (first / "snapshot.html").write_text("another page")
    elif problem == "pricing_bytes":
        path = first / "artifacts/pricing.json"
        path.write_text(path.read_text() + " ")
    elif problem == "missing_raw_llm":
        (first / "artifacts/raw-llm-responses.json").unlink()
    elif problem == "parent_cost":
        manifest["estimated_cost_usd"] = "7"
    elif problem == "parent_usage":
        manifest["usage"]["output_tokens"] = 99999
    save_json(run / "full.json", manifest)
    refused_report(run, capsys)


def test_empty_page_without_globals_still_has_a_report(full_workspace, monkeypatch):
    """A listed page with no Human findings can complete its empty review."""
    path = full_workspace / "human-audit.xlsx"
    book = openpyxl.load_workbook(path)
    book["Defect report"].delete_rows(5, 2)
    book.save(path)
    mapping_path = full_workspace / "snapshots/snapshots.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["human_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(mapping_path, mapping)
    recording_provider_usage(monkeypatch, "gpt-6-luna")
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    assert report_all(run) == 0
    empty = run / manifest["pages"][2]["run_dir"]
    text = BeautifulSoup((empty / "report.html").read_text(), "html.parser").get_text(" ", strip=True)
    assert "Overall: 0 caught / 0 eligible; Not defined: no imported Human findings" in text
    parent = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    assert "Overall: 0 caught / 3 eligible; 0.0%" in parent.get_text(" ", strip=True)
    comparison = parent.find("figure", attrs={"aria-labelledby": "page-chart-title"})
    assert [item.get_text(" ", strip=True) for item in comparison.select(".chart-value")] == [
        f"{url}: 0 caught / {eligible} eligible; " + ("0.0%" if eligible else "Not defined: no eligible Human findings")
        for url, eligible in zip(URLS, [2, 1, 0], strict=True)
    ]


def test_invalid_revised_review_withholds_stale_combined_rates(completed_review, capsys):
    """A report regenerated after an invalid edit must not leave earlier rates."""
    run, manifest = completed_review
    assert report_all(run) == 0
    (run / "report.md").write_text("superseded Markdown")
    first = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(first)
    rows[0]["classification"] = ""
    save_review(first, rows)
    assert "decision changed: classification" in refused_report(run, capsys)
    assert (first / "report.html").exists()


@pytest.mark.parametrize("problem", [
    "unclassified", "source_identity", "wrong_source_id", "foreign_id",
    "missing_reason", "reused_id", "missing_child", "missing_review",
])
def test_every_page_review_uses_the_existing_validation(completed_review, capsys, problem):
    """Unfinished or invalid page decisions cannot receive pooled credit."""
    run, manifest = completed_review
    first = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(first)
    if problem == "unclassified":
        rows[0]["classification"] = ""
    elif problem == "source_identity":
        rows[0]["source_element"] = "Changed source element"
    elif problem == "wrong_source_id":
        rows[0]["llm_finding_id"] = json.loads(
            (first / "artifacts/normalized-programmatic-findings.json").read_text())[0]["finding_id"]
    elif problem == "foreign_id":
        other = run / manifest["pages"][1]["run_dir"]
        rows[0]["llm_finding_id"] = json.loads(
            (other / "normalized-llm-findings.json").read_text())[0]["finding_id"]
    elif problem == "missing_reason":
        rows[0]["match_reason"] = ""
    elif problem == "reused_id":
        rows[1]["llm_finding_id"] = rows[0]["llm_finding_id"]
    elif problem == "missing_child":
        (first / "run.json").unlink()
    elif problem == "missing_review":
        (first / "review.csv").unlink()
    if problem not in {"missing_child", "missing_review"}:
        save_review(first, rows)
    refused_report(run, capsys)


def test_completed_child_report_survives_later_parent_failure(full_workspace, monkeypatch, capsys):
    """An incomplete parent withholds combined rates while its finished page reports."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    recording_provider_usage(monkeypatch, "claude-haiku-5-5", stream_failure_at=2)
    assert preview(full_workspace, "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    first = run / manifest["pages"][0]["run_dir"]
    assert main(["report", "--run-dir", str(first), "--reviewer", "Page reviewer"]) == 0
    saved = (first / "report.html").read_bytes()
    assert "Incomplete Full evaluations" in refused_report(run, capsys)
    assert (first / "report.html").read_bytes() == saved


def test_reviewer_description_is_required(completed_review, capsys):
    """Scoring cannot discard the identity of the reviewer making the decisions."""
    run, _ = completed_review
    assert "reviewer description" in refused_report(run, capsys, reviewer=" ")


@pytest.mark.parametrize("response", ["", "not JSON"])
def test_combined_report_keeps_unreadable_response_evidence(full_workspace, monkeypatch, response):
    """Successful Unreadable responses remain complete and are counted across pages."""
    recording_provider_usage(monkeypatch, "gpt-6-luna", text=response)
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    assert manifest["complete"]
    for child, saved in children(run, manifest):
        assert saved["complete"] and len(saved["format_failures"]) == len(saved["prompts"])
        assert json.loads((child / "normalized-llm-findings.json").read_text()) == []
        assert all(item["result"]["response"] == response for item in json.loads(
            (child / "artifacts/raw-llm-responses.json").read_text()))
    assert report_all(run) == 0
    assert sum(len(json.loads((child / "run.json").read_text())["format_failures"])
               for child, _ in children(run, manifest)) == 6


def test_successful_full_regeneration_replaces_only_its_generated_markdown(completed_review, capsys):
    """HTML replaces regenerated Markdown without sweeping historical outputs."""
    run, manifest = completed_review
    (run / "report.md").write_text("old combined result")
    historical = run.parent / "historical-run"
    historical.mkdir()
    (historical / "report.md").write_text("historical result")
    for page in manifest["pages"]:
        (run / page["run_dir"] / "report.md").write_text("old page result")
    assert report_all(run) == 0
    assert f"Combined HTML report: {run / 'report.html'}" in capsys.readouterr().out
    assert not (run / "report.md").exists()
    assert all(not (run / page["run_dir"] / "report.md").exists() for page in manifest["pages"])
    assert (historical / "report.md").read_text() == "historical result"
