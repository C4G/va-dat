"""End-to-end checks of review-report-auto, with fake models and no network.

Retries and a failed review are covered once, by the series test.
"""

import json

import pytest

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    URLS,
    approve_mapping,
    fake_providers,
    match_first_rows,
    read_csv,
    run_all,
    workspace,
)
from vision_aid.evaluation.cli import main

ATTRIBUTION = f"{MODEL}/medium/matcher"


def review_report_auto(run):
    """Run review-report-auto with Luna as the matcher."""
    return main(["review-report-auto", "--run-dir", str(run), "--matcher-model", MODEL,
                 "--max-cost-usd", "1", "--approve-live"])


def test_full_evaluation_is_reviewed_and_reported(workspace, monkeypatch, capsys):
    """The matcher fills every page's review.csv and report-all's reports follow."""
    mapping = approve_mapping(workspace)
    log = fake_providers(monkeypatch, matcher=lambda page, _: match_first_rows(page, URLS))
    code, run, manifest = run_all(workspace, mapping, "--max-cost-usd", "1",
                                  "--live", "--approve-live")
    assert code == 0 and manifest["complete"]
    pages = [run / page["run_dir"] for page in manifest["pages"]]

    assert review_report_auto(run) == 0

    assert len(log["matcher"]) == 2
    for page in pages:
        llm = json.loads((page / "normalized-llm-findings.json").read_text())
        rows = read_csv(page / "review.csv")
        assert rows[0]["llm_finding_id"] == llm[0]["finding_id"]
        assert rows[0]["match_reason"] == "Same image problem"
        assert all(row["llm_finding_id"] == "" for row in rows[1:])
        assert ATTRIBUTION in (page / "report.html").read_text()
    assert ATTRIBUTION in (run / "report.html").read_text()

    record = json.loads((run / "automated-review.json").read_text())
    assert record["role"] == "matcher"
    assert record["reviewer"] == ATTRIBUTION
    assert record["status"] == "complete"
    assert record["estimated_cost_usd"] == "0.004"
    assert record["usage"]["input_tokens"] == 20_000
    assert "$0.004" in capsys.readouterr().out


def test_preview_is_refused_before_any_request(workspace, monkeypatch, capsys):
    """A preview run has nothing to review, so no matcher request is sent."""
    _, run, _ = run_all(workspace, approve_mapping(workspace), "--max-cost-usd", "1")
    log = fake_providers(monkeypatch, matcher=lambda page, _: match_first_rows(page, URLS))
    with pytest.raises(SystemExit):
        review_report_auto(run)
    assert "Incomplete" in capsys.readouterr().err
    assert not log["matcher"]
