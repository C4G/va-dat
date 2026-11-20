"""End-to-end checks of human-finding-mapping-auto, with a fake mapper and no network."""

import json

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    read_csv,
    run_all,
    workspace,
)
from tests.test_review_report_auto import fake_matcher as fake_reviewer
from vision_aid.evaluation.cli import main

ATTRIBUTION = f"{MODEL}/medium/mapper_v1"


def page_data(prompt):
    """Return the JSON payload the mapper prompt carries after `Data: `."""
    return json.JSONDecoder().raw_decode(prompt.split("Data: ", 1)[1])[0]


def map_shared_defect(prompt, _attempt):
    """Classify the Global finding as programmatic, matched to the page's first check."""
    page = page_data(prompt)
    first_ref = page["programmatic_findings"][0]["finding_ref"]
    decisions = []
    for human in page["human_findings"]:
        shared = human["human_audit"]["Issue Title"] == "Shared defect"
        decisions.append({
            "human_finding_id": human["human_finding_id"],
            "classification": "programmatic" if shared else "llm_eligible",
            "classification_reason": "Checker covers it" if shared else "Needs judgment",
            "programmatic_finding_refs": [first_ref] if shared else [],
            "programmatic_reason": "Same missing alt" if shared else "No checker covers it",
        })
    return {"decisions": decisions}


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
    mapper = fake_reviewer(monkeypatch, map_shared_defect)

    assert mapping_auto(workspace) == 0

    assert len(mapper) == 2
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


def test_global_disagreement_is_retried(workspace, monkeypatch):
    """Pages that classify a Global finding differently get the conflict sent back."""
    def answers(prompt, attempt):
        """Call the Global finding LLM eligible on the second page's first try."""
        decided = map_shared_defect(prompt, attempt)
        if attempt == 2:
            for decision in decided["decisions"]:
                if decision["classification"] == "programmatic":
                    decision.update(classification="llm_eligible",
                                    programmatic_finding_refs=[])
        return decided

    mapper = fake_reviewer(monkeypatch, answers)

    assert mapping_auto(workspace) == 0
    assert len(mapper) == 3
    assert "classified programmatic" in mapper[2]["messages"][0]["content"]
    mapping = json.loads(
        (workspace / "mapping-review/human-finding-mapping.json").read_text())
    assert [d["classification"] for d in mapping["decisions"]].count("programmatic") == 1


def test_double_failure_writes_no_decisions(workspace, monkeypatch, capsys):
    """Two bad answers leave the prepared CSVs blank and no mapping file."""
    def answers(prompt, attempt):
        """Give the second page a reference it does not have."""
        decided = map_shared_defect(prompt, attempt)
        if "example.test/contact/" in prompt:
            decided["decisions"][0]["programmatic_finding_refs"] = ["P009-F001"]
        return decided

    mapper = fake_reviewer(monkeypatch, answers)

    assert mapping_auto(workspace) == 1

    assert len(mapper) == 3
    assert "review failed" in capsys.readouterr().out.lower()
    review = workspace / "mapping-review"
    assert not (review / "human-finding-mapping.json").exists()
    assert all(row["classification"] == "" for row in read_csv(review / "classifications.csv"))
    record = json.loads((review / "automated-review.json").read_text())
    assert record["status"] == "failed"
