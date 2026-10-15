"""Run, review, and report Evaluation runs through the public CLI."""

import csv
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
from bs4 import BeautifulSoup

from processing_scripts.llm.registry import PROMPT_REGISTRY
from vision_aid.evaluation import llm_audit
from vision_aid.evaluation.cli import main

MODELS = (
    "claude-haiku-5-5", "claude-opus-5-5", "claude-sonnet-5-5",
    "gpt-6-luna", "gpt-6.1-sol",
)
CATEGORIES = [spec.name for spec in PROMPT_REGISTRY if not spec.is_summary]
RUN_ROOT = {"review.csv", "snapshot.html", "normalized-programmatic-findings.json",
            "run.json", "artifacts"}
REVIEWER = "Test reviewer"
# Synthetic markup that activates every non-summary prompt category.
HTML = (
    '<html lang="en"><head><title>Home</title></head><body>'
    '<header><nav><a href="/">Click here</a></nav></header><main><h1>Home</h1>'
    "<h3>News</h3><table><tr><th>Year</th></tr><tr><td>2026</td></tr></table>"
    '<iframe src="/v" title="Video"></iframe><form><label for="n">Name</label>'
    '<input id="n" required aria-describedby="h"><p id="h">Full name</p>'
    '<input placeholder="Email"><fieldset><legend>Plan</legend>'
    '<input type="radio" id="p" name="p"><label for="p">Basic</label></fieldset>'
    '</form><img src="team.png" alt="Team"><img src="line.png" alt="">'
    '<a href="/d"><img src="d.png" alt="Donate"></a>'
    '<img src="sales-chart.png" alt="Sales"><svg role="img"><title>Logo</title></svg>'
    '<i class="fa fa-star"></i><video src="v.mp4" controls></video></main>'
    "<footer>Footer</footer></body></html>"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a Human audit and Benchmark snapshot with credentials available."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Defect report"
    sheet.append([
        "Sr. #", "element name", "Browser Combination", "Page name", "Issue Title",
        "Steps to Reproduce", "actual result", "expected result",
        "Recommendation for Fix", "WCAG Sc", "Type of Change", "comment",
    ])
    sheet.append([1, "First link", "Chrome", "Home", "Unclear link", "Open page",
                  "Vague link\nfor everyone", "Descriptive", "Rename", "2.4.4", "Code", ""])
    for number, title, wcag in (
        (2, "Missing destination", "2.4.4"), (3, "Skipped heading", "1.3.1"),
        (4, "Hidden menu", "2.1.1"), (5, "Unclear claim", "4.1.2"),
        (6, "No captions", "1.2.2"),
    ):
        sheet.append([number, "Element", "Chrome", "Global", title, "", "", "", "", wcag])
    sheet.append([7, "Other", "Chrome", "Careers", "Outside scope"])
    book.save(tmp_path / "human-audit.xlsx")
    (tmp_path / "home.html").write_text(HTML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    return tmp_path


def run_cli(workspace: Path, *extra: str) -> int:
    """Invoke the public run command for the synthetic inputs."""
    return main([
        "run", "--human-audit", str(workspace / "human-audit.xlsx"),
        "--html", str(workspace / "home.html"),
        "--source-url", "https://example.test/", "--max-cost-usd", "1", *extra,
    ])


def report(run: Path) -> str:
    """Score a reviewed run and return readable HTML text."""
    assert main(["report", "--run-dir", str(run), "--reviewer", REVIEWER]) == 0
    return BeautifulSoup((run / "report.html").read_text(encoding="utf-8"), "html.parser").get_text(" ", strip=True)


def refused(run: Path, capsys: pytest.CaptureFixture[str], reviewer: str = REVIEWER) -> str:
    """Assert reporting fails without writing a report, returning the error."""
    with pytest.raises(SystemExit) as error:
        main(["report", "--run-dir", str(run), "--reviewer", reviewer])
    assert error.value.code == 2
    assert not (run / "report.html").exists()
    return capsys.readouterr().err


def only_run(workspace: Path) -> Path:
    """Find the single run created under the workspace."""
    (run,) = (workspace / ".model-evaluation" / "runs").iterdir()
    return run


def load(run: Path, name: str):
    """Read one saved JSON artifact."""
    return json.loads((run / name).read_text())


def edit_review(run: Path, *decisions: dict[str, str]) -> None:
    """Apply reviewer decisions to review.csv rows in Human audit order."""
    path = run / "review.csv"
    with path.open(newline="") as stream:
        rows = sorted(csv.DictReader(stream), key=lambda row: int(row["source_row"]))
    for row, decision in zip(rows, decisions):
        row.update(decision)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(reversed(rows))


def fake_client(monkeypatch: pytest.MonkeyPatch, *responses: dict) -> list[str]:
    """Replace the request client, replaying responses and recording prompts."""
    prompts: list[str] = []
    default = {"success": True, "response": '[{"issues": ["Vague link"]}]',
               "usage": {"input_tokens": 1, "output_tokens": 1}}

    def call(prompt: str) -> dict:
        """Return the next scripted response."""
        prompts.append(prompt)
        return responses[len(prompts) - 1] if len(prompts) <= len(responses) else default

    monkeypatch.setattr(llm_audit, "LLMRequestClient",
                        lambda **_: SimpleNamespace(call=call))
    return prompts


def recording_provider_usage(monkeypatch, model, *usages, stream_failure_at=None):
    """Replay SDK usage payloads, then zero usage, through the public CLI."""
    requests = []
    text = '{"issues": ["Synthetic failure"]}'

    def create(**kwargs):
        """Return a Chat Completion or streamed Message with supplied usage."""
        index = len(requests)
        requests.append(kwargs)
        usage = usages[index] if index < len(usages) else {}
        if model.startswith("gpt-"):
            return SimpleNamespace(
                id="synthetic-price", model=model,
                choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
                usage=SimpleNamespace(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
                    prompt_tokens_details=usage.get("prompt_tokens_details"),
                    completion_tokens_details=usage.get("completion_tokens_details"),
                ),
            )

        def events():
            """Expose reported usage before optional transport failure."""
            yield SimpleNamespace(type="message_start", message=SimpleNamespace(
                id="synthetic-price", model=model, type="message", usage=SimpleNamespace(
                    input_tokens=usage.get("input_tokens", 0), output_tokens=0,
                    cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
                    cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                )))
            yield SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(
                type="text", text=text))
            yield SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"),
                                  usage=SimpleNamespace(output_tokens=usage.get("output_tokens", 0)))
            if index == stream_failure_at:
                raise TimeoutError("synthetic stream failure")
            yield SimpleNamespace(type="message_stop")

        return nullcontext(events())

    if model.startswith("gpt-"):
        monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
        monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("wrong provider"))
        monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    else:
        monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("wrong provider"))
        monkeypatch.setattr("anthropic.Anthropic", lambda **_: SimpleNamespace(
            messages=SimpleNamespace(create=create)))
    return requests


@pytest.mark.parametrize("model", [None, *MODELS])
def test_preview_preserves_evidence_without_provider_access(workspace, monkeypatch, capsys, model):
    """Credentials alone never buy requests, and all homepage rows survive."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("provider access"))
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("provider access"))
    assert run_cli(workspace, *(["--model", model] if model else [])) == 0
    run = only_run(workspace)
    assert {path.name for path in run.iterdir()} == RUN_ROOT
    assert {path.name for path in (run / "artifacts").iterdir()} == {
        "human-findings.json", "pricing.json", "raw-programmatic-findings.json",
        "prompts", "payloads",
    }
    manifest = load(run, "run.json")
    selected = model or MODELS[0]
    config = manifest["configuration"]
    assert config["model"] == selected
    provider, endpoint = (("openai", "chat.completions") if selected.startswith("gpt-")
                          else ("anthropic", "messages"))
    assert (config["provider"], config["endpoint"]) == (provider, endpoint)
    assert config["temperature"] == "omitted" and config["summaries"] == "disabled"
    assert config["max_output_tokens"] == 24192
    output = capsys.readouterr().out
    assert f"provider: {provider}; endpoint: {endpoint}" in output
    assert "Cost guardrail: $1" in output
    assert config["reasoning_effort"] == "medium"
    if selected.startswith("gpt-"):
        assert "thinking" not in config
        assert "thinking: none" in output
    else:
        assert config["thinking"]["type"] == "adaptive"
    assert manifest["complete"] is False and manifest["incomplete_reason"] == "preview"
    assert len(CATEGORIES) == 18
    assert [prompt["name"] for prompt in manifest["prompts"]] == CATEGORIES
    assert (run / "snapshot.html").read_text(encoding="utf-8", errors="replace") == HTML
    audit = workspace / "human-audit.xlsx"
    assert manifest["human_audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
    assert manifest["snapshot_sha256"] == hashlib.sha256(HTML.encode()).hexdigest()
    raw = load(run, "artifacts/raw-programmatic-findings.json")
    normalized = load(run, "normalized-programmatic-findings.json")
    assert raw and [item["raw_source"] for item in normalized] == raw
    assert all(item["run_id"] == run.name for item in normalized)
    with (run / "review.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["source_row"] for row in rows] == ["2", "3", "4", "5", "6", "7"]
    assert rows[0]["actual result"] == "Vague link\nfor everyone"
    assert all(not row["classification"] for row in rows)


@pytest.mark.parametrize("model", MODELS)
def test_live_run_without_approval_or_with_unsupported_model_buys_nothing(
    workspace, monkeypatch, capsys, model,
):
    """Declined approval prepares a preview; invalid models create no run."""
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("paid call"))
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("paid call"))
    with pytest.raises(SystemExit) as error:
        run_cli(workspace, "--model", "gpt-4o", "--live", "--approve-live")
    assert error.value.code == 2 and "invalid choice" in capsys.readouterr().err
    assert not (workspace / ".model-evaluation").exists()
    monkeypatch.setattr("builtins.input", lambda _: "no")
    for interactive in (False, True):
        monkeypatch.setattr(
            "sys.stdin", SimpleNamespace(isatty=lambda interactive=interactive: interactive),
        )
        assert run_cli(workspace, "--model", model, "--live") == 0
    runs = list((workspace / ".model-evaluation" / "runs").iterdir())
    assert len(runs) == 2
    for run in runs:
        assert load(run, "run.json")["incomplete_reason"] == "preview"
        assert not (run / "artifacts" / "raw-llm-responses.json").exists()


@pytest.mark.parametrize("model,thinking,effort,cost", [
    (MODELS[0], {"type": "adaptive"}, "medium", "0.003915"),
    (MODELS[1], {"type": "adaptive"}, "medium", "0.1548"),
    (MODELS[2], {"type": "adaptive"}, "medium", "0.0783"),
])
def test_presets_stream_every_category_and_report_saved_prices(
    workspace, monkeypatch, model, thinking, effort, cost,
):
    """Each preset's request settings, final text, model, and costs persist."""
    requests, options = [], []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("wrong provider"))

    def create(**kwargs):
        """Stream thinking, then final text, with cache usage."""
        requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=1,
                                cache_read_input_tokens=500, cache_creation_input_tokens=100)
        return nullcontext(iter([
            SimpleNamespace(type="message_start", message=SimpleNamespace(
                id="synthetic", model=model, type="message", usage=usage)),
            SimpleNamespace(type="content_block_start",
                            content_block=SimpleNamespace(type="thinking", thinking="SECRET")),
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(
                type="text", text='[{"issues": ["Synthetic failure"], "location_hint": "body"}]')),
            SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"),
                            usage=SimpleNamespace(output_tokens=200)),
            SimpleNamespace(type="message_stop"),
        ]))

    def client(**kwargs):
        """Record client options and expose the fake Messages API."""
        options.append(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    monkeypatch.setattr("anthropic.Anthropic", client)
    assert run_cli(workspace, "--model", model, "--live", "--approve-live") == 0
    assert options == [{"api_key": "synthetic", "max_retries": 0}]
    assert len(requests) == len(CATEGORIES)
    for request in requests:
        assert request["model"] == model and request["thinking"] == thinking
        assert request["max_tokens"] == 24192 and request["stream"] is True
        assert "temperature" not in request
        assert request.get("output_config") == ({"effort": effort} if effort else None)
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True and manifest["estimated_cost_usd"] == cost
    assert manifest["configuration"]["reasoning_effort"] == effort
    raw = load(run, "artifacts/raw-llm-responses.json")
    assert all(item["result"]["provider"]["response_model"] == model for item in raw)
    assert "SECRET" not in json.dumps(raw)
    assert manifest["format_failures"] == [
        "page_title", "heading_structure", "landmark_structure",
    ]
    findings = load(run, "normalized-llm-findings.json")
    assert [finding["prompt"] for finding in findings] == [
        "table_semantics", "placeholder_as_label", "group_labels",
        "required_field_indicators", "form_instructions", "informative_alt_quality",
        "actionable_image_alt", "complex_descriptions", "svg_accessibility",
        "icon_font_accessibility", "media_captions",
    ]
    assert all(finding["model"] == model for finding in findings)
    assert all(finding["problem"] == "Synthetic failure" for finding in findings)
    assert all(finding["finding_id"].startswith("llm-") for finding in findings)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    text = report(run)
    assert model in text and run.name in text
    assert "published prices captured on 2026-10-09" in text
    assert "18000 input tokens" in text and "3600 output tokens" in text
    assert "9000 cached input tokens" in text and "1800 cache-creation input tokens" in text


@pytest.mark.parametrize("model,cost", [("gpt-6-luna", "0.0036"), ("gpt-6.1-sol", "0.072")])
def test_gpt_presets_use_openai_key_and_save_response_identity(
    workspace, monkeypatch, model, cost,
):
    """GPT requests use the selected preset and preserve provider evidence for review."""
    requests, options = [], []
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("wrong provider"))

    def create(**kwargs):
        """Return final text and reported usage through Chat Completions."""
        requests.append(kwargs)
        return SimpleNamespace(
            id="synthetic-gpt", model=f"{model}-provider", service_tier="default",
            system_fingerprint="synthetic-fingerprint",
            choices=[SimpleNamespace(message=SimpleNamespace(
                content='[{"issues": ["Synthetic failure"], "location_hint": "body"}]'),
                finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=200,
                                  total_tokens=1200, prompt_tokens_details=None,
                                  completion_tokens_details=SimpleNamespace(reasoning_tokens=150)),
        )

    def client(**kwargs):
        """Record the SDK credentials and expose the provider request boundary."""
        options.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr("openai.OpenAI", client)
    assert run_cli(workspace, "--model", model, "--live", "--approve-live") == 0
    assert options == [{"api_key": "synthetic-openai", "max_retries": 0}]
    assert len(requests) == len(CATEGORIES)
    for request in requests:
        assert request["model"] == model
        assert request["reasoning_effort"] == "medium"
        assert request["max_completion_tokens"] == 24192
        assert set(request) == {"model", "messages", "reasoning_effort", "max_completion_tokens"}
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True and manifest["estimated_cost_usd"] == cost
    raw = load(run, "artifacts/raw-llm-responses.json")
    for item in raw:
        result = item["result"]
        assert result["model"] == f"{model}-provider"
        assert result["provider"]["response_id"] == "synthetic-gpt"
        assert result["provider"]["response_model"] == f"{model}-provider"
        assert result["usage"]["provider_usage"]["completion_tokens_details"] == {"reasoning_tokens": 150}
        assert result["usage"]["output_tokens"] == 200
        assert result["request"]["reasoning_effort"] == "medium"
        assert "thinking" not in result["request"]
    findings = load(run, "normalized-llm-findings.json")
    assert findings and all(item["model"] == model for item in findings)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    text = report(run)
    assert model in text and "18000 input tokens" in text and "3600 output tokens" in text


def test_run_help_explains_presets_and_provider_credentials(capsys):
    """Operators can discover request settings and the relevant credentials in help."""
    with pytest.raises(SystemExit) as error:
        main(["run", "--help"])
    assert error.value.code == 0
    text = capsys.readouterr().out
    assert all(model in text for model in MODELS)
    assert "Haiku 5.5 (default)" in text
    assert "adaptive" in text and "medium" in text
    assert "24,192" in text and "temperature" in text and "summaries" in text
    assert "Chat Completions" in text
    assert "OPENAI_API_KEY" in text and "ANTHROPIC_API_KEY" in text


@pytest.mark.parametrize("model,threshold,low,high,source", [
    ("gpt-6-luna", 272000, ("0.10", "0.50", "0.01", "0.125"),
     ("0.20", "0.75", "0.02", "0.25"), "https://developers.openai.com/api/docs/pricing"),
    ("gpt-6.1-sol", 272000, ("2.00", "10.00", "0.10", "2.50"),
     ("4.00", "15.00", "0.20", "5.00"), "https://developers.openai.com/api/docs/pricing"),
    ("claude-haiku-5-5", 100000, ("0.10", "0.50", "0.01", "0.125"),
     ("0.50", "2.50", "0.05", "0.625"),
     "https://platform.claude.com/docs/en/about-claude/pricing"),
])
def test_preview_saves_and_displays_both_request_price_tiers(
    workspace, monkeypatch, capsys, model, threshold, low, high, source,
):
    """Key-free previews expose the recorded rates applicable to each request."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("provider access"))
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("provider access"))
    assert run_cli(workspace, "--model", model) == 0
    run = only_run(workspace)
    schedule = load(run, "artifacts/pricing.json")
    assert schedule["captured_at"] == "2026-10-09"
    assert schedule["version"] == "public-standard-2026-10-09"
    assert source in schedule["sources"]
    manifest = load(run, "run.json")
    assert manifest["pricing_sha256"] == hashlib.sha256(
        (run / "artifacts/pricing.json").read_bytes()
    ).hexdigest()
    output = capsys.readouterr().out
    assert f"up to {threshold:,} total input tokens per request" in output
    assert f"above {threshold:,} total input tokens per request" in output
    cache_write = "5-minute cache write" if model.startswith("claude-") else "cache write"
    for input_rate, output_rate, read_rate, write_rate in (low, high):
        assert (f"input ${input_rate}; output ${output_rate}; "
                f"cache read ${read_rate}; {cache_write} ${write_rate}") in output
    if model.startswith("gpt-"):
        assert "5-minute" not in output


@pytest.mark.parametrize("model,cost", [("gpt-6-luna", "0.0002345"), ("gpt-6.1-sol", "0.00467")])
def test_openai_prices_cached_subsets_and_reasoning_once(workspace, monkeypatch, model, cost):
    """Cache reads/writes replace ordinary input; output already includes reasoning."""
    details = SimpleNamespace(cached_tokens=200, cache_write_tokens=100)
    requests = recording_provider_usage(monkeypatch, model, {
        "prompt_tokens": 1000, "completion_tokens": 300, "prompt_tokens_details": details,
        "completion_tokens_details": SimpleNamespace(reasoning_tokens=250),
    })
    assert run_cli(workspace, "--model", model, "--live", "--approve-live") == 0
    assert len(requests) == len(CATEGORIES)
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["estimated_cost_usd"] == cost
    # Aggregate reported usage and raw provider evidence retain their existing meaning.
    assert manifest["usage"] == {"input_tokens": 1000, "cached_input_tokens": 200,
                                 "cache_creation_input_tokens": 0, "output_tokens": 300}
    (first, *rest) = load(run, "artifacts/raw-llm-responses.json")
    assert first["result"]["usage"]["provider_usage"]["prompt_tokens_details"] == {
        "cached_tokens": 200, "cache_write_tokens": 100,
    }
    assert first["result"]["usage"]["provider_usage"]["completion_tokens_details"] == {
        "reasoning_tokens": 250,
    }
    assert first["billable_usage"] == {"input_tokens": 700, "cached_input_tokens": 200,
                                       "cache_creation_input_tokens": 100, "output_tokens": 300}
    assert first["estimated_cost_usd"] == cost
    assert all(item["estimated_cost_usd"] == "0" for item in rest)


@pytest.mark.parametrize("model,threshold,costs,total", [
    ("gpt-6-luna", 272000, ["0.0271895", "0.0543767"], "0.0815662"),
    ("gpt-6.1-sol", 272000, ["0.54377", "1.087494"], "1.631264"),
    ("claude-haiku-5-5", 100000, ["0.0099895", "0.049948"], "0.0599375"),
])
def test_each_request_uses_total_input_and_inclusive_price_threshold(
    workspace, monkeypatch, model, threshold, costs, total,
):
    """Equality gets the lower tier; one extra token prices the whole request higher."""
    if model.startswith("gpt-"):
        usages = [{"prompt_tokens": size, "completion_tokens": 10,
                   "prompt_tokens_details": SimpleNamespace(cached_tokens=200, cache_write_tokens=100)}
                  for size in (threshold, threshold + 1)]
    else:
        usages = [{"input_tokens": size - 300, "output_tokens": 10,
                   "cache_read_input_tokens": 200, "cache_creation_input_tokens": 100}
                  for size in (threshold, threshold + 1)]
    requests = recording_provider_usage(monkeypatch, model, *usages)
    assert run_cli(workspace, "--model", model, "--max-cost-usd", "10",
                   "--live", "--approve-live") == 0
    assert len(requests) == len(CATEGORIES)
    run = only_run(workspace)
    assert load(run, "run.json")["estimated_cost_usd"] == total
    raw = load(run, "artifacts/raw-llm-responses.json")
    assert [item["estimated_cost_usd"] for item in raw[:2]] == costs
    assert [item["billable_usage"]["input_tokens"] for item in raw[:2]] == [threshold - 300, threshold - 299]
    assert all(item["estimated_cost_usd"] == "0" for item in raw[2:])


@pytest.mark.parametrize("limited", [False, True])
@pytest.mark.parametrize("model,short_size,long_size,costs,total,partial,guardrail", [
    ("gpt-6-luna", 136001, 272001,
     ["0.0136051", "0.0136051", "0.0544077", "0.000015"], "0.0816329", "0.0816179", "0.03"),
    ("gpt-6.1-sol", 136001, 272001,
     ["0.272102", "0.272102", "1.088154", "0.0003"], "1.632658", "1.632358", "0.6"),
    ("claude-haiku-5-5", 50001, 100001,
     ["0.0050051", "0.0050051", "0.0500255", "0.000015"], "0.0600507", "0.0600357", "0.012"),
])
def test_mixed_request_sizes_accumulate_cost_and_drive_guardrail(
    workspace, monkeypatch, model, short_size, long_size, costs, total, partial, guardrail, limited,
):
    """Combined short input never triggers long rates or stops execution early."""
    input_key, output_key = (("prompt_tokens", "completion_tokens") if model.startswith("gpt-")
                             else ("input_tokens", "output_tokens"))
    usages = [{input_key: size, output_key: 10} for size in (short_size, short_size, long_size, 100)]
    requests = recording_provider_usage(monkeypatch, model, *usages)
    assert run_cli(workspace, "--model", model, "--max-cost-usd", guardrail if limited else "10",
                   "--live", "--approve-live") == (1 if limited else 0)
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["estimated_cost_usd"] == (partial if limited else total)
    assert len(requests) == (3 if limited else len(CATEGORIES))
    assert manifest["incomplete_reason"] == ("cost guardrail exhausted" if limited else None)
    raw = load(run, "artifacts/raw-llm-responses.json")
    assert [item["estimated_cost_usd"] for item in raw[:4]] == (costs[:3] if limited else costs)
    assert manifest["usage"]["input_tokens"] == short_size * 2 + long_size + (0 if limited else 100)
    assert manifest["usage"]["output_tokens"] == (30 if limited else 40)
    assert load(run, "normalized-llm-findings.json")


def test_stream_failure_retains_observed_tiered_cost_and_partial_usage(workspace, monkeypatch, capsys):
    """A failed stream still contributes observed input, caches, and output to cost."""
    model = "claude-haiku-5-5"
    requests = recording_provider_usage(monkeypatch, model,
        {"input_tokens": 1000, "output_tokens": 10},
        {"input_tokens": 99701, "cache_read_input_tokens": 200,
         "cache_creation_input_tokens": 100, "output_tokens": 10},
        stream_failure_at=1,
    )
    assert run_cli(workspace, "--model", model, "--live", "--approve-live") == 1
    assert len(requests) == 2
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["incomplete_reason"] == "synthetic stream failure"
    assert manifest["estimated_cost_usd"] == "0.050053"
    assert manifest["usage"] == {"input_tokens": 100701, "cached_input_tokens": 200,
                                 "cache_creation_input_tokens": 100, "output_tokens": 20}
    raw = load(run, "artifacts/raw-llm-responses.json")
    assert [item["estimated_cost_usd"] for item in raw] == ["0.000105", "0.049948"]
    assert raw[1]["result"]["response"] == '{"issues": ["Synthetic failure"]}'
    assert raw[1]["result"]["failure"]["type"] == "TimeoutError"
    assert raw[1]["result"]["usage"]["provider_usage"] == {
        "input_tokens": 99701, "cache_read_input_tokens": 200,
        "cache_creation_input_tokens": 100, "output_tokens": 10,
    }
    assert len(load(run, "normalized-llm-findings.json")) == 1
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    assert "Incomplete" in refused(run, capsys)


def test_historical_reports_keep_saved_prices_and_stored_estimate(workspace, monkeypatch):
    """Saved evidence reports with its original prices and stored estimate."""
    response = {"success": True, "response": '{"issues": []}',
                "usage": {"input_tokens": 10000, "output_tokens": 1000}}
    fake_client(monkeypatch, *[response] * len(CATEGORIES))
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    # Turn the saved artifacts into a historical fixture with its original rates.
    schedule = {
        "version": "historical-public-2025-10-01", "published_at": "2025-10-01",
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "models": {MODELS[0]: {
            "input_per_million_usd": "20", "output_per_million_usd": "100",
            "cached_input_per_million_usd": "2", "cache_creation_input_per_million_usd": "25",
        }},
    }
    price_path = run / "artifacts/pricing.json"
    price_path.write_text(json.dumps(schedule))
    manifest = load(run, "run.json")
    manifest.update(pricing_version=schedule["version"],
                    pricing_sha256=hashlib.sha256(price_path.read_bytes()).hexdigest(),
                    estimated_cost_usd="5.4")
    (run / "run.json").write_text(json.dumps(manifest))
    raw = load(run, "artifacts/raw-llm-responses.json")
    for item in raw:
        item.pop("estimated_cost_usd")
        item.pop("billable_usage")
    (run / "artifacts/raw-llm-responses.json").write_text(json.dumps(raw))
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    originals = {path: path.read_bytes() for path in (price_path, run / "run.json",
                 run / "artifacts/raw-llm-responses.json")}
    text = report(run)
    assert "Estimated run cost: $5.40" in text
    assert "published prices dated 2025-10-01" in text
    assert "https://platform.claude.com/docs/en/about-claude/pricing" in text
    assert "180000 input tokens" in text and "18000 output tokens" in text
    assert all(path.read_bytes() == saved for path, saved in originals.items())


def test_report_describes_the_evaluated_page(workspace, monkeypatch):
    """A saved page's report identifies its URL without claiming homepage scope."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--source-url", "https://example.test/contact/",
                   "--live", "--approve-live") == 0
    run = only_run(workspace)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    text = report(run)
    assert "This evaluation covers the saved page at https://example.test/contact/" in text
    assert "homepage only" not in text


def test_review_validation_and_report_metrics(workspace, monkeypatch, capsys):
    """Known decisions yield hand-calculated rates, cross-catches, and exclusions."""
    fake_client(
        monkeypatch,
        {"success": True, "response": "not JSON", "usage": {}},
        {"success": True, "response": '{"issues": []}', "usage": {}},
        # The API reads the first fenced block and ignores trailing prose.
        {"success": True, "usage": {}, "response": (
            '```json\n[{"text": "Click here", "is_clear": false, "reason": "Fenced with a note"}]'
            '\n```\n\n**Note:** Context was limited.'
        )},
        {"success": True, "response": "[]", "usage": {}},
        {"success": True, "response": "[]", "usage": {}},
        {"success": True, "response": '{"issues": []}', "usage": {}},
    )
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True and manifest["format_failures"] == ["page_title"]
    findings = load(run, "normalized-llm-findings.json")
    assert findings[0]["problem"] == "Fenced with a note"
    llm = [item["finding_id"] for item in findings]
    assert len(llm) == 11
    programmatic = load(run, "normalized-programmatic-findings.json")[0]["finding_id"]
    assert "classification" in refused(run, capsys)
    decisions = [
        {"classification": "llm_eligible", "llm_finding_id": llm[0], "match_reason": "Full issue"},
        {"classification": "programmatic", "programmatic_finding_id": programmatic,
         "match_reason": "HTML check"},
        {"classification": "programmatic", "llm_finding_id": llm[1], "match_reason": "Cross-catch"},
        {"classification": "unavailable_evidence", "classification_reason": "Needs a browser",
         "llm_finding_id": "", "match_reason": ""},
        {"classification": "ambiguous", "classification_reason": "Needs judgment"},
        {"classification": "llm_eligible", "review_notes": "No full finding"},
    ]
    edit_review(run, *decisions)
    refused(run, capsys, reviewer=" ")
    edit_review(run, {"match_reason": ""})
    assert "needs a match reason" in refused(run, capsys)
    edit_review(run, {"llm_finding_id": programmatic, "match_reason": "Full issue"})
    assert "Unknown LLM finding ID" in refused(run, capsys)
    edit_review(run, *decisions[:3], {"llm_finding_id": llm[2], "match_reason": "Claimed"})
    assert "cannot claim coverage" in refused(run, capsys)
    edit_review(run, *decisions)
    text = report(run)
    assert ("Of the 2 Human findings the LLM could be expected to detect from the "
            "page's HTML, it caught 1 (50.0%)") in text
    assert "they caught 1 (50.0%)" in text
    assert "Of all 6 Human findings, either part of the tool caught 3 (50.0%)" in text
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    chart = document.find("figure", attrs={"aria-labelledby": "detection-chart-title"})
    assert chart is not None
    assert "LLM: 1 caught / 2 eligible; 50.0%" in chart.get_text(" ", strip=True)
    table = document.find("caption", string="Exact detection overview data").parent
    assert [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            for row in table.tbody.find_all("tr")] == [
        ["LLM", "1", "2", "50.0%", "Human findings expected to be detected by the LLM"],
        ["Programmatic", "1", "2", "50.0%", "Human findings expected to be detected by Programmatic checks"],
        ["Overall", "3", "6", "50.0%", "All imported Human findings, including findings Not testable from the page file"],
    ]
    assert document.find("caption", string="Exact page LLM detection data") is None
    rows = document.select("#findings tbody > tr")
    assert [cell.get_text(" ", strip=True) for cell in rows[2].find_all(["th", "td"], recursive=False)[:5]] == [
        "Skipped heading", "1.3.1", "Programmatic checks", "Caught", "Not caught",
    ]
    assert "Full issue" in rows[0].details.get_text()
    assert "No full finding" in rows[5].details.get_text()
    assert "Needs a browser" in rows[3].details.get_text()
    assert "Needs judgment" in rows[4].details.get_text()
    assert ("1 of 18 LLM checks returned an Unreadable response that the tool "
            "would skip: page title check.") in text
    assert llm[0] in text and llm[1] in text and programmatic in text
    assert llm[2] not in text
    edit_review(run, *[{"classification": "ambiguous", "llm_finding_id": "",
                        "programmatic_finding_id": "", "match_reason": ""}] * 6)
    text = report(run)
    assert "No Human findings were expected to be detected by the LLM" in text
    assert "No Human findings were expected to be detected by the Programmatic checks" in text
    assert "Of all 6 Human findings, either part of the tool caught 0 (0.0%)" in text


@pytest.mark.parametrize("failure,calls,cost,reason", [
    (True, 2, "0.02002", "synthetic failure"),
    (False, 1, "0.01001", "cost guardrail exhausted"),
])
def test_failure_or_exhaustion_stops_and_keeps_partial_evidence(
    workspace, monkeypatch, capsys, failure, calls, cost, reason,
):
    """Requests stop, billed usage and findings remain, and reporting refuses."""
    usage = {"input_tokens": 100000, "output_tokens": 20}
    success = {"success": True, "response": '{"issues": ["Unclear title"]}', "usage": usage}
    stopped = {"success": False, "response": None, "error": "synthetic failure", "usage": usage}
    prompts = fake_client(monkeypatch, success, stopped if failure else success)
    limit = "1" if failure else "0.01"
    assert run_cli(workspace, "--max-cost-usd", limit, "--live", "--approve-live") == 1
    assert len(prompts) == calls
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is False and manifest["incomplete_reason"] == reason
    assert manifest["usage"]["input_tokens"] == calls * 100000
    assert manifest["estimated_cost_usd"] == cost
    assert len(load(run, "artifacts/raw-llm-responses.json")) == calls
    assert len(load(run, "normalized-llm-findings.json")) == 1
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    assert "Incomplete" in refused(run, capsys)


@pytest.mark.parametrize("name,field,message", [
    ("run.json", "run_id", "does not belong"),
    ("normalized-llm-findings.json", "run_id", "do not belong"),
    ("normalized-programmatic-findings.json", "page_url", "do not belong"),
    ("artifacts/human-findings.json", "human_audit_sha256", "identity differs"),
    ("artifacts/pricing.json", None, "pricing.json"),
])
def test_report_rejects_unrelated_or_missing_evidence(
    workspace, monkeypatch, capsys, name, field, message,
):
    """Reports cannot combine evidence from different or partial runs."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    if field is None:
        (run / name).unlink()
    else:
        evidence = load(run, name)
        (evidence[0] if isinstance(evidence, list) else evidence)[field] = "unrelated"
        (run / name).write_text(json.dumps(evidence))
    assert message in refused(run, capsys)


def test_llm_findings_follow_the_tools_rules(workspace, monkeypatch):
    """Findings come from the tool's per-check rules, before filtering or deduplication."""
    def ok(response: object) -> dict:
        """Script one successful response as JSON text."""
        return {"success": True, "response": json.dumps(response), "usage": {}}

    fake_client(
        monkeypatch,
        ok({"is_descriptive": False, "issues": ["Title is generic"]}),
        ok({"structure_clear": False, "issues": ["Skips h2", "Two h1s", "No outline"],
            "vague_headings": ["News", "More"]}),
        # Kept although the tool's false-positive filter would drop it.
        ok([{"text": "Contact", "is_clear": False, "reason": "Ambiguous",
             "location_hint": "Footer"}, {"text": "Home", "is_clear": True}]),
        # The table prompt asks for one object, not a list.
        ok({"is_data_table": True, "caption_clear": False,
            "header_clarity_issues": ["Year is vague"], "issues": ["No caption"]}),
        # A list check answered with one object is unreadable.
        ok({"title": "Video", "is_descriptive": False}),
        # Text where a list belongs is unreadable, not one finding per character.
        ok({"structure_appropriate": False, "issues": "No main"}),
        ok([]),
        ok([{"field_id": None, "placeholder": "Email", "reason": "Placeholder only"}]),
        ok([{"legend_is_meaningful": False, "issues": []}]),
        ok([{"field_id": "n", "requirement_in_label": False,
             "requirement_in_instructions": False, "issues": []}]),
        ok([]),
        ok([{"src": "team.png", "alt": "Team", "quality": "poor",
             "issues": ["Too short", "Omits names"]}]),
        ok([]),
        ok([]),
        ok([]),
        ok([{"has_accessible_name": False, "issues": [],
             "reason": "No 1.1.1 failure; presentational"}]),
        ok([]),
        ok([{"src": "v.mp4", "has_captions_track": False, "issues": []},
            {"src": "v.mp4", "has_captions_track": False, "issues": ["No captions track"]}]),
    )
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    manifest = load(run, "run.json")
    assert manifest["complete"] is True
    assert manifest["format_failures"] == ["iframe_titles", "landmark_structure"]
    findings = load(run, "normalized-llm-findings.json")
    assert [(item["prompt"], item["problem"]) for item in findings] == [
        ("page_title", "Title is generic"),
        ("heading_structure", "Skips h2"),
        ("heading_structure", "Two h1s"),
        ("heading_structure", "No outline"),
        ("heading_structure", 'Heading "News" is vague or unclear'),
        ("heading_structure", 'Heading "More" is vague or unclear'),
        ("link_clarity", "Ambiguous"),
        ("table_semantics", "No caption; Year is vague"),
        ("placeholder_as_label", "Placeholder only"),
        ("informative_alt_quality", "Too short; Omits names"),
        ("media_captions", "No captions track"),
    ]
    assert len({item["finding_id"] for item in findings}) == len(findings)
    screen_only = [item["prompt"] for item in findings if item["screen_only"]]
    assert screen_only == ["table_semantics", "placeholder_as_label", "media_captions"]
    link = findings[6]
    assert (link["element"], link["location"]) == ('<a> "Contact"', "Footer")
    assert link["raw_source"]["text"] == "Contact" and link["wcag_evidence"] == ["2.4.4"]
    assert findings[7]["raw_source"]["issues"] == ["No caption"]
    vague = findings[4]["raw_source"]
    assert vague["issue"] == "News" and vague["response"]["vague_headings"] == ["News", "More"]
    media = findings[-1]
    assert media["raw_source"]["issues"] == ["No captions track"]
    edit_review(
        run, *[{"classification": "llm_eligible"}] * 5,
        {"classification": "llm_eligible", "llm_finding_id": media["finding_id"],
         "match_reason": "No captions on the video"},
    )
    text = report(run)
    assert ("LLM findings are read from each response with the tool's own rules, "
            "before its false-positive filter and deduplication.") in text
    assert ("LLM (media captions check; shown on screen only, not in the tool's "
            "CSV report): No captions track") in text


def test_single_page_report_is_standalone_html(workspace, monkeypatch, capsys):
    """A completed review produces readable offline HTML with native evidence controls."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    legacy = run / "report.md"
    legacy.write_text("Superseded report")
    assert main(["report", "--run-dir", str(run), "--reviewer", REVIEWER]) == 0
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    assert f"HTML report: {run / 'report.html'}" in capsys.readouterr().out
    assert not legacy.exists()
    assert document.html["lang"] == "en"
    assert document.title and document.h1
    assert document.select_one('a[href="#main"]') and document.main["id"] == "main"
    assert document.style and not document.select("script[src], link[rel=stylesheet], img[src]")
    table = document.find("table", attrs={"id": "findings"})
    assert table.caption and len(table.tbody.find_all("tr", recursive=False)) == 6
    assert [row.th.get_text(strip=True) for row in table.tbody.find_all("tr", recursive=False)] == [
        "Unclear link", "Missing destination", "Skipped heading", "Hidden menu", "Unclear claim", "No captions",
    ]
    disclosures = table.find_all("details")
    assert len(disclosures) == 6 and all(not item.has_attr("open") for item in disclosures)
    assert all("View evidence" in item.summary.get_text() for item in disclosures)
    assert "Vague link\nfor everyone" in document.get_text()


def test_report_embeds_canonical_and_complete_matching_evidence(workspace, monkeypatch):
    """Editable evidence cannot replace originals, and joint matches retain check provenance."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    findings = load(run, "normalized-llm-findings.json")
    hostile = '<script>alert("evidence")</script><img src=x onerror=alert(1)>'
    findings[0].update(problem=hostile, element="<a href='x'>", location="Footer", checklist="Synthetic checklist 42")
    (run / "normalized-llm-findings.json").write_text(json.dumps(findings))
    edit_review(run, {
        "classification": "llm_eligible", "llm_finding_id": ";".join(item["finding_id"] for item in findings[:2]),
        "match_reason": "Together they fully cover the link", "review_notes": hostile,
        "actual result": "Editable evidence replacement", "Issue Title": "Edited title",
    }, *[{"classification": "ambiguous"}] * 5)
    monkeypatch.setattr(llm_audit, "LLMRequestClient", lambda **_: pytest.fail("report made a paid request"))
    assert main(["report", "--run-dir", str(run), "--reviewer", hostile]) == 0
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    evidence = document.select_one("#findings tbody tr details")
    text = evidence.get_text(" ", strip=True)
    assert "Editable evidence replacement" not in text and "Edited title" not in text
    assert "Vague link\nfor everyone" in text and "Unclear link" in text
    assert hostile in text and not document.select("header script, #findings script, img, [onerror]")
    assert "Synthetic checklist 42" in text
    assert all(item["finding_id"] in text for item in findings[:2])
    assert "Together they fully cover the link" in text and "Footer" in text
    assert "<a href='x'>" in text and findings[0]["page_url"] in text


@pytest.mark.parametrize("missing", ["human_audit_filename", "configuration.model"])
def test_report_requires_complete_rendering_data(workspace, monkeypatch, capsys, missing):
    """Absent required fields cannot publish HTML or discard a legacy report."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    edit_review(run, *[{"classification": "llm_eligible"}] * 6)
    manifest = load(run, "run.json")
    if missing == "configuration.model":
        del manifest["configuration"]["model"]
    else:
        del manifest[missing]
    (run / "run.json").write_text(json.dumps(manifest))
    legacy = run / "report.md"
    legacy.write_text("Previous report")
    assert "Cannot render complete report" in refused(run, capsys)
    assert legacy.read_text() == "Previous report"
    assert not list(run.glob(".report.html.*.tmp"))


def test_report_with_no_human_findings_has_no_false_zero_rates(workspace, monkeypatch):
    """An empty saved review explains absent denominators in words."""
    fake_client(monkeypatch)
    assert run_cli(workspace, "--live", "--approve-live") == 0
    run = only_run(workspace)
    audit = load(run, "artifacts/human-findings.json")
    audit["human_findings"] = []
    (run / "artifacts/human-findings.json").write_text(json.dumps(audit))
    with (run / "review.csv").open() as stream:
        header = next(csv.reader(stream))
    with (run / "review.csv").open("w", newline="") as stream:
        csv.writer(stream).writerow(header)
    text = report(run)
    assert "No Human findings were imported for this page" in text
    assert "No Human findings were expected to be detected by the LLM" in text
    assert "No Human findings were expected to be detected by the Programmatic checks" in text
    assert "(0.0%)" not in text
    document = BeautifulSoup((run / "report.html").read_text(), "html.parser")
    table = document.find("caption", string="Exact detection overview data").parent
    assert [row.find_all("td")[2].get_text(strip=True) for row in table.tbody.find_all("tr")] == [
        "Not defined: no imported Human findings" if index == 2 else "Not defined: no eligible Human findings"
        for index in range(3)
    ]
    chart = document.find("figure", attrs={"aria-labelledby": "detection-chart-title"})
    assert "0.0%" not in chart.get_text(" ", strip=True)
    assert not document.select("#findings tbody tr")
