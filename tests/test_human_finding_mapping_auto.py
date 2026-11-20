"""End-to-end checks of human-finding-mapping-auto, with a fake mapper and no network."""

import json

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    fake_providers,
    map_shared_defect,
    read_csv,
    reviewer_payload,
    run_all,
    workspace,
)
from vision_aid.evaluation.cli import main

ATTRIBUTION = f"{MODEL}/medium/mapper"


def mapping_auto(workspace):
    """Run human-finding-mapping-auto with Luna as the mapper."""
    return main([
        "human-finding-mapping-auto",
        "--human-audit", str(workspace / "audit.xlsx"),
        "--snapshots", str(workspace / "snapshots/snapshots.json"),
        "--output-dir", str(workspace / "mapping-review"),
        "--mapper-model", MODEL, "--max-cost-usd", "1", "--approve-live",
    ])


def test_mapping_is_built_approved_and_accepted_by_run_all(workspace, monkeypatch, capsys):
    """The mapper decides both pages, and run-all resolves the approved mapping."""
    log = fake_providers(monkeypatch, mapper=map_shared_defect)

    assert mapping_auto(workspace) == 0

    assert len(log["mapper"]) == 2
    # The Global finding is classified on the first page; the second page is
    # told that decision and only matches its checks.
    first, second = (reviewer_payload(prompt) for prompt in log["mapper"])
    assert all("decided_classification" not in human for human in first["human_findings"])
    decided = {human["human_audit"]["Issue Title"]: human.get("decided_classification")
               for human in second["human_findings"]}
    assert decided["Contact defect"] is None
    assert decided["Shared defect"] == {
        "classification": "programmatic", "classification_reason": "Checker covers it",
    }

    review = workspace / "mapping-review"
    mapping = json.loads((review / "human-finding-mapping.json").read_text())
    assert mapping["approved_by"] == ATTRIBUTION
    shared = [d for d in mapping["decisions"] if d["classification"] == "programmatic"]
    assert len(shared) == 1
    assert len(shared[0]["programmatic_by_page"]) == 2
    assert all(page["expectations"] for page in shared[0]["programmatic_by_page"].values())
    classes = {row["Issue Title"]: row["classification"]
               for row in read_csv(review / "classifications.csv")}
    assert classes == {"Home defect": "llm_eligible", "Contact defect": "llm_eligible",
                       "Shared defect": "programmatic"}

    record = json.loads((review / "automated-review.json").read_text())
    assert record["role"] == "mapper"
    assert record["reviewer"] == ATTRIBUTION
    assert record["status"] == "complete"
    assert record["estimated_cost_usd"] == "0.004"
    assert "$0.004" in capsys.readouterr().out

    code, _, manifest = run_all(workspace, review / "human-finding-mapping.json",
                                "--max-cost-usd", "1")
    assert code == 0
    assert manifest["human_finding_mapping_approved_by"] == ATTRIBUTION


def test_double_failure_writes_no_decisions(workspace, monkeypatch, capsys):
    """Two bad answers leave the prepared CSVs blank and no mapping file."""
    def answers(page, number):
        """Give the second page a reference it does not have."""
        decided = map_shared_defect(page, number)
        if page["source_url"].endswith("/contact/"):
            decided["decisions"][0]["programmatic_finding_refs"] = ["P009-F001"]
        return decided

    log = fake_providers(monkeypatch, mapper=answers)

    assert mapping_auto(workspace) == 1

    assert len(log["mapper"]) == 3
    assert "review failed" in capsys.readouterr().out.lower()
    review = workspace / "mapping-review"
    assert not (review / "human-finding-mapping.json").exists()
    assert all(row["classification"] == "" for row in read_csv(review / "classifications.csv"))
    record = json.loads((review / "automated-review.json").read_text())
    assert record["status"] == "failed"
