"""Integration test: a live audit and report with the provider SDKs faked.

Everything from HTML extraction to the CSV report runs for real. Only the
Anthropic and OpenAI SDK clients are replaced, so no network calls are made
and no key is needed.
"""

from __future__ import annotations

import csv
import re
from types import SimpleNamespace

import anthropic
import openai
import pytest

from entry_points.generate_report import generate_report
from entry_points.run_pipeline import run_pipeline

PAGE = (
    "<html><head></head><body>"
    "<img src='a.png'><img src='b.png'>"
    "<a href='/x'></a><button></button>"
    "<form><input type='text'></form>"
    "</body></html>"
)

# Request fields that differ between the default request and a preset.
SHAPE_KEYS = ("temperature", "max_tokens", "max_completion_tokens", "reasoning_effort")

EXPECTED = {
    # No preset: the request the pipeline sent before this change.
    "claude-haiku-4-5-20251001": {
        "audit": {"temperature": 0.1, "max_tokens": 8192},
        "dedup": {"temperature": 0.0, "max_tokens": 512},
    },
    # Preset: reasoning effort, no temperature, max_completion_tokens.
    "gpt-6-luna": {
        "audit": {"max_completion_tokens": 24192, "reasoning_effort": "medium"},
        "dedup": {"max_completion_tokens": 24192, "reasoning_effort": "medium"},
    },
}


def _fake_sdks(monkeypatch):
    """Replace both SDK clients with fakes that record every request.

    Audit prompts get an empty JSON object back. The dedup prompt (the only
    one listing "IDX" lines) gets ``[1]``, marking the first row a duplicate.
    """
    requests = {"audit": [], "dedup": []}

    def answer(prompt, kwargs):
        kind = "dedup" if "IDX 1 |" in prompt else "audit"
        requests[kind].append({"prompt": prompt, **kwargs})
        return "[1]" if kind == "dedup" else "{}"

    class FakeAnthropic:
        """Anthropic client whose messages.create answers locally."""

        def __init__(self, **_):
            """Expose ``messages.create``."""
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            """Return a Messages-shaped response."""
            text = answer(kwargs["messages"][0]["content"], kwargs)
            return SimpleNamespace(
                model=kwargs["model"],
                content=[SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                stop_reason="end_turn",
            )

    class FakeOpenAI:
        """OpenAI client whose chat.completions.create answers locally."""

        def __init__(self, **_):
            """Expose ``chat.completions.create``."""
            completions = SimpleNamespace(create=self._create)
            self.chat = SimpleNamespace(completions=completions)

        def _create(self, **kwargs):
            """Return a Chat Completions-shaped response."""
            text = answer(kwargs["messages"][0]["content"], kwargs)
            return SimpleNamespace(
                model=kwargs["model"],
                choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return requests


@pytest.mark.parametrize("model", EXPECTED)
def test_audit_and_report_send_the_right_request(tmp_path, monkeypatch, model):
    """A live run produces a deduplicated report using the model's request shape."""
    requests = _fake_sdks(monkeypatch)
    html = tmp_path / "page.html"
    html.write_text(PAGE, encoding="utf-8")
    output_dir = tmp_path / "out"

    manifest = run_pipeline(
        html_path=str(html),
        output_dir=output_dir,
        api_key="test-key",
        model=model,
        dry_run=False,
        include_summaries=False,
    )
    report = generate_report(output_dir, tmp_path / "report", api_key="test-key", model=model)

    # Every prompt the pipeline ran succeeded through the request client.
    executed = manifest["prompts_executed"]
    assert executed and all(p["status"] == "success" for p in executed)
    assert len(requests["audit"]) == len(executed)

    # Dedup ran (not silently skipped) and removed the row it was told to.
    assert len(requests["dedup"]) == 1
    rows_sent = len(re.findall(r"^IDX \d+ \|", requests["dedup"][0]["prompt"], re.M))
    with report.open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == rows_sent - 1

    # Each request used the shape expected for this model.
    for kind in ("audit", "dedup"):
        for request in requests[kind]:
            shape = {key: request[key] for key in SHAPE_KEYS if key in request}
            assert shape == EXPECTED[model][kind], kind
