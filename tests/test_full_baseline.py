"""Enforce shared approved decisions through the Full evaluation CLI."""

import hashlib
import json
from types import SimpleNamespace

import openpyxl
import pytest
from bs4 import BeautifulSoup
from test_evaluation import recording_provider_usage
from test_full_execution import children
from test_full_preview import URLS, full_workspace, only_full, preview
from test_full_report import (
    refused_report,
    report_all,
    review_rows,
    save_json,
    save_review,
)

__all__ = ["full_workspace"]
BASELINE_ARTIFACT = "artifacts/evaluation-baseline.json"


def load(path):
    """Read saved operator-visible evidence."""
    return json.loads(path.read_text())


@pytest.fixture
def full_approved(full_workspace):
    """Eight originals: two Programmatic, four LLM, and two not testable."""
    path = full_workspace / "human-audit.xlsx"
    book = openpyxl.load_workbook(path)
    sheet = book["Defect report"]
    for number, title in enumerate(("Shared model defect", "Unclear defect", "Partial defect"), start=6):
        sheet.append([number, "Element", "Chrome", "Global", title, f"Open {URLS[0]}",
                      "Original\nevidence", "Expected", "", "1.1.1"])
    book.save(path)
    book.close()
    mapping_path = full_workspace / "snapshots/snapshots.json"
    mapping = load(mapping_path)
    mapping["human_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(mapping_path, mapping)
    for number in range(1, 4):
        (full_workspace / f"snapshots/page-{number:03d}.html").write_text(
            '<html><head></head><body><img src="x"></body></html>'
        )
    assert preview(full_workspace) == 0
    seed, _ = only_full(full_workspace)
    original = load(seed / "human-findings.json")
    decisions = []
    for finding in original["human_findings"]:
        title = finding["problem"]
        classification = {
            "First local": "programmatic", "Shared defect": "programmatic",
            "Shared second defect": "unavailable_evidence", "Unclear defect": "ambiguous",
        }.get(title, "llm_eligible")
        pages = URLS if finding["page_scope"] == "global" else [
            original["page_assignments"][finding["human_finding_id"]]
        ]
        expectations = {
            "First local": [
                {"rule": "PAGE_TITLE_001", "evidence": {"raw_source": {"location": {"tag": "head"}}}},
                {"rule": "LANG_001", "evidence": {"problem": "<html> element missing lang attribute."}},
            ],
            "Shared defect": [{"rule": "HEAD_003", "evidence": {
                "problem": "The page does not contain an <h1> element."}}],
            "Contact local": [{"rule": "LAND_001", "evidence": {
                "problem": "Page does not contain a <main> landmark."}}],
        }.get(title, [])
        decisions.append({
            "human_finding_id": finding["human_finding_id"], "classification": classification,
            "classification_reason": f"Approved responsibility: {title}",
            "programmatic_by_page": {
                url: {"expectations": expectations, "reason": f"Approved complete evidence: {title}"}
                for url in pages
            },
        })
    baseline = {"schema_version": 1, "human_audit_sha256": original["human_audit_sha256"],
                "approved_by": "Independent Full audit reviewer", "decisions": decisions}
    baseline_path = full_workspace / "approved-baseline.json"
    save_json(baseline_path, baseline)
    return baseline_path, seed


def approved_run(workspace, baseline, *extra):
    """Create a separate Full evaluation with the selected approved decisions."""
    root = workspace / ".model-evaluation/full-runs"
    before = set(root.iterdir())
    assert preview(workspace, "--baseline", str(baseline), *extra) == 0
    (run,) = set(root.iterdir()) - before
    return run, load(run / "full.json")


def test_full_preparation_saves_one_baseline_and_resolves_each_pages_own_ids(
    full_workspace, full_approved,
):
    """Every child, including a Globals-only page, uses the parent's frozen source."""
    path, seed = full_approved
    run, manifest = approved_run(full_workspace, path)
    baseline = load(path)
    assert load(run / BASELINE_ARTIFACT) == baseline
    assert manifest["evaluation_baseline_sha256"] == hashlib.sha256((run / BASELINE_ARTIFACT).read_bytes()).hexdigest()
    assert load(run / "human-findings.json") == load(seed / "human-findings.json")
    previous = load(seed / "full.json")
    ids = set()
    for (child, saved), old_page in zip(children(run, manifest), previous["pages"], strict=True):
        assert load(child / BASELINE_ARTIFACT) == baseline
        assert saved["evaluation_baseline_sha256"] == manifest["evaluation_baseline_sha256"]
        assert load(child / "artifacts/human-findings.json") == load(seed / old_page["run_dir"] / "artifacts/human-findings.json")
        local_ids = {item["finding_id"] for item in load(child / "normalized-programmatic-findings.json")}
        rows = review_rows(child)
        assert all(row["classification"] and row["classification_reason"] for row in rows)
        selected = {identity for row in rows for identity in row["programmatic_finding_id"].split(";") if identity}
        assert selected <= local_ids
        assert not ids.intersection(selected)
        ids.update(selected)
        joint = next((row for row in rows if row["Issue Title"] == "First local"), None)
        if joint:
            assert len(joint["programmatic_finding_id"].split(";")) == 2
    globals_only = review_rows(run / manifest["pages"][2]["run_dir"])
    assert len(globals_only) == 5 and all(row["page_scope"] == "global" for row in globals_only)


@pytest.fixture
def completed_approved(full_workspace, full_approved, monkeypatch):
    """Review one complete Global LLM catch while keeping partial evidence uncredited."""
    path, _ = full_approved
    recording_provider_usage(monkeypatch, "gpt-6-luna")
    run, manifest = approved_run(full_workspace, path, "--model", "gpt-6-luna", "--live", "--approve-live")
    for number, (child, _) in enumerate(children(run, manifest)):
        rows = review_rows(child)
        llm = load(child / "normalized-llm-findings.json")
        for row in rows:
            if row["Issue Title"] == "Shared model defect" and number == 1:
                row.update(llm_finding_id=llm[0]["finding_id"], match_reason="Complete semantic Global match")
            elif row["Issue Title"] == "Partial defect":
                row["review_notes"] = f"Partial evidence only on page {number + 1}"
        save_review(child, rows)
    return run, manifest


def test_combined_reporting_rejects_a_child_with_different_saved_approved_decisions(
    completed_approved, capsys,
):
    """Even a locally valid child cannot substitute another audit-wide decision source."""
    run, manifest = completed_approved
    assert report_all(run) == 0
    child = run / manifest["pages"][2]["run_dir"]
    path = child / BASELINE_ARTIFACT
    baseline = load(path)
    # This local finding does not appear on child three, so its review still validates.
    baseline["decisions"][0]["classification_reason"] = "Different approved responsibility"
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n")
    saved = load(child / "run.json")
    saved["evaluation_baseline_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(child / "run.json", saved)
    assert "baseline" in refused_report(run, capsys).lower()


def rates(document):
    """Read the report's public source counts rather than reconstructing scoring."""
    overview = document.find("figure", attrs={"aria-labelledby": "detection-chart-title"})
    return [node.get_text(" ", strip=True) for node in overview.select(".chart-value")]


def test_combined_and_child_reports_keep_complete_matches_and_source_denominators(completed_approved):
    """Two P catches, a P cross-catch and one complete LLM Global catch cover four originals."""
    run, manifest = completed_approved
    assert report_all(run) == 0
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    assert rates(document) == [
        "LLM: 1 caught / 4 eligible; 25.0%",
        "Programmatic: 2 caught / 2 eligible; 100.0%",
        "Overall: 4 caught / 8 eligible; 50.0%",
    ]
    child_counts = [
        ["LLM: 0 caught / 3 eligible; 0.0%", "Programmatic: 2 caught / 2 eligible; 100.0%", "Overall: 2 caught / 7 eligible; 28.6%"],
        ["LLM: 1 caught / 3 eligible; 33.3%", "Programmatic: 1 caught / 1 eligible; 100.0%", "Overall: 3 caught / 6 eligible; 50.0%"],
        ["LLM: 0 caught / 2 eligible; 0.0%", "Programmatic: 1 caught / 1 eligible; 100.0%", "Overall: 1 caught / 5 eligible; 20.0%"],
    ]
    text = document.get_text(" ", strip=True)
    assert "Independent Full audit reviewer" in text and "Combined reviewer" in text
    assert "Complete semantic Global match" in text
    assert "Approved complete evidence: First local" in text
    assert len(document.select("#findings > tbody > tr")) == 8
    assert not document.select("script[src], link[rel=stylesheet], iframe")
    for (child, _), expected in zip(children(run, manifest), child_counts, strict=True):
        page = BeautifulSoup((child / "report.html").read_text(), "html.parser")
        assert rates(page) == expected
        assert "Independent Full audit reviewer" in page.get_text()
        assert not page.select("script[src], link[rel=stylesheet], iframe")
        programmatic = {item["finding_id"]: item for item in load(child / "normalized-programmatic-findings.json")}
        for row in review_rows(child):
            for identity in row["programmatic_finding_id"].split(";"):
                if identity:
                    assert identity in text
                    assert programmatic[identity]["problem"] in text
                    assert programmatic[identity]["run_id"] in text


@pytest.mark.parametrize("change,error", [
    ("classification", "decision changed: classification"),
    ("classification_reason", "decision changed: classification_reason"),
    ("programmatic_finding_id", "decision changed: programmatic_finding_id"),
    ("missing_evidence", "resolved to 0 findings"),
    ("foreign_id", "decision changed: programmatic_finding_id"),
    ("missing_child_baseline", "baseline"),
    ("missing_parent_baseline", "baseline"),
    ("parent_source", "checksum changed"),
])
def test_combined_report_rejects_changed_approved_decisions_or_missing_expected_evidence(
    completed_approved, capsys, change, error,
):
    """Every failure removes previously successful combined rates before returning an error."""
    run, manifest = completed_approved
    assert report_all(run) == 0
    (run / "report.md").write_text("superseded report")
    child = run / manifest["pages"][0]["run_dir"]
    rows = review_rows(child)
    if change == "missing_evidence":
        path = child / "normalized-programmatic-findings.json"
        save_json(path, [item for item in load(path) if item["problem_family"] != "PAGE_TITLE_001"])
    elif change in {"missing_child_baseline", "missing_parent_baseline"}:
        target = child if change == "missing_child_baseline" else run
        (target / BASELINE_ARTIFACT).unlink()
    elif change == "parent_source":
        path = run / BASELINE_ARTIFACT
        path.write_text(path.read_text() + " ")
    else:
        if change == "foreign_id":
            other = run / manifest["pages"][1]["run_dir"]
            rows[0]["programmatic_finding_id"] = load(other / "normalized-programmatic-findings.json")[0]["finding_id"]
        else:
            rows[0][change] = "llm_eligible" if change == "classification" else ""
        save_review(child, rows)
    assert error.lower() in refused_report(run, capsys).lower()


def test_different_models_keep_equal_combined_programmatic_counts_with_independent_llm_findings(
    full_workspace, full_approved, completed_approved, monkeypatch,
):
    """Run-local IDs and a genuine model miss change LLM rates while checker rates agree."""
    first, first_manifest = completed_approved
    path, _ = full_approved

    def create(**options):
        """Return a successful model response with no defects, without external requests."""
        return SimpleNamespace(
            id="no-defects", model=options["model"], usage=SimpleNamespace(
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                prompt_tokens_details=None, completion_tokens_details=None,
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"issues": []}'), finish_reason="stop")],
        )

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    second, second_manifest = approved_run(full_workspace, path, "--model", "gpt-6.1-sol", "--live", "--approve-live")
    # Changing the original selected file does not rewrite either saved interpretation.
    source = load(path)
    source["decisions"][0]["classification_reason"] = "Future manual update"
    save_json(path, source)
    for (a, _), (b, _) in zip(children(first, first_manifest), children(second, second_manifest), strict=True):
        a_findings = load(a / "normalized-programmatic-findings.json")
        b_findings = load(b / "normalized-programmatic-findings.json")
        assert {item["finding_id"] for item in a_findings}.isdisjoint(item["finding_id"] for item in b_findings)
        assert load(a / "normalized-llm-findings.json")
        assert load(b / "normalized-llm-findings.json") == []
        for left, right in zip(review_rows(a), review_rows(b), strict=True):
            for field in ("classification", "classification_reason", "programmatic_match_reason"):
                assert left[field] == right[field]
            lookup_a = {item["finding_id"]: item["problem_family"] for item in a_findings}
            lookup_b = {item["finding_id"]: item["problem_family"] for item in b_findings}
            assert {lookup_a[identity] for identity in left["programmatic_finding_id"].split(";") if identity} == {
                lookup_b[identity] for identity in right["programmatic_finding_id"].split(";") if identity
            }
    assert report_all(first) == report_all(second) == 0
    first_report = BeautifulSoup((first / "report.html").read_text(), "html.parser")
    second_report = BeautifulSoup((second / "report.html").read_text(), "html.parser")
    assert rates(first_report)[1] == rates(second_report)[1] == "Programmatic: 2 caught / 2 eligible; 100.0%"
    assert rates(first_report)[0] == "LLM: 1 caught / 4 eligible; 25.0%"
    assert rates(second_report)[0] == "LLM: 0 caught / 4 eligible; 0.0%"
    assert rates(second_report)[2] == "Overall: 3 caught / 8 eligible; 37.5%"
    assert "Future manual update" not in first_report.get_text() + second_report.get_text()


def test_full_preparation_automatically_selects_the_audits_bundled_baseline(
    full_workspace, full_approved, monkeypatch,
):
    """The audit checksum selects shared decisions once for all pages without a flag."""
    path, _ = full_approved
    baseline = load(path)
    directory = full_workspace / "bundled-baselines"
    directory.mkdir()
    (directory / f"{baseline['human_audit_sha256']}.json").write_bytes(path.read_bytes())
    monkeypatch.setattr("vision_aid.evaluation.baseline.BASELINE_DIRECTORY", directory)
    before = set((full_workspace / ".model-evaluation/full-runs").iterdir())
    assert preview(full_workspace) == 0
    (run,) = set((full_workspace / ".model-evaluation/full-runs").iterdir()) - before
    manifest = load(run / "full.json")
    assert load(run / BASELINE_ARTIFACT) == baseline
    assert all(saved["evaluation_baseline_sha256"] == manifest["evaluation_baseline_sha256"]
               for _, saved in children(run, manifest))
