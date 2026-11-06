"""Network-free tests for the audit request client and model presets.

Every provider SDK is replaced by a fake that records the request it was
sent, so these tests make no API calls and need no keys.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from entry_points import generate_report, run_pipeline
from processing_scripts.llm_client import audit
from processing_scripts.llm_client.audit import AuditRequestClient, AuditRequestConfig
from processing_scripts.llm_client.presets import MODEL_PRESETS, request_config_for

LEGACY_KEYS = {"success", "response", "model", "usage", "stop_reason", "duration_seconds"}


class _Recorder:
    """Record keyword arguments and hand back a canned response."""

    def __init__(self, response):
        """Store the response to return from every call."""
        self.calls: list[dict] = []
        self._response = response

    def __call__(self, **kwargs):
        """Record *kwargs* and return the canned response (or raise it)."""
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response(kwargs) if callable(self._response) else self._response


def _anthropic_message(text="[]"):
    """Return a non-streamed Anthropic Messages response."""
    return SimpleNamespace(
        id="msg_1",
        type="message",
        model="claude-test",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        stop_reason="end_turn",
    )


class _AnthropicStream:
    """Context manager yielding a thinking block followed by text."""

    def __init__(self, events):
        """Store the events to yield."""
        self._events = events

    def __enter__(self):
        """Return the event iterator."""
        return iter(self._events)

    def __exit__(self, *exc):
        """Propagate any exception."""
        return False


def _stream_events():
    """Return the Messages events for a thinking-then-text response."""
    event = SimpleNamespace
    return [
        event(
            type="message_start",
            message=event(
                id="msg_2",
                model="claude-haiku-5-5",
                type="message",
                usage={"input_tokens": 20, "output_tokens": 0},
            ),
        ),
        event(type="content_block_start", content_block=event(type="thinking")),
        event(type="content_block_delta", delta=event(type="thinking_delta", thinking="secret")),
        event(type="content_block_start", content_block=event(type="text", text="")),
        event(type="content_block_delta", delta=event(type="text_delta", text='{"ok":')),
        event(type="content_block_delta", delta=event(type="text_delta", text="true}")),
        event(
            type="message_delta",
            delta=event(stop_reason="end_turn"),
            usage={"output_tokens": 40},
        ),
        event(type="message_stop"),
    ]


def _anthropic(response):
    """Return a fake Anthropic client whose messages.create is a recorder."""
    create = _Recorder(response)
    return SimpleNamespace(messages=SimpleNamespace(create=create)), create


def _openai():
    """Return a fake OpenAI client whose chat.completions.create is a recorder."""
    response = SimpleNamespace(
        id="chatcmpl_1",
        model="gpt-test",
        choices=[SimpleNamespace(message=SimpleNamespace(content="[]"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )
    create = _Recorder(response)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


def _gemini():
    """Return a fake Gemini client whose models.generate_content is a recorder."""
    response = SimpleNamespace(
        text="[]",
        usage_metadata=SimpleNamespace(prompt_token_count=4, candidates_token_count=2),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
    )
    create = _Recorder(response)
    return SimpleNamespace(models=SimpleNamespace(generate_content=create)), create


# ── Default requests match the old PipelineClient ────────────────────────────


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            "claude-haiku-4-5-20251001",
            {"max_tokens": 8192, "temperature": 0.1},
        ),
        # Listed in supports_temperature's no-sampling set: temperature omitted.
        ("claude-sonnet-5", {"max_tokens": 8192}),
    ],
)
def test_default_anthropic_request_is_unchanged(model, expected):
    """Default Anthropic requests send what PipelineClient sent on main."""
    fake, create = _anthropic(_anthropic_message())
    AuditRequestClient(api_key="k", model=model, provider_client=fake).call("hi")

    assert create.calls == [
        {"model": model, "messages": [{"role": "user", "content": "hi"}], **expected}
    ]


def test_default_openai_request_is_unchanged():
    """Default OpenAI requests send what PipelineClient sent on main."""
    fake, create = _openai()
    AuditRequestClient(api_key="k", model="gpt-4o", provider_client=fake).call("hi")

    assert create.calls == [
        {
            "model": "gpt-4o",
            "max_tokens": 8192,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": "hi"}],
        }
    ]


def test_default_gemini_request_is_unchanged():
    """Default Gemini requests send what PipelineClient sent on main."""
    fake, create = _gemini()
    AuditRequestClient(api_key="k", model="gemini-flash-latest", provider_client=fake).call("hi")

    assert create.calls == [
        {
            "model": "gemini-flash-latest",
            "contents": "hi",
            "config": {"temperature": 0.1, "max_output_tokens": 8192},
        }
    ]


@pytest.mark.parametrize(
    ("model", "factory"),
    [
        ("claude-haiku-4-5-20251001", lambda: _anthropic(_anthropic_message())),
        ("gpt-4o", _openai),
        ("gemini-flash-latest", _gemini),
    ],
)
def test_result_keeps_the_keys_callers_read(model, factory):
    """run_pipeline, api_server and generate_report read these keys."""
    fake, _ = factory()
    result = AuditRequestClient(api_key="k", model=model, provider_client=fake).call("hi")

    assert result["success"] is True
    assert LEGACY_KEYS <= result.keys()
    assert result["response"] == "[]"
    assert {"input_tokens", "output_tokens"} <= result["usage"].keys()


def test_provider_error_is_returned_not_raised():
    """A provider exception becomes success=False with the error message."""
    fake, _ = _anthropic(RuntimeError("overloaded"))
    result = AuditRequestClient(
        api_key="k", model="claude-haiku-4-5-20251001", provider_client=fake
    ).call("hi")

    assert result["success"] is False
    assert result["error"] == "overloaded"
    assert result["usage"]["input_tokens"] == 0
    assert "duration_seconds" in result


# ── Preset requests ──────────────────────────────────────────────────────────


def test_anthropic_preset_streams_adaptive_thinking_and_drops_thinking_text():
    """Claude 5.5 presets stream with adaptive thinking and return only text."""
    fake, create = _anthropic(lambda kwargs: _AnthropicStream(_stream_events()))
    result = AuditRequestClient(
        api_key="k",
        request_config=MODEL_PRESETS["claude-haiku-5-5"],
        provider_client=fake,
    ).call("hi")

    assert create.calls == [
        {
            "model": "claude-haiku-5-5",
            "max_tokens": 24192,
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "stream": True,
        }
    ]
    assert result["success"] is True
    assert result["response"] == '{"ok":true}'
    assert result["stop_reason"] == "end_turn"
    assert (result["usage"]["input_tokens"], result["usage"]["output_tokens"]) == (20, 40)


def test_truncated_stream_is_a_failure_with_partial_usage():
    """A stream that never reaches message_stop is reported as a failure."""
    events = [e for e in _stream_events() if e.type != "message_stop"]
    fake, _ = _anthropic(lambda kwargs: _AnthropicStream(events))
    result = AuditRequestClient(
        api_key="k",
        request_config=MODEL_PRESETS["claude-haiku-5-5"],
        provider_client=fake,
    ).call("hi")

    assert result["success"] is False
    assert result["usage"]["output_tokens"] == 40


def test_openai_preset_sends_reasoning_effort_without_sampling():
    """GPT-6 presets use max_completion_tokens and reasoning_effort only."""
    fake, create = _openai()
    AuditRequestClient(
        api_key="k", request_config=MODEL_PRESETS["gpt-6-luna"], provider_client=fake
    ).call("hi")

    assert create.calls == [
        {
            "model": "gpt-6-luna",
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 24192,
            "reasoning_effort": "medium",
        }
    ]


def test_models_without_a_preset_get_the_default_config():
    """Only the listed models change; everything else keeps the defaults."""
    assert request_config_for("gpt-4o") == AuditRequestConfig(model="gpt-4o")
    assert request_config_for("claude-opus-5") == AuditRequestConfig(model="claude-opus-5")
    assert set(MODEL_PRESETS) == {
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5-5",
        "gpt-6-luna",
        "gpt-6.1-sol",
    }


# ── Callers pick up the presets ──────────────────────────────────────────────


@pytest.mark.parametrize("model", ["gpt-6-luna", "claude-haiku-4-5-20251001"])
def test_run_pipeline_uses_the_model_preset(tmp_path, monkeypatch, model):
    """run_pipeline without a request_config resolves the model's preset."""
    seen = []

    class FakeClient:
        """Stand-in for AuditRequestClient that records its config."""

        def __init__(self, api_key, request_config):
            """Record the configuration the pipeline built."""
            seen.append(request_config)

        def call(self, prompt):
            """Return an empty, successful result."""
            return {
                "success": True,
                "response": "[]",
                "model": model,
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "stop_reason": "stop",
                "duration_seconds": 0.0,
            }

    monkeypatch.setattr(run_pipeline, "PipelineClient", FakeClient)
    html = tmp_path / "page.html"
    html.write_text(
        "<html lang='en'><head><title>T</title></head>"
        "<body><main><h1>Hi</h1><img src='a.png'><a href='/x'>Link</a></main></body></html>",
        encoding="utf-8",
    )

    manifest = run_pipeline.run_pipeline(
        html_path=str(html),
        output_dir=tmp_path / "out",
        api_key="k",
        model=model,
        dry_run=False,
        include_summaries=False,
    )

    assert seen == [request_config_for(model)]
    assert manifest["request_config"]["model"] == model


def test_dedup_sends_preset_models_through_the_preset_client(monkeypatch):
    """The report's dedup pass uses the preset request for preset models."""
    sent = []

    class FakeClient:
        """Stand-in for AuditRequestClient that marks row 2 as a duplicate."""

        def __init__(self, api_key, request_config):
            """Record the configuration dedup chose."""
            sent.append(request_config)

        def call(self, prompt):
            """Report IDX 2 as a duplicate."""
            return {"success": True, "response": "[2]"}

    monkeypatch.setattr(audit, "AuditRequestClient", FakeClient)
    rows = [
        generate_report.ReportRow(issue_title="Missing alt"),
        generate_report.ReportRow(issue_title="Missing alt"),
    ]

    deduped = generate_report.deduplicate_with_llm(rows, api_key="k", model="gpt-6.1-sol")

    assert sent == [MODEL_PRESETS["gpt-6.1-sol"]]
    assert len(deduped) == 1
