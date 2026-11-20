"""End-to-end check of `auto`: an Evaluation series with fake models and no network."""

import json
import re
from decimal import Decimal
from types import SimpleNamespace

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    workspace,
)
from tests.test_human_finding_mapping_auto import map_shared_defect
from vision_aid.evaluation.cli import main

MAPPER = f"{MODEL}/medium/mapper_v1"
MATCHER = f"{MODEL}/medium/matcher_v1"


def fake_providers(monkeypatch, matcher_answers):
    """Stand in for every role on one fake OpenAI client.

    The model under test gets plain prompts and answers one issue for 1,000
    output tokens ($0.0005 on Luna). Reviewer requests ask for a JSON-schema
    response: mapper prompts carry programmatic findings and get
    `map_shared_defect`; matcher prompts carry LLM findings and get
    `matcher_answers(prompt, matcher_request_number)`. Each reviewer request
    reports 10,000 input and 2,000 output tokens ($0.002).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    log = {"audit": [], "mapper": [], "matcher": []}

    def create(**kwargs):
        """Return a Chat Completions-shaped response for whichever role asked."""
        prompt = kwargs["messages"][0]["content"]
        if "response_format" not in kwargs:
            log["audit"].append(prompt)
            content, usage = '{"issues": ["Fake issue"]}', (0, 1_000)
        elif '"llm_findings"' in prompt:
            log["matcher"].append(prompt)
            content = json.dumps(matcher_answers(prompt, len(log["matcher"])))
            usage = (10_000, 2_000)
        else:
            log["mapper"].append(prompt)
            content, usage = json.dumps(map_shared_defect(prompt, 0)), (10_000, 2_000)
        return SimpleNamespace(
            id="fake", model=MODEL,
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop",
            )],
            usage=SimpleNamespace(
                prompt_tokens=usage[0], completion_tokens=usage[1],
                total_tokens=sum(usage),
                prompt_tokens_details=None, completion_tokens_details=None,
            ),
        )

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return log


def match_home_page_only(prompt, number):
    """Match the home page's first Human finding to its first LLM finding.

    Request 1 invents an ID (retried), and requests 5 and 6, the second run's
    contact page, leave a row out, so that run's review fails.
    """
    humans = list(dict.fromkeys(re.findall(r'"human_finding_id": "(human-\w+)"', prompt)))
    llm = list(dict.fromkeys(re.findall(r'"finding_id": "(llm-\w+)"', prompt)))
    home = '"source_url": "https://example.test/"' in prompt
    decisions = [
        {"human_finding_id": human,
         "llm_finding_ids": [llm[0]] if home and position == 0 else [],
         "match_reason": "Same image problem" if home and position == 0 else "",
         "review_notes": ""}
        for position, human in enumerate(humans)
    ]
    if number == 1:
        decisions[0]["llm_finding_ids"] = ["llm-invented"]
    if number in (5, 6):
        decisions.pop()
    return {"decisions": decisions}


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
    """Two runs: the mapping is built once, one review fails, the series reports 1 of 2."""
    log = fake_providers(monkeypatch, match_home_page_only)

    assert auto(workspace, 2) == 1

    assert len(log["mapper"]) == 2
    assert len(log["matcher"]) == 6
    assert "llm-invented" in log["matcher"][1]

    mapping = workspace / "snapshots/human-finding-mapping/human-finding-mapping.json"
    assert json.loads(mapping.read_text())["approved_by"] == MAPPER

    (series,) = (workspace / ".model-evaluation/series").iterdir()
    record = json.loads((series / "series.json").read_text())
    assert record["model"]["model"] == MODEL
    assert record["reviewers"] == {"mapper": MAPPER, "matcher": MATCHER,
                                   "human_finding_mapping_approved_by": MAPPER}
    assert record["runs_requested"] == 2
    assert record["completed"] == 1
    assert record["snapshots"] == str((workspace / "snapshots/snapshots.json").resolve())
    assert record["human_finding_mapping"] == str(mapping.resolve())
    first, second = record["runs"]
    assert first["status"] == "complete"
    assert first["counts"]["llm"] == {"caught": 1, "eligible": 2}
    assert first["counts"]["overall"] == {"caught": 2, "eligible": 3}
    assert second["status"] == "incomplete"
    assert "review failed" in second["reason"]
    assert (series / "runs" / first["run_id"] / "report.html").is_file()
    assert not (series / "runs" / second["run_id"] / "report.html").exists()

    cost = record["cost_by_role"]
    assert cost["mapper"]["estimated_cost_usd"] == "0.004"
    assert cost["matcher"]["estimated_cost_usd"] == "0.012"
    assert Decimal(cost["model"]["estimated_cost_usd"]) == Decimal("0.0005") * len(log["audit"])
    assert cost["matcher"]["usage"]["input_tokens"] == 60_000

    report = (series / "report.html").read_text()
    assert "1 of 2 runs completed" in report
    assert "50.0%" in report and "66.7%" in report
    catches = dict(re.findall(r'<th scope="row">(\w+ defect)</th><td>[^<]*</td><td>(\d/\d)</td>',
                              report))
    assert catches == {"Home defect": "1/1", "Contact defect": "0/1", "Shared defect": "1/1"}
    assert "$0.012" in report and MATCHER in report
    assert "1 of 2 runs completed" in capsys.readouterr().out

    # A second series on the same snapshots reuses the saved mapping.
    log["mapper"].clear()
    assert auto(workspace, 1) == 0
    assert not log["mapper"]
