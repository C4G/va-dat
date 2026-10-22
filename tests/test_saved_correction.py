"""Correct saved Full evaluations through the operator CLI without execution."""

import hashlib
import json

import pytest
from bs4 import BeautifulSoup
from test_evaluation import recording_provider_usage
from test_full_baseline import full_approved, load, rates
from test_full_execution import children
from test_full_preview import full_workspace, preview
from test_full_report import report_all, review_rows, save_review

from vision_aid.evaluation.cli import main

__all__ = ["full_approved", "full_workspace"]
LLM_FIELDS = ("llm_finding_id", "match_reason", "review_notes")


@pytest.fixture
def saved_legacy(full_workspace, full_approved, monkeypatch):
    """Save independently reviewed legacy results before any baseline is applied."""
    baseline, _ = full_approved
    root = full_workspace / ".model-evaluation/full-runs"
    before = set(root.iterdir())
    recording_provider_usage(monkeypatch, "gpt-6-luna")
    assert (
        preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live")
        == 0
    )
    (run,) = set(root.iterdir()) - before
    manifest = load(run / "full.json")
    for number, (child, _) in enumerate(children(run, manifest)):
        rows = review_rows(child)
        llm = load(child / "normalized-llm-findings.json")
        for row in rows:
            row.update(
                classification="llm_eligible",
                classification_reason="Legacy responsibility",
                match_reason="Old qualification remains exact",
                review_notes=f"Partial evidence on page {number}",
            )
            if row["Issue Title"] == "Shared model defect" and number == 1:
                row["llm_finding_id"] = llm[0]["finding_id"]
        save_review(child, rows)
    assert report_all(run) == 0
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda **_: pytest.fail("paid Claude request")
    )
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("paid OpenAI request"))
    monkeypatch.setattr(
        "requests.get", lambda *_, **__: pytest.fail("snapshot download")
    )
    return run, manifest, baseline


def correct(run, baseline):
    """Invoke the saved-run correction and report operation."""
    return main(
        [
            "correct-all",
            "--run-dir",
            str(run),
            "--baseline",
            str(baseline),
            "--reviewer",
            "Saved evidence correction reviewer",
        ]
    )


def files(run):
    """Capture exact saved bytes for preservation assertions."""
    return {
        str(path.relative_to(run)): path.read_bytes()
        for path in run.rglob("*")
        if path.is_file()
    }


def llm_decisions(run, manifest):
    """Keep every model-specific review cell indexed by page and original identity."""
    return {
        (child.name, row["human_finding_id"]): tuple(row[field] for field in LLM_FIELDS)
        for child, _ in children(run, manifest)
        for row in review_rows(child)
    }


def test_correction_backs_up_original_results_preserves_execution_and_regenerates_reports(
    saved_legacy,
):
    """Corrected evidence uses actual page-local IDs while all original results remain inspectable."""
    run, manifest, baseline = saved_legacy
    previous = files(run)
    llm = llm_decisions(run, manifest)
    assert correct(run, baseline) == 0
    history = run.parent / "review-history" / run.name
    inventory = load(history / "inventory.json")
    assert inventory["source_run"] == str(run)
    assert inventory["files"] == {
        name: hashlib.sha256(content).hexdigest() for name, content in previous.items()
    }
    assert files(history / "original") == previous
    for name, content in previous.items():
        if name.endswith(
            ("review.csv", "report.html", "report.md", "run.json", "full.json")
        ):
            continue
        assert (run / name).read_bytes() == content
    new_manifest = load(run / "full.json")
    assert all(new_manifest[key] == value for key, value in manifest.items())
    assert llm_decisions(run, new_manifest) == llm
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    assert rates(document) == [
        "LLM: 1 caught / 4 eligible; 25.0%",
        "Programmatic: 2 caught / 2 eligible; 100.0%",
        "Overall: 4 caught / 8 eligible; 50.0%",
    ]
    assert "Saved evidence correction reviewer" in document.get_text()
    assert "Independent Full audit reviewer" in document.get_text()
    ids = set()
    for child, saved in children(run, new_manifest):
        assert (child / "report.html").is_file()
        assert all(
            saved[key] == value
            for key, value in json.loads(
                previous[f"{child.relative_to(run)}/run.json"]
            ).items()
        )
        known = {
            item["finding_id"]
            for item in load(child / "normalized-programmatic-findings.json")
        }
        selected = {
            identity
            for row in review_rows(child)
            for identity in row["programmatic_finding_id"].split(";")
            if identity
        }
        assert selected <= known and not ids.intersection(selected)
        ids.update(selected)


def test_incompatible_saved_llm_catches_require_explicit_review_and_keep_original_backup(
    saved_legacy, capsys
):
    """A newly not-testable finding is surfaced, never silently awarded or cleared."""
    run, manifest, baseline_path = saved_legacy
    before = files(run)
    previous_llm = llm_decisions(run, manifest)
    baseline = load(baseline_path)
    decision = next(
        item
        for item in baseline["decisions"]
        if item["classification_reason"].endswith("Shared model defect")
    )
    decision["classification"] = "unavailable_evidence"
    baseline_path.write_text(json.dumps(baseline))
    with pytest.raises(SystemExit) as caught:
        correct(run, baseline_path)
    assert caught.value.code == 2
    message = capsys.readouterr().err
    assert "explicit LLM review" in message
    assert decision["human_finding_id"] in message
    assert "correction-review.json" in message
    assert not (run / "report.html").exists()
    assert files(run.parent / "review-history" / run.name / "original") == before
    assert llm_decisions(run, manifest) == previous_llm
    pending = load(run / "correction-review.json")
    assert (
        pending["incompatible_llm_decisions"][0]["human_finding_id"]
        == decision["human_finding_id"]
    )
    # The operator explicitly removes the incompatible claim and reruns correction.
    for child, _ in children(run, manifest):
        rows = review_rows(child)
        for row in rows:
            if row["human_finding_id"] == decision["human_finding_id"]:
                row["llm_finding_id"] = ""
        save_review(child, rows)
    assert correct(run, baseline_path) == 0
    assert not (run / "correction-review.json").exists()
    assert files(run.parent / "review-history" / run.name / "original") == before


def test_corrected_reports_distinguish_original_llm_review_from_baseline_and_correction(
    saved_legacy,
):
    """The correction reviewer does not replace attribution for retained LLM decisions."""
    run, _, baseline = saved_legacy
    assert correct(run, baseline) == 0
    manifest = load(run / "full.json")
    provenance = manifest["review_correction"]
    assert provenance["corrected_by"] == "Saved evidence correction reviewer"
    assert provenance["original_llm_reviewers"] == ["Combined reviewer"]
    assert provenance["baseline_approved_by"] == "Independent Full audit reviewer"
    history = run.parent / "review-history" / run.name
    assert (
        provenance["backup_inventory_sha256"]
        == hashlib.sha256((history / "inventory.json").read_bytes()).hexdigest()
    )
    for report_path, metadata in [
        (run / "report.html", manifest),
        *[(child / "report.html", saved) for child, saved in children(run, manifest)],
    ]:
        text = BeautifulSoup(report_path.read_text(), "html.parser").get_text(
            " ", strip=True
        )
        assert (
            "Saved-run correction reviewed by: Saved evidence correction reviewer"
            in text
        )
        assert "Original LLM review by: Combined reviewer" in text
        assert metadata["review_correction"]["original_llm_reviewers"] == [
            "Combined reviewer"
        ]


@pytest.mark.parametrize(
    "change,error",
    [
        ("missing_evidence", "resolved to 0 findings"),
        ("wrong_audit", "Human audit identity differs"),
        ("incomplete", "completed Full evaluation"),
        ("foreign_child", "directory ownership differs"),
    ],
)
def test_failed_correction_preserves_previous_reports_and_removes_stale_combined_rates(
    saved_legacy,
    capsys,
    change,
    error,
):
    """Unresolvable saved evidence never leaves successful old combined rates in place."""
    run, manifest, baseline = saved_legacy
    if change == "missing_evidence":
        child = run / manifest["pages"][0]["run_dir"]
        path = child / "normalized-programmatic-findings.json"
        path.write_text(
            json.dumps(
                [
                    item
                    for item in load(path)
                    if item["problem_family"] != "PAGE_TITLE_001"
                ]
            )
        )
    elif change == "wrong_audit":
        source = load(baseline)
        source["human_audit_sha256"] = "unrelated-human-audit"
        baseline.write_text(json.dumps(source))
    elif change == "incomplete":
        manifest["complete"] = False
        (run / "full.json").write_text(json.dumps(manifest))
    elif change == "foreign_child":
        manifest["pages"][0]["run_dir"] = "../foreign-run"
        (run / "full.json").write_text(json.dumps(manifest))
    previous = files(run)
    with pytest.raises(SystemExit) as caught:
        correct(run, baseline)
    assert caught.value.code == 2
    message = capsys.readouterr().err
    assert error in message
    assert "Original evidence and reports preserved" in message
    assert not (run / "report.html").exists()
    history = run.parent / "review-history" / run.name
    assert files(history / "original") == previous
    # Unresolved expectations are diagnosed before baseline/CSV replacement.
    for name, contents in previous.items():
        if name.endswith(("review.csv", "run.json")):
            assert (run / name).read_bytes() == contents


def test_retry_reuses_and_verifies_first_backup_without_replacing_originals(
    saved_legacy, capsys
):
    """Repeated correction is reproducible and refuses corrupted backup evidence."""
    run, _, baseline = saved_legacy
    previous = files(run)
    assert correct(run, baseline) == 0
    history = run.parent / "review-history" / run.name
    inventory = (history / "inventory.json").read_bytes()
    assert correct(run, baseline) == 0
    assert files(history / "original") == previous
    assert (history / "inventory.json").read_bytes() == inventory
    (history / "original/report.html").write_text("Corrupted preserved result")
    before_attempt = files(run)
    with pytest.raises(SystemExit):
        correct(run, baseline)
    assert "backup failed verification" in capsys.readouterr().err
    assert files(run) == before_attempt


def test_correction_discovers_bundled_baseline_without_model_or_snapshot_selection(
    saved_legacy, monkeypatch
):
    """Saved correction chooses approved decisions by the original Human audit checksum."""
    run, _, baseline = saved_legacy
    source = load(baseline)
    directory = baseline.parent / "bundled"
    directory.mkdir()
    (directory / f"{source['human_audit_sha256']}.json").write_bytes(
        baseline.read_bytes()
    )
    monkeypatch.setattr("vision_aid.evaluation.baseline.BASELINE_DIRECTORY", directory)
    assert (
        main(
            [
                "correct-all",
                "--run-dir",
                str(run),
                "--reviewer",
                "Bundled baseline correction",
            ]
        )
        == 0
    )
    assert load(run / "artifacts/evaluation-baseline.json") == source
