"""Report pooled Full evaluation results through the public CLI."""

import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from test_evaluation import recording_provider_usage
from test_full_execution import children
from test_full_preview import URLS, full_workspace, only_full, preview
from vision_aid.evaluation.cli import main


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
    return capsys.readouterr().err


@pytest.fixture
def completed_review(full_workspace, monkeypatch):
    """Execute uneven page memberships, then record hand-calculated decisions."""
    path = full_workspace / "human-audit.xlsx"
    book = openpyxl.load_workbook(path)
    sheet = book["Defect report"]
    for number, title in enumerate(
        ("Eligible uncaught", "Partial across pages", "Joint catch"), start=6,
    ):
        sheet.append([number, "Element", "Chrome", "Global", title,
                      f"Open {URLS[0]}", "Original", "Expected", "", "1.1.1"])
    book.save(path)
    mapping_path = full_workspace / "snapshots/snapshots.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["human_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(mapping_path, mapping)
    recording_provider_usage(monkeypatch, "gpt-6-luna", {
        "prompt_tokens": 1000, "completion_tokens": 100,
    })
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    for number, (child, _) in enumerate(children(run, manifest)):
        llm = json.loads((child / "normalized-llm-findings.json").read_text())
        programmatic = json.loads((child / "normalized-programmatic-findings.json").read_text())
        rows = review_rows(child)
        for row in rows:
            row.update(classification="llm_eligible", classification_reason="HTML is sufficient")
            title = row["Issue Title"]
            if title == "First local":
                row.update(llm_finding_id=llm[0]["finding_id"], match_reason="Complete first issue")
            elif title == "Second local":
                row.update(classification="programmatic", llm_finding_id=llm[1]["finding_id"],
                           match_reason="Cross-catch by LLM")
            elif title == "Contact local":
                row.update(programmatic_finding_id=programmatic[0]["finding_id"],
                           match_reason="Cross-catch by Programmatic checks")
            elif title == "Shared defect":
                if number == 0:
                    row.update(programmatic_finding_id=programmatic[0]["finding_id"],
                               match_reason="Complete Global on home")
                else:
                    identities = llm if number == 1 else llm[:1]
                    row.update(llm_finding_id=";".join(item["finding_id"] for item in identities),
                               match_reason="Complete Global on another page")
            elif title == "Shared second defect":
                row.update(classification="ambiguous" if number == 1 else "unavailable_evidence",
                           classification_reason=f"Not testable on page {number + 1}")
            elif title == "Eligible uncaught":
                row.update(classification="programmatic" if number == 1 else "unavailable_evidence",
                           classification_reason=f"Evidence varies on page {number + 1}")
            elif title == "Partial across pages":
                row.update(review_notes=f"Partial evidence only on page {number + 1}")
            elif title == "Joint catch":
                row.update(classification="programmatic")
                if number == 1:
                    row.update(programmatic_finding_id=";".join(
                        item["finding_id"] for item in programmatic[1:3]),
                        match_reason="These two findings jointly cover the entire Global")
        save_review(child, rows)
    return run, manifest


def test_combined_report_pools_original_findings_and_any_page_globals(completed_review):
    """Eight originals score 2/4 LLM, 1/3 Programmatic and 5/8 Overall."""
    run, manifest = completed_review
    assert report_all(run) == 0
    text = (run / "report.md").read_text()
    assert "LLM detection rate: Of the 4" in text and "caught 2 (50.0%)" in text
    assert "Programmatic detection rate: Of the 3" in text and "caught 1 (33.3%)" in text
    assert "Overall detection rate: Of all 8 Human findings" in text and "caught 5 (62.5%)" in text
    assert "Review decisions by: Combined reviewer" in text
    assert "Estimated run cost: $0.00" in text
    assert "1000 input tokens" in text and "100 output tokens" in text
    assert "published prices captured on 2026-10-09" in text
    assert "Unreadable responses: 0" in text
    originals = json.loads((run / "human-findings.json").read_text())
    for finding in originals["human_findings"]:
        assert text.count(finding["human_finding_id"]) == 1
    assert "Not testable on page 1" in text and "Not testable on page 2" in text
    assert "Partial evidence only on page 1" in text
    for page in manifest["pages"]:
        child = run / page["run_dir"]
        assert (child / "report.md").is_file()
        assert f"]({page['run_dir']}/report.md)" in text
        assert page["source_url"] in text
        for row in review_rows(child):
            for kind in ("llm", "programmatic"):
                for identity in row[f"{kind}_finding_id"].split(";"):
                    if identity:
                        assert identity in text
    assert "complete detection on any single page" in text
    assert "partial matches across pages" in text


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
    for child, _ in children(run, manifest):
        rows = review_rows(child)
        for row in rows:
            row.update(classification="unavailable_evidence", classification_reason="Needs a browser")
        save_review(child, rows)
    assert report_all(run) == 0
    empty = run / manifest["pages"][2]["run_dir"]
    text = (empty / "report.md").read_text()
    assert "Overall detection rate: No Human findings were imported for this page" in text
    assert "Overall detection rate: Of all 3 Human findings" in (run / "report.md").read_text()


def test_invalid_revised_review_withholds_stale_combined_rates(completed_review, capsys):
    """A report regenerated after an invalid edit must not leave earlier rates."""
    run, manifest = completed_review
    assert report_all(run) == 0
    first = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(first)
    rows[0]["classification"] = ""
    save_review(first, rows)
    assert "invalid classification" in refused_report(run, capsys)
    assert (first / "report.md").exists()


@pytest.mark.parametrize("title", ["Shared defect", "Eligible uncaught"])
def test_conflicting_testable_global_classifications_require_correction(completed_review, capsys, title):
    """Eligibility conflicts block reporting whether or not the Global was caught."""
    run, manifest = completed_review
    first = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(first)
    row = next(row for row in rows if row["Issue Title"] == title)
    row["classification"] = "programmatic" if title == "Shared defect" else "llm_eligible"
    save_review(first, rows)
    assert "conflicting testable classifications" in refused_report(run, capsys)


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
            (first / "normalized-programmatic-findings.json").read_text())[0]["finding_id"]
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


def test_no_eligible_sources_retain_all_originals_in_overall(completed_review):
    """All-not-testable reviews produce no source denominator and zero of eight Overall."""
    run, manifest = completed_review
    for child, _ in children(run, manifest):
        rows = review_rows(child)
        for row in rows:
            row.update(classification="unavailable_evidence", classification_reason="No saved evidence",
                       llm_finding_id="", programmatic_finding_id="", match_reason="")
        save_review(child, rows)
    assert report_all(run) == 0
    text = (run / "report.md").read_text()
    assert "LLM detection rate: No Human findings were expected" in text
    assert "Programmatic detection rate: No Human findings were expected" in text
    assert "Overall detection rate: Of all 8 Human findings" in text
    assert "caught 0 (0.0%)" in text


def test_completed_child_report_survives_later_parent_failure(full_workspace, monkeypatch, capsys):
    """An incomplete parent withholds combined rates while its finished page reports."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    recording_provider_usage(monkeypatch, "claude-haiku-5-5", stream_failure_at=2)
    assert preview(full_workspace, "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    first = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(first)
    for row in rows:
        row.update(classification="llm_eligible", classification_reason="Saved evidence")
    save_review(first, rows)
    assert main(["report", "--run-dir", str(first), "--reviewer", "Page reviewer"]) == 0
    saved = (first / "report.md").read_bytes()
    assert "Incomplete Full evaluations" in refused_report(run, capsys)
    assert (first / "report.md").read_bytes() == saved


def test_reviewer_description_is_required(completed_review, capsys):
    """Scoring cannot discard the identity of the reviewer making the decisions."""
    run, _ = completed_review
    assert "reviewer description" in refused_report(run, capsys, reviewer=" ")


def test_combined_report_summarizes_unreadable_responses(full_workspace, monkeypatch):
    """Successful Unreadable responses remain complete and are counted across pages."""
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")

    def create(**options):
        """Return an unreadable provider reply without leaving the process."""
        return SimpleNamespace(
            id="unreadable", model="gpt-6-luna",
            choices=[SimpleNamespace(message=SimpleNamespace(content="not JSON"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0,
                                  prompt_tokens_details=None, completion_tokens_details=None),
        )

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    for child, _ in children(run, manifest):
        rows = review_rows(child)
        for row in rows:
            row.update(classification="llm_eligible", classification_reason="HTML evidence")
        save_review(child, rows)
    assert report_all(run) == 0
    assert "Unreadable responses: 6 of 6 LLM checks" in (run / "report.md").read_text()


def test_report_all_help_explains_review_completion(capsys):
    """The combined reporting command explains when it can publish scores."""
    with pytest.raises(SystemExit) as error:
        main(["report-all", "--help"])
    assert error.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "every listed execution" in text and "all page reviews" in text
    assert "Global" in text and "once" in text
