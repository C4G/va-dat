"""Execute Full evaluations through the CLI with controlled provider replies."""

import json

import pytest

from test_evaluation import recording_provider_usage
from test_full_preview import URLS, full_workspace, only_full, preview


def children(run, manifest):
    return [(run / page["run_dir"], json.loads((run / page["run_dir"] / "run.json").read_text()))
            for page in manifest["pages"]]


def test_declined_full_approval_makes_no_requests_after_showing_all_pages(
    full_workspace, monkeypatch, capsys,
):
    """One refusal covers the whole prepared scope, even with credentials present."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    approvals = []

    def decline(prompt):
        approvals.append(prompt)
        run, manifest = only_full(full_workspace)
        assert all((child / "review.csv").exists() for child, _ in children(run, manifest))
        displayed = capsys.readouterr().out
        assert all(url in displayed for url in URLS)
        assert "Pricing:" in displayed and "Cost guardrail: $2" in displayed
        return "no"

    monkeypatch.setattr("builtins.input", decline)
    assert preview(full_workspace, "--live") == 0
    assert len(approvals) == 1
    _, manifest = only_full(full_workspace)
    assert not manifest["complete"] and manifest["estimated_cost_usd"] == "0"
    assert "declined" in capsys.readouterr().out


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "gpt-6-luna"])
def test_one_approval_executes_ordered_pages_with_one_fixed_preset(
    full_workspace, monkeypatch, capsys, model,
):
    """Each child's requests use the approved model and evidence belongs to its page."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    requests = recording_provider_usage(monkeypatch, model)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    approvals = []

    def approve(prompt):
        assert not requests
        approvals.append(prompt)
        run, manifest = only_full(full_workspace)
        assert all((child / "snapshot.html").exists() for child, _ in children(run, manifest))
        return "yes"

    monkeypatch.setattr("builtins.input", approve)
    assert preview(full_workspace, "--live", "--model", model) == 0
    run, manifest = only_full(full_workspace)
    saved = children(run, manifest)
    assert len(approvals) == 1 and manifest["complete"]
    assert manifest["incomplete_reason"] is None
    assert len(requests) == sum(len(child["prompts"]) for _, child in saved) > 0
    assert all(request["model"] == model for request in requests)
    identities = set()
    for child, child_manifest in saved:
        assert child_manifest["complete"]
        assert child_manifest["configuration"] == manifest["configuration"]
        assert not (child / "report.md").exists()
        assert (child / "artifacts/raw-llm-responses.json").exists()
        for finding in json.loads((child / "normalized-llm-findings.json").read_text()):
            assert finding["page_url"] == child_manifest["source_url"]
            assert finding["run_id"] == child.name
            assert finding["finding_id"] not in identities
            identities.add(finding["finding_id"])
    assert "Full evaluation complete" in capsys.readouterr().out


def test_allowance_exhausted_between_pages_keeps_later_pages_unexecuted(
    full_workspace, monkeypatch,
):
    """Finishing one page consumes the single allowance rather than resetting it."""
    requests = recording_provider_usage(monkeypatch, "gpt-6-luna",
                                       {"completion_tokens": 1_000_000},
                                       {"completion_tokens": 1_000_000})
    assert preview(full_workspace, "--model", "gpt-6-luna", "--max-cost-usd", "1",
                   "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    assert len(requests) == 2
    assert not manifest["complete"] and "exhausted" in manifest["incomplete_reason"]
    assert manifest["estimated_cost_usd"] == "1"
    assert manifest["usage"]["output_tokens"] == 2_000_000
    assert [page["status"] for page in manifest["pages"]] == [
        "complete", "not_executed", "not_executed",
    ]
    assert [child["complete"] for _, child in children(run, manifest)] == [True, False, False]
    assert not (run / manifest["pages"][1]["run_dir"] / "normalized-llm-findings.json").exists()


def test_partial_page_consumes_only_remaining_allowance(full_workspace, monkeypatch):
    """A second page cannot repeat the first page's full spending allowance."""
    requests = recording_provider_usage(monkeypatch, "gpt-6-luna",
                                       *[{"completion_tokens": 500_000}] * 6)
    assert preview(full_workspace, "--model", "gpt-6-luna", "--max-cost-usd", "0.75",
                   "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    saved = children(run, manifest)
    assert len(requests) == 3
    assert manifest["estimated_cost_usd"] == "0.75"
    assert manifest["usage"]["output_tokens"] == 1_500_000
    assert [page["status"] for page in manifest["pages"]] == [
        "complete", "incomplete", "not_executed",
    ]
    assert saved[1][1]["max_cost_usd"] == "0.25"
    assert saved[1][1]["estimated_cost_usd"] == "0.25"
    assert saved[1][1]["incomplete_reason"] == "cost guardrail exhausted"
    assert len(json.loads((saved[1][0] / "artifacts/raw-llm-responses.json").read_text())) == 1


def test_failed_stream_usage_is_retained_and_later_pages_stop(full_workspace, monkeypatch):
    """A request failure retains reported usage and partial evidence alongside prior pages."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    requests = recording_provider_usage(
        monkeypatch, "claude-haiku-5-5",
        {"output_tokens": 1_000}, {"output_tokens": 1_000},
        {"input_tokens": 100, "output_tokens": 2_000}, stream_failure_at=2,
    )
    assert preview(full_workspace, "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    saved = children(run, manifest)
    assert len(requests) == 3
    assert manifest["estimated_cost_usd"] == "0.00201"
    assert manifest["usage"]["input_tokens"] == 100
    assert manifest["usage"]["output_tokens"] == 4_000
    assert "synthetic stream failure" in manifest["incomplete_reason"]
    assert [page["status"] for page in manifest["pages"]] == [
        "complete", "incomplete", "not_executed",
    ]
    assert saved[0][1]["complete"]
    assert (saved[0][0] / "normalized-llm-findings.json").exists()
    assert (saved[1][0] / "normalized-llm-findings.json").exists()
    raw = json.loads((saved[1][0] / "artifacts/raw-llm-responses.json").read_text())
    assert not raw[0]["result"]["success"]
    assert raw[0]["result"]["usage"]["output_tokens"] == 2_000


@pytest.mark.parametrize("last_request", [1, 5])
def test_overshoot_completes_only_when_no_more_work_remains(
    full_workspace, monkeypatch, last_request,
):
    """The underway request may overshoot; completion depends on remaining work."""
    usages = [{"completion_tokens": 0}] * last_request + [{"completion_tokens": 1_000_000}]
    requests = recording_provider_usage(monkeypatch, "gpt-6-luna", *usages)
    expected = last_request == 5
    assert preview(full_workspace, "--model", "gpt-6-luna", "--max-cost-usd", "0.1",
                   "--live", "--approve-live") == (0 if expected else 1)
    run, manifest = only_full(full_workspace)
    assert len(requests) == last_request + 1
    assert manifest["complete"] is expected
    assert manifest["estimated_cost_usd"] == "0.5"
    assert children(run, manifest)[0][1]["complete"]
    if expected:
        assert all(page["complete"] for page in manifest["pages"])
    else:
        assert "exhausted" in manifest["incomplete_reason"]


def test_fresh_full_attempt_repeats_requests_with_new_child_identities(
    full_workspace, monkeypatch,
):
    """Saved HTML is reused, while every new execution starts with fresh requests."""
    requests = recording_provider_usage(monkeypatch, "gpt-6-luna")
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    first, first_manifest = only_full(full_workspace)
    first_count = len(requests)
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    runs = list((full_workspace / ".model-evaluation/full-runs").iterdir())
    assert len(runs) == 2 and len(requests) == first_count * 2
    second = next(run for run in runs if run != first)
    second_manifest = json.loads((second / "full.json").read_text())
    assert {page["run_id"] for page in first_manifest["pages"]}.isdisjoint(
        page["run_id"] for page in second_manifest["pages"]
    )


def test_provider_initialization_failure_records_stopping_reason(full_workspace, monkeypatch):
    """Failed provider setup retains prepared evidence and identifies unfinished pages."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")

    def fail(**options):
        raise ValueError("synthetic provider initialization failure")

    monkeypatch.setattr("anthropic.Anthropic", fail)
    assert preview(full_workspace, "--live", "--approve-live") == 1
    run, manifest = only_full(full_workspace)
    assert manifest["estimated_cost_usd"] == "0"
    assert "synthetic provider initialization failure" in manifest["incomplete_reason"]
    assert [page["status"] for page in manifest["pages"]] == [
        "incomplete", "not_executed", "not_executed",
    ]
    assert "synthetic provider initialization failure" in children(run, manifest)[0][1]["incomplete_reason"]


def test_noninteractive_approval_requires_live_before_preparing(full_workspace, capsys):
    """An approval flag alone cannot create or authorize a Full evaluation."""
    with pytest.raises(SystemExit) as error:
        preview(full_workspace, "--approve-live")
    assert error.value.code == 2
    assert "--approve-live requires --live" in capsys.readouterr().err
    assert not (full_workspace / ".model-evaluation").exists()


@pytest.mark.parametrize("model,key", [
    ("gpt-6-luna", "OPENAI_API_KEY"), ("claude-haiku-5-5", "ANTHROPIC_API_KEY"),
])
def test_live_requires_the_selected_providers_credentials(
    full_workspace, monkeypatch, capsys, model, key,
):
    """The other provider's credentials cannot authorize this fixed preset."""
    monkeypatch.setenv("ANTHROPIC_API_KEY" if key == "OPENAI_API_KEY" else "OPENAI_API_KEY",
                       "synthetic-other-provider")
    with pytest.raises(SystemExit) as error:
        preview(full_workspace, "--model", model, "--live", "--approve-live")
    assert error.value.code == 2
    assert f"requires {key}" in capsys.readouterr().err
    run, manifest = only_full(full_workspace)
    assert not manifest["complete"]
    assert all((child / "review.csv").exists() for child, _ in children(run, manifest))


def test_parent_sums_all_reported_usage_categories(full_workspace, monkeypatch):
    """Cache usage remains a separate provider-reported category in parent totals."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    recording_provider_usage(monkeypatch, "claude-haiku-5-5", {
        "input_tokens": 100, "output_tokens": 1_000,
        "cache_read_input_tokens": 1_000, "cache_creation_input_tokens": 1_000,
    })
    assert preview(full_workspace, "--live", "--approve-live") == 0
    _, manifest = only_full(full_workspace)
    assert manifest["usage"] == {
        "input_tokens": 100, "output_tokens": 1_000,
        "cached_input_tokens": 1_000, "cache_creation_input_tokens": 1_000,
    }
    assert manifest["estimated_cost_usd"] == "0.000645"


def test_unreadable_successful_responses_preserve_execution_completion(
    full_workspace, monkeypatch,
):
    """Unreadable responses yield no findings while retaining current completion semantics."""
    from types import SimpleNamespace

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")

    def create(**options):
        return SimpleNamespace(
            id="synthetic-unreadable", model="gpt-6-luna",
            choices=[SimpleNamespace(message=SimpleNamespace(content="unreadable"),
                                     finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0,
                                  prompt_tokens_details=None, completion_tokens_details=None),
        )

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assert preview(full_workspace, "--model", "gpt-6-luna", "--live", "--approve-live") == 0
    run, manifest = only_full(full_workspace)
    assert manifest["complete"]
    for child, saved in children(run, manifest):
        assert saved["complete"] and len(saved["format_failures"]) == len(saved["prompts"])
        assert json.loads((child / "normalized-llm-findings.json").read_text()) == []
