"""End-to-end check of `auto`: an Evaluation series with fake models and no network."""

import json
import re
import shutil
from decimal import Decimal

import pytest

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    URLS,
    approve_mapping,
    fake_providers,
    map_shared_defect,
    match_first_rows,
    read_csv,
    workspace,
)
from vision_aid.evaluation.cli import main

MAPPER = f"{MODEL}/medium/mapper_v1"
MATCHER = f"{MODEL}/medium/matcher_v1"


def match_by_run(page, number):
    """Decide matches so the three runs of the series differ.

    Each run sends two matcher requests (home, contact) plus any retries.
    Request 1 invents an ID and is retried. Requests 5 and 6, the second run's
    contact page, leave a row out, so that run's review fails. Request 8, the
    third run's contact page, also matches the contact page's first finding.
    """
    decided = match_first_rows(page, URLS if number == 8 else URLS[:1])
    if number == 1:
        decided["decisions"][0]["llm_finding_ids"] = ["llm-invented"]
    if number in (5, 6):
        decided["decisions"].pop()
    return decided


def auto(workspace, runs, *extra):
    """Run `auto` on the saved snapshots with Luna in every role."""
    return main([
        "auto", "-n", str(runs), "--model", MODEL,
        "--mapper-model", MODEL, "--matcher-model", MODEL,
        "--human-audit", str(workspace / "audit.xlsx"),
        "--snapshots", str(workspace / "snapshots/snapshots.json"),
        "--max-cost-usd", "1", "--approve-live", *extra,
    ])


def test_series_records_completed_runs_rates_and_cost(workspace, monkeypatch, capsys):
    """Three runs: the mapping is built once, one review fails, the series reports 2 of 3."""
    log = fake_providers(monkeypatch, mapper=map_shared_defect, matcher=match_by_run)

    assert auto(workspace, 3) == 1

    assert len(log["mapper"]) == 2
    assert len(log["matcher"]) == 8
    assert "llm-invented" in log["matcher"][1]

    mapping = workspace / "snapshots/human-finding-mapping/human-finding-mapping.json"
    assert json.loads(mapping.read_text())["approved_by"] == MAPPER

    (series,) = (workspace / ".model-evaluation/series").iterdir()
    record = json.loads((series / "series.json").read_text())
    assert record["model"]["model"] == MODEL
    assert record["reviewers"] == {"mapper": MAPPER, "matcher": MATCHER,
                                   "human_finding_mapping_approved_by": MAPPER}
    assert record["runs_requested"] == 3
    assert record["completed"] == 2
    assert record["snapshots"] == str((workspace / "snapshots/snapshots.json").resolve())
    assert record["human_finding_mapping"] == str(mapping.resolve())
    first, failed, third = record["runs"]
    assert first["status"] == "complete" and third["status"] == "complete"
    assert first["counts"]["llm"] == {"caught": 1, "eligible": 2}
    assert first["counts"]["overall"] == {"caught": 2, "eligible": 3}
    assert third["counts"]["llm"] == {"caught": 2, "eligible": 2}
    assert third["counts"]["overall"] == {"caught": 3, "eligible": 3}
    assert failed["status"] == "incomplete"
    assert "review failed" in failed["reason"]
    assert (series / "runs" / first["run_id"] / "report.html").is_file()

    # The failed review wrote no decisions and no report, and recorded its spend.
    failed_run = series / "runs" / failed["run_id"]
    assert not (failed_run / "report.html").exists()
    for page in (failed_run / "pages").iterdir():
        assert all(row["llm_finding_id"] == "" for row in read_csv(page / "review.csv"))
    failed_review = json.loads((failed_run / "automated-review.json").read_text())
    assert failed_review["status"] == "failed"
    assert failed_review["estimated_cost_usd"] == "0.006"

    cost = record["cost_by_role"]
    assert cost["mapper"]["estimated_cost_usd"] == "0.004"
    assert cost["matcher"]["estimated_cost_usd"] == "0.016"
    assert Decimal(cost["model"]["estimated_cost_usd"]) == Decimal("0.0005") * len(log["audit"])
    assert cost["matcher"]["usage"]["input_tokens"] == 80_000

    report = (series / "report.html").read_text()
    assert "2 of 3 runs completed" in report
    rates = dict(re.findall(
        r'<tr><th scope="row">(LLM|Overall)</th>((?:<td>[^<]*</td>){4})</tr>', report))
    assert re.findall(r"<td>([^<]*)</td>", rates["LLM"]) == [
        "75.0%", "50.0%", "100.0%", "35.4 points"]
    assert re.findall(r"<td>([^<]*)</td>", rates["Overall"]) == [
        "83.3%", "66.7%", "100.0%", "23.6 points"]
    catches = dict(re.findall(r'<th scope="row">(\w+ defect)</th><td>[^<]*</td><td>(\d/\d)</td>',
                              report))
    assert catches == {"Home defect": "2/2", "Contact defect": "1/2", "Shared defect": "2/2"}
    assert "$0.016" in report and MATCHER in report
    assert "2 of 3 runs completed" in capsys.readouterr().out

    # A second series on the same snapshots reuses the saved mapping.
    log["mapper"].clear()
    assert auto(workspace, 1) == 0
    assert not log["mapper"]


def test_bad_inputs_are_refused_before_capture_or_approval(workspace, monkeypatch, capsys):
    """Argument and mapping problems stop `auto` before any capture, prompt, or request."""
    log = fake_providers(monkeypatch, mapper=map_shared_defect)
    audit = ["--human-audit", str(workspace / "audit.xlsx")]
    base = ["auto", "-n", "1", "--model", MODEL, "--matcher-model", MODEL,
            "--max-cost-usd", "1", *audit]

    # A capture needs a new mapping, so it needs a mapper. (The fixture's fake
    # download has no pages left, so capturing would raise.)
    with pytest.raises(SystemExit):
        main([*base, "--capture", "--output-dir", str(workspace / "new"), "--approve-live"])
    assert "--mapper-model" in capsys.readouterr().err
    assert not (workspace / "new").exists()

    # A mapping approved for other snapshots is refused.
    mapping = approve_mapping(workspace)
    other = workspace / "other-snapshots"
    shutil.copytree(workspace / "snapshots", other)
    (other / "page-002.html").write_text("<html><body>Changed page</body></html>")
    with pytest.raises(SystemExit):
        main([*base, "--snapshots", str(other / "snapshots.json"),
              "--human-finding-mapping", str(mapping), "--approve-live"])
    assert "different snapshots" in capsys.readouterr().err

    # A mapping that records no snapshots can't be checked: warn, then go on to
    # the approval prompt, which a non-interactive run declines.
    legacy = json.loads(mapping.read_text())
    del legacy["snapshot_sha256_by_page"]
    (workspace / "legacy.json").write_text(json.dumps(legacy))
    assert main([*base, "--snapshots", str(workspace / "snapshots/snapshots.json"),
                 "--human-finding-mapping", str(workspace / "legacy.json")]) == 0
    out = capsys.readouterr().out
    assert "Warning" in out and "declined" in out

    assert not any(log.values())
    assert not (workspace / ".model-evaluation/series").exists()
