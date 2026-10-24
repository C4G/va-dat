"""Create approved audit decisions through human-edited CSV files and the CLI."""

import csv
import json

import pytest
from bs4 import BeautifulSoup
from test_evaluation import recording_provider_usage
from test_full_preview import URLS, full_workspace, only_full, preview

from vision_aid.evaluation.cli import main

__all__ = ["full_workspace"]


def rows(path):
    """Read a spreadsheet-friendly CSV produced for the operator."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def prepare(workspace, *, legacy=False):
    """Prepare a Human finding mapping review independently of model selection and execution."""
    directory = workspace / "human-finding-mapping-review"
    assert main([
        "baseline-prepare" if legacy else "human-finding-mapping-prepare",
        "--human-audit", str(workspace / "human-audit.xlsx"),
        "--snapshots", str(workspace / "snapshots/snapshots.json"),
        "--output-dir", str(directory),
    ]) == 0
    return directory


def save_rows(path, entered):
    """Save reviewer edits as an ordinary spreadsheet CSV."""
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=entered[0])
        writer.writeheader()
        writer.writerows(entered)


def fill_review(directory):
    """Record one joint catch, a cross-catch and explicit absences for five originals."""
    classifications = rows(directory / "classifications.csv")
    for row, classification in zip(
        classifications,
        [
            "programmatic",
            "llm_eligible",
            "unavailable_evidence",
            "llm_eligible",
            "ambiguous",
        ],
        strict=True,
    ):
        row.update(
            classification=classification,
            classification_reason="Reviewed original defect against saved evidence",
        )
    save_rows(directory / "classifications.csv", list(reversed(classifications)))
    matches = rows(directory / "programmatic-review.csv")
    catalog = rows(directory / "programmatic-findings.csv")
    for row in matches:
        rules = {
            "First local": ["LANG_001", "HEAD_003"],
            "Second local": ["LAND_001"],
        }.get(row["Issue Title"], [])
        row["programmatic_finding_refs"] = ";".join(
            next(
                f["finding_ref"]
                for f in catalog
                if f["source_url"] == row["source_url"] and f["rule"] == rule
            )
            for rule in rules
        )
        row["programmatic_reason"] = (
            "Jointly covers the complete defect"
            if rules
            else "No existing rule fully covers this defect"
        )
    save_rows(directory / "programmatic-review.csv", list(reversed(matches)))


def approve(directory, *, legacy=False):
    """Approve reviewed CSV choices using only the supported CLI."""
    return main([
        "baseline-approve" if legacy else "human-finding-mapping-approve",
        "--review-dir", str(directory), "--reviewer", "Human CSV reviewer",
    ])


def test_human_finding_mapping_preparation_lists_originals_once_and_readable_page_evidence(
    full_workspace,
):
    """Reviewers classify five originals once and choose matches for nine page rows."""
    directory = prepare(full_workspace)
    classifications = rows(directory / "classifications.csv")
    matches = rows(directory / "programmatic-review.csv")
    findings = rows(directory / "programmatic-findings.csv")
    assert len(classifications) == 5
    assert len({row["human_finding_id"] for row in classifications}) == 5
    assert all(row["actual result"] == "Original\nevidence" for row in classifications)
    assert all(
        row["classification"] == row["classification_reason"] == ""
        for row in classifications
    )
    assert len(matches) == 9
    assert {row["source_url"] for row in matches} == set(URLS)
    assert all(
        row["programmatic_finding_refs"] == row["programmatic_reason"] == ""
        for row in matches
    )
    assert findings and all(
        row["finding_ref"] and row["rule"] and row["problem"] for row in findings
    )
    assert any(row["rule"] == "LAND_001" for row in findings)
    assert any(row["element"] == "img" and row["target"] == "x" for row in findings)
    assert len({row["finding_ref"] for row in findings}) == len(findings)
    assert (directory / "README.md").is_file()
    evidence = json.loads((directory / "evidence.json").read_text())
    assert len(evidence["pages"]) == 3
    assert all((directory / page["snapshot"]).is_file() for page in evidence["pages"])


@pytest.mark.parametrize("legacy", [False, True])
def test_csv_approval_builds_reusable_expectations_consumed_by_new_full_run(
    full_workspace, monkeypatch, legacy
):
    """A reviewer never authors JSON or selectors; the approved result drives run scoring."""
    directory = prepare(full_workspace, legacy=legacy)
    fill_review(directory)
    assert approve(directory, legacy=legacy) == 0
    mapping = directory / ("baseline.json" if legacy else "human-finding-mapping.json")
    approved = json.loads(mapping.read_text())
    assert approved["approved_by"] == "Human CSV reviewer"
    assert len(approved["decisions"]) == 5
    assert sum(len(d["programmatic_by_page"]) for d in approved["decisions"]) == 9
    first = next(
        d for d in approved["decisions"] if d["classification"] == "programmatic"
    )
    assert {
        e["rule"] for e in first["programmatic_by_page"][URLS[0]]["expectations"]
    } == {"LANG_001", "HEAD_003"}
    assert '"run_id"' not in mapping.read_text()
    assert "human-finding-mapping-review" not in mapping.read_text()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    recording_provider_usage(monkeypatch, "gpt-6-luna")
    assert (
        preview(
            full_workspace,
            "--baseline" if legacy else "--human-finding-mapping",
            str(mapping),
            "--model",
            "gpt-6-luna",
            "--live",
            "--approve-live",
        )
        == 0
    )
    run, _ = only_full(full_workspace)
    assert (
        main(["report-all", "--run-dir", str(run), "--reviewer", "LLM reviewer"]) == 0
    )
    text = BeautifulSoup((run / "report.html").read_text(), "html.parser").get_text(
        " ", strip=True
    )
    assert "Programmatic: 1 caught / 1 eligible" in text
    assert "LLM: 0 caught / 2 eligible" in text
    assert "Overall: 2 caught / 5 eligible" in text
    assert "Human finding mapping approved by" in text


@pytest.mark.parametrize("command", ["run", "run-all"])
@pytest.mark.parametrize("live", [False, True])
def test_new_evaluations_require_approved_decisions_before_creating_a_run(
    full_workspace, capsys, command, live
):
    """New audits must complete Human finding mapping review before either evaluation entry point."""
    arguments = [
        command,
        "--human-audit",
        str(full_workspace / "human-audit.xlsx"),
        "--max-cost-usd",
        "1",
    ]
    if command == "run-all":
        arguments += ["--snapshots", str(full_workspace / "snapshots/snapshots.json")]
    else:
        arguments += [
            "--html",
            str(full_workspace / "snapshots/page-001.html"),
            "--source-url",
            URLS[0],
        ]
    if live:
        arguments += ["--live", "--approve-live"]
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    message = capsys.readouterr().err
    assert (
        "approved Human finding mapping" in message
        and "human-finding-mapping-prepare" in message
        and "--human-finding-mapping" in message
    )
    assert not (full_workspace / ".model-evaluation").exists()


@pytest.mark.parametrize(
    "change,error",
    [
        ("classification", "valid classification"),
        ("classification_reason", "classification_reason"),
        ("missing_original", "every original review row"),
        ("duplicate_original", "unknown or repeated"),
        ("original_evidence", "original Human finding evidence changed"),
        ("missing_page", "every original review row"),
        ("duplicate_page", "unknown or repeated"),
        ("reason", "programmatic_reason"),
        ("unknown_ref", "unknown or wrong-page"),
        ("wrong_page", "unknown or wrong-page"),
        ("reuse", "finding ID reuse"),
        ("duplicate_ref", "finding ID reuse"),
        ("programmatic_absence", "requires expected coverage"),
        ("not_testable_catch", "not testable"),
        ("evidence", "evidence checksum changed"),
        ("snapshot", "snapshot changed"),
    ],
)
def test_csv_approval_rejects_incomplete_or_conflicting_reviews(
    full_workspace, capsys, change, error
):
    """Errors identify review cells or evidence; incomplete choices never become approved JSON."""
    directory = prepare(full_workspace)
    fill_review(directory)
    classifications = rows(directory / "classifications.csv")
    matches = rows(directory / "programmatic-review.csv")
    first = next(row for row in matches if row["Issue Title"] == "First local")
    second = next(row for row in matches if row["Issue Title"] == "Second local")
    if change == "classification":
        classifications[0]["classification"] = "guess"
    elif change == "classification_reason":
        classifications[0]["classification_reason"] = ""
    elif change == "missing_original":
        classifications.pop()
    elif change == "duplicate_original":
        classifications[0] = classifications[1].copy()
    elif change == "original_evidence":
        classifications[0]["actual result"] = "Rewritten original"
    elif change == "missing_page":
        matches.pop()
    elif change == "duplicate_page":
        matches[0] = matches[1].copy()
    elif change == "reason":
        first["programmatic_reason"] = ""
    elif change == "unknown_ref":
        first["programmatic_finding_refs"] = "P999-F999"
    elif change == "wrong_page":
        first["programmatic_finding_refs"] = next(
            row["finding_ref"]
            for row in rows(directory / "programmatic-findings.csv")
            if row["source_url"] == URLS[1]
        )
    elif change == "reuse":
        second["programmatic_finding_refs"] = first["programmatic_finding_refs"]
    elif change == "duplicate_ref":
        first["programmatic_finding_refs"] += (
            ";" + first["programmatic_finding_refs"].split(";")[0]
        )
    elif change == "programmatic_absence":
        first["programmatic_finding_refs"] = ""
    elif change == "not_testable_catch":
        next(row for row in classifications if row["Issue Title"] == "First local")[
            "classification"
        ] = "unavailable_evidence"
    elif change == "evidence":
        path = directory / "evidence.json"
        path.write_text(path.read_text() + " ")
    elif change == "snapshot":
        (directory / "snapshots/page-001.html").write_text("changed snapshot")
    save_rows(directory / "classifications.csv", classifications)
    save_rows(directory / "programmatic-review.csv", matches)
    with pytest.raises(SystemExit) as failure:
        approve(directory)
    assert failure.value.code == 2
    assert error in capsys.readouterr().err
    assert not (directory / "human-finding-mapping.json").exists()


def test_catalog_edits_cannot_replace_checker_evidence_and_approval_never_overwrites(
    full_workspace, capsys
):
    """Only selected review references and explanations affect export; saved evidence stays authoritative."""
    directory = prepare(full_workspace)
    fill_review(directory)
    catalog = rows(directory / "programmatic-findings.csv")
    for row in catalog:
        row.update(rule="INVENTED_RULE", problem="Invented checker evidence")
    save_rows(directory / "programmatic-findings.csv", catalog)
    output = full_workspace / "approved/human-finding-mapping.json"
    arguments = [
        "human-finding-mapping-approve",
        "--review-dir",
        str(directory),
        "--reviewer",
        "Reviewer",
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    original = output.read_bytes()
    assert b"INVENTED_RULE" not in original
    with pytest.raises(SystemExit):
        main(arguments)
    assert "File exists" in capsys.readouterr().err
    assert output.read_bytes() == original


def test_csv_review_requires_reviewer_and_keeps_previous_work_on_repeated_preparation(
    full_workspace, capsys,
):
    """An unfinished or already-open review cannot be approved or silently replaced."""
    directory = prepare(full_workspace)
    fill_review(directory)
    original = (directory / "classifications.csv").read_bytes()
    with pytest.raises(SystemExit):
        prepare(full_workspace)
    assert (directory / "classifications.csv").read_bytes() == original
    with pytest.raises(SystemExit) as failure:
        main(["human-finding-mapping-approve", "--review-dir", str(directory), "--reviewer", " "])
    assert failure.value.code == 2
    assert "reviewer description is required" in capsys.readouterr().err
    assert not (directory / "human-finding-mapping.json").exists()
