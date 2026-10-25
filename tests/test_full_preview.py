"""Preview Full evaluations through the public evaluator CLI."""

import csv
import hashlib
import json

import openpyxl
import pytest
from evaluation_fixtures import run_with_mapping

from vision_aid.evaluation.cli import main
from vision_aid.evaluation.inputs.human_audit import HEADERS

URLS = ["https://example.test/", "https://example.test/contact/",
        "https://example.test/empty/"]
HTML = '<html><head><title>Test</title></head><body><img src="x"></body></html>'


@pytest.fixture
def full_workspace(tmp_path, monkeypatch):
    """Save a synthetic Human audit and reusable captured snapshot mapping."""
    human_audit_excel = openpyxl.Workbook()
    sheet = human_audit_excel.active
    sheet.title = "Defect report"
    sheet.append(HEADERS)
    for number, page_name, title, steps in (
        (1, "Repeated name", "First local", f"Open {URLS[0]}"),
        (2, "Repeated name", "Second local", f"Open {URLS[0]}"),
        (3, "Home", "Contact local", "Open https://example.test/Contact/."),
        (4, "Global", "Shared defect", f"Open {URLS[0]}"),
        (5, "Global", "Shared second defect", f"Open {URLS[0]}"),
    ):
        sheet.append([number, "Element", "Chrome", page_name, title, steps,
                      "Original\nevidence", "Expected", f"Read {URLS[2]}", "1.1.1"])
    urls = human_audit_excel.create_sheet("URL list")
    urls.append(["Page name", "URL"])
    for url in URLS:
        urls.append(["Repeated name", url])
    human_audit_excel.save(tmp_path / "human-audit.xlsx")
    saved = tmp_path / "snapshots"
    saved.mkdir()
    snapshots = []
    for number, url in enumerate(URLS, start=1):
        filename = f"page-{number:03d}.html"
        (saved / filename).write_text(HTML)
        snapshots.append({"source_url": url, "html": filename})
    mapping = {
        "human_audit_filename": "human-audit.xlsx",
        "human_audit_sha256": hashlib.sha256((tmp_path / "human-audit.xlsx").read_bytes()).hexdigest(),
        "snapshots": snapshots,
    }
    (saved / "snapshots.json").write_text(json.dumps(mapping))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("model request"))
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("model request"))
    monkeypatch.setattr("requests.get", lambda *_, **__: pytest.fail("HTTP download"))
    return tmp_path


def preview(workspace, *extra):
    """Preview with approved fixture decisions retained in every saved run."""
    return run_with_mapping(workspace, [
        "run-all", "--human-audit", str(workspace / "human-audit.xlsx"),
        "--snapshots", str(workspace / "snapshots/snapshots.json"),
        "--max-cost-usd", "2", *extra,
    ])


def only_full(workspace):
    """Read the only saved Full evaluation manifest."""
    (run,) = (workspace / ".model-evaluation/full-runs").iterdir()
    return run, json.loads((run / "full.json").read_text())


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "gpt-6-luna"])
def test_preview_maps_original_findings_and_keeps_page_evidence(full_workspace, capsys, model):
    """URL assignment, Globals and separate saved evidence survive key-free preview."""
    assert preview(full_workspace, "--model", model) == 0
    run, manifest = only_full(full_workspace)
    instructions = (run / "README.md").read_text(encoding="utf-8")
    assert "full.json" in instructions and "--live" in instructions
    assert f"report-all --run-dir {run}" in instructions
    assert manifest["configuration"]["model"] == model
    assert [page["source_url"] for page in manifest["pages"]] == URLS
    assert len({page["run_id"] for page in manifest["pages"]}) == 3
    assert manifest["complete"] is False and manifest["incomplete_reason"] == "preview"
    assert manifest["max_cost_usd"] == "2" and manifest["estimated_cost_usd"] == "0"
    assert all(value == 0 for value in manifest["usage"].values())
    memberships = []
    globals_by_page = []
    programmatic_ids = set()
    prompt_count = 0
    for page in manifest["pages"]:
        child = run / page["run_dir"]
        child_manifest = json.loads((child / "run.json").read_text())
        assert child_manifest["run_id"] == child.name == page["run_id"]
        assert child_manifest["source_url"] == page["source_url"]
        assert child_manifest["configuration"] == manifest["configuration"]
        prices = json.loads((child / "artifacts/pricing.json").read_text())
        assert model in prices["models"]
        assert (child / "snapshot.html").read_text() == HTML
        assert child_manifest["snapshot_sha256"] == hashlib.sha256(HTML.encode()).hexdigest()
        prompt_count += len(child_manifest["prompts"])
        with (child / "review.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        memberships.append([row["Issue Title"] for row in rows])
        globals_by_page.append({row["human_finding_id"] for row in rows if row["page_scope"] == "global"})
        assert all(row["actual result"] == "Original\nevidence" for row in rows)
        assert all(row["classification"] == "llm_eligible" for row in rows)
        findings = json.loads((child / "artifacts/normalized-programmatic-findings.json").read_text())
        assert not (child / "normalized-programmatic-findings.json").exists()
        instructions = (child / "README.md").read_text(encoding="utf-8")
        assert "review.csv" in instructions
        assert f"report --run-dir {child}" in instructions
        assert findings and all(item["page_url"] == page["source_url"] for item in findings)
        assert not programmatic_ids.intersection(item["finding_id"] for item in findings)
        programmatic_ids.update(item["finding_id"] for item in findings)
    assert memberships == [
        ["First local", "Second local", "Shared defect", "Shared second defect"],
        ["Contact local", "Shared defect", "Shared second defect"],
        ["Shared defect", "Shared second defect"],
    ]
    assert globals_by_page[0] == globals_by_page[1] == globals_by_page[2]
    originals = json.loads((run / "human-findings.json").read_text())
    assert len(originals["human_findings"]) == 5
    assert len(originals["page_assignments"]) == 3
    output = capsys.readouterr().out
    assert all(url in output for url in URLS)
    assert f"prompts: {prompt_count}" in output
    assert "Cost guardrail: $2" in output and "Pricing:" in output
    assert "Preview complete; no paid requests made." in output


def change_audit(workspace, steps):
    """Replace a reproduction URL and refresh its captured identity."""
    path = workspace / "human-audit.xlsx"
    human_audit_excel = openpyxl.load_workbook(path)
    human_audit_excel["Defect report"].cell(2, 6, steps)
    human_audit_excel.save(path)
    mapping_path = workspace / "snapshots/snapshots.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["human_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    mapping_path.write_text(json.dumps(mapping))


@pytest.mark.parametrize("steps", [
    "No reproduction URL", "Open https://example.test/EMPTY/",
    f"Open {URLS[0]} and {URLS[1]}",
])
def test_invalid_page_assignments_stop_before_preparation(full_workspace, steps, capsys):
    """Missing, arbitrary case aliases and ambiguous targets cannot start a run."""
    change_audit(full_workspace, steps)
    with pytest.raises(SystemExit) as error:
        preview(full_workspace)
    assert error.value.code == 2
    assert "exactly one listed target URL" in capsys.readouterr().err
    assert not (full_workspace / ".model-evaluation").exists()


@pytest.mark.parametrize("problem", [
    "checksum", "missing", "duplicate", "reordered", "outside", "missing_html",
])
def test_snapshot_mapping_must_match_the_human_audit(full_workspace, problem, capsys):
    """Mismatched capture identities and page sets never prepare an evaluation."""
    path = full_workspace / "snapshots/snapshots.json"
    mapping = json.loads(path.read_text())
    if problem == "checksum":
        mapping["human_audit_sha256"] = "other audit"
    elif problem == "missing":
        mapping["snapshots"].pop()
    elif problem == "duplicate":
        mapping["snapshots"].append(mapping["snapshots"][0])
    elif problem == "reordered":
        mapping["snapshots"].reverse()
    elif problem == "outside":
        mapping["snapshots"][0]["html"] = "../human-audit.xlsx"
    else:
        (full_workspace / "snapshots/page-001.html").unlink()
    path.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit) as error:
        preview(full_workspace)
    assert error.value.code == 2
    assert not (full_workspace / ".model-evaluation").exists()
    assert "Snapshot mapping" in capsys.readouterr().err


def test_page_preparation_failure_retains_parent_and_earlier_evidence(full_workspace, capsys):
    """A failed HTML read stops preparation and records every unfinished member."""
    (full_workspace / "snapshots/page-002.html").write_bytes(b"\xff")
    with pytest.raises(SystemExit) as error:
        preview(full_workspace)
    assert error.value.code == 2
    run, manifest = only_full(full_workspace)
    assert manifest["complete"] is False
    assert "preparation failed" in manifest["incomplete_reason"]
    assert [page["status"] for page in manifest["pages"]] == [
        "prepared", "preparation_failed", "unprepared",
    ]
    first, second, third = [run / page["run_dir"] for page in manifest["pages"]]
    assert (first / "review.csv").is_file()
    assert (first / "artifacts/raw-programmatic-findings.json").is_file()
    assert (second / "snapshot.html").read_bytes() == b"\xff"
    assert not third.exists()
    assert str(run) in capsys.readouterr().out


def test_audit_without_human_findings_cannot_start_evaluation(full_workspace, capsys):
    """Listed pages alone provide no Human findings to score."""
    path = full_workspace / "human-audit.xlsx"
    human_audit_excel = openpyxl.load_workbook(path)
    human_audit_excel["Defect report"].delete_rows(2, 5)
    human_audit_excel.save(path)
    mapping_path = full_workspace / "snapshots/snapshots.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["human_audit_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    mapping_path.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit) as error:
        preview(full_workspace)
    assert error.value.code == 2
    assert "no Human findings" in capsys.readouterr().err
    assert not (full_workspace / ".model-evaluation").exists()


def test_one_page_selection_and_human_ids_remain_compatible(full_workspace):
    """The one-page command selects the URL's local findings and stable Globals."""
    assert preview(full_workspace) == 0
    full_run, _ = only_full(full_workspace)
    originals = json.loads((full_run / "human-findings.json").read_text())
    assert main([
        "run", "--human-audit", str(full_workspace / "human-audit.xlsx"),
        "--html", str(full_workspace / "snapshots/page-001.html"),
        "--source-url", URLS[0], "--max-cost-usd", "2",
        "--human-finding-mapping", str(full_workspace / "fixture-human-finding-mapping.json"),
    ]) == 0
    (page_run,) = (full_workspace / ".model-evaluation/runs").iterdir()
    evidence = json.loads((page_run / "artifacts/human-findings.json").read_text())
    assert [finding["problem"] for finding in evidence["human_findings"]] == [
        "First local", "Second local", "Shared defect", "Shared second defect",
    ]
    assert evidence["human_findings"] == (
        originals["human_findings"][:2] + originals["human_findings"][3:]
    )
