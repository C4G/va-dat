"""End-to-end checks of review-report-auto, with fake models and no network."""

import json
import re
from types import SimpleNamespace

import pytest

from tests.test_evaluation_workflow import (  # noqa: F401  (workspace is a fixture)
    MODEL,
    approve_mapping,
    fake_model,
    read_csv,
    run_all,
    workspace,
)
from vision_aid.evaluation.cli import main

ATTRIBUTION = f"{MODEL}/medium/matcher_v1"


def fake_matcher(monkeypatch, answers):
    """Answer audit prompts as fake_model does and matcher prompts with `answers`.

    `answers(prompt, attempt)` returns the matcher's response object. Matcher
    requests are the ones that ask for a JSON-schema response. Each matcher
    request reports 10,000 input and 2,000 output tokens ($0.002 on Luna).
    """
    audit = fake_model(monkeypatch)
    matcher = []

    def create(**kwargs):
        """Return a Chat Completions-shaped response."""
        if "response_format" not in kwargs:
            audit.append(kwargs)
            content, usage = '{"issues": ["Fake issue"]}', (0, 0)
        else:
            matcher.append(kwargs)
            prompt = kwargs["messages"][0]["content"]
            content, usage = json.dumps(answers(prompt, len(matcher))), (10_000, 2_000)
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
    return matcher


def match_first_row(prompt, _attempt):
    """Match the page's first Human finding to its first LLM finding."""
    humans = list(dict.fromkeys(re.findall(r'"human_finding_id": "(human-\w+)"', prompt)))
    llm = list(dict.fromkeys(re.findall(r'"finding_id": "(llm-\w+)"', prompt)))
    return {"decisions": [
        {"human_finding_id": human,
         "llm_finding_ids": [llm[0]] if number == 0 else [],
         "match_reason": "Same image problem" if number == 0 else "",
         "review_notes": ""}
        for number, human in enumerate(humans)
    ]}


def live_run(workspace, monkeypatch, answers):
    """Run run-all live with fake models and return the matcher log and run folder."""
    mapping = approve_mapping(workspace)
    matcher = fake_matcher(monkeypatch, answers)
    code, run, manifest = run_all(workspace, mapping, "--max-cost-usd", "1",
                                  "--live", "--approve-live")
    assert code == 0 and manifest["complete"]
    return matcher, run, [run / page["run_dir"] for page in manifest["pages"]]


def review_report_auto(run):
    """Run review-report-auto with Luna as the matcher."""
    return main(["review-report-auto", "--run-dir", str(run), "--matcher-model", MODEL,
                 "--max-cost-usd", "1", "--approve-live"])


def test_full_evaluation_is_reviewed_and_reported(workspace, monkeypatch, capsys):
    """The matcher fills every page's review.csv and report-all's reports follow."""
    matcher, run, pages = live_run(workspace, monkeypatch, match_first_row)

    assert review_report_auto(run) == 0

    assert len(matcher) == 2
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


def test_invalid_response_is_retried_with_the_error(workspace, monkeypatch):
    """An unknown finding ID is sent back once, and the corrected answer is used."""
    def answers(prompt, attempt):
        """Invent an ID on the first request, then answer properly."""
        if attempt == 1:
            decided = match_first_row(prompt, attempt)
            decided["decisions"][0]["llm_finding_ids"] = ["llm-invented"]
            return decided
        return match_first_row(prompt, attempt)

    matcher, run, _ = live_run(workspace, monkeypatch, answers)

    assert review_report_auto(run) == 0
    assert len(matcher) == 3
    assert "llm-invented" in matcher[1]["messages"][0]["content"]
    assert (run / "report.html").is_file()
    record = json.loads((run / "automated-review.json").read_text())
    assert record["estimated_cost_usd"] == "0.006"


def test_double_failure_writes_nothing(workspace, monkeypatch, capsys):
    """Two bad answers for one page leave every review.csv and report untouched."""
    def answers(prompt, attempt):
        """Answer the first page properly; leave a row out on the second page."""
        decided = match_first_row(prompt, attempt)
        if "example.test/contact/" in prompt:
            decided["decisions"].pop()
        return decided

    matcher, run, pages = live_run(workspace, monkeypatch, answers)
    before = {page: (page / "review.csv").read_bytes() for page in pages}

    assert review_report_auto(run) == 1

    assert len(matcher) == 3
    assert "review failed" in capsys.readouterr().out.lower()
    assert not (run / "report.html").exists()
    for page in pages:
        assert (page / "review.csv").read_bytes() == before[page]
        assert not (page / "report.html").exists()
    record = json.loads((run / "automated-review.json").read_text())
    assert record["status"] == "failed"
    assert record["estimated_cost_usd"] == "0.006"


def test_preview_is_refused_before_any_request(workspace, monkeypatch, capsys):
    """A preview run has nothing to review, so no matcher request is sent."""
    _, run, _ = run_all(workspace, approve_mapping(workspace), "--max-cost-usd", "1")
    matcher = fake_matcher(monkeypatch, match_first_row)
    with pytest.raises(SystemExit):
        review_report_auto(run)
    assert "Incomplete" in capsys.readouterr().err
    assert not matcher
