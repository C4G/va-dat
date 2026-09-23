from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

import pytest

from entry_points.run_pipeline import (
    AuditRequestConfig,
    PipelineClient,
    run_pipeline,
)


class RecordingCompletions:
    def __init__(self, response):
        """Store the response returned by every fake completion."""
        self.response = response
        self.requests = []

    def create(self, **kwargs):
        """Record request arguments and return the configured response."""
        self.requests.append(kwargs)
        return self.response


class OpenAIFake:
    def __init__(self, response):
        """Expose the Chat Completions shape used by the OpenAI SDK."""
        self.chat = SimpleNamespace(completions=RecordingCompletions(response))


class RecordingMessages:
    def __init__(self, response):
        """Store the response returned by every fake message request."""
        self.response = response
        self.requests = []

    def create(self, **kwargs):
        """Record request arguments and return the configured response."""
        self.requests.append(kwargs)
        return self.response


class AnthropicFake:
    def __init__(self, response):
        """Expose the Messages shape used by the Anthropic SDK."""
        self.messages = RecordingMessages(response)


class RecordingModels:
    def __init__(self, response):
        """Store the response returned by every fake content request."""
        self.response = response
        self.requests = []

    def generate_content(self, **kwargs):
        """Record request arguments and return the configured response."""
        self.requests.append(kwargs)
        return self.response


class GeminiFake:
    def __init__(self, response):
        """Expose the Models shape used by the Google Gen AI SDK."""
        self.models = RecordingModels(response)


class AuditRequestTests(TestCase):
    def test_legacy_provider_request_defaults_are_preserved(self):
        """Implicit configuration preserves all production request defaults."""
        anthropic_response = SimpleNamespace(
            id="msg_prod_1",
            model="claude-sonnet-5",
            type="message",
            content=[SimpleNamespace(type="text", text="[]")],
            usage=SimpleNamespace(
                input_tokens=40,
                output_tokens=12,
                cache_creation_input_tokens=3,
                cache_read_input_tokens=7,
            ),
            stop_reason="end_turn",
        )
        anthropic_fake = AnthropicFake(anthropic_response)

        anthropic_result = PipelineClient(
            "unused", "claude-sonnet-5", provider_client=anthropic_fake
        ).call("audit")

        self.assertEqual(
            anthropic_fake.messages.requests,
            [
                {
                    "model": "claude-sonnet-5",
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": "audit"}],
                }
            ],
        )
        self.assertEqual(anthropic_result["provider"]["name"], "anthropic")
        self.assertEqual(anthropic_result["usage"]["cached_input_tokens"], 7)
        self.assertEqual(anthropic_result["usage"]["cache_creation_input_tokens"], 3)
        self.assertEqual(
            anthropic_result["request"]["sampling"],
            {
                "temperature": None,
                "omitted_parameters": ["temperature"],
            },
        )

        openai_response = SimpleNamespace(
            id="chatcmpl-prod-1",
            model="gpt-4o",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="[]"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=25,
                completion_tokens=5,
                total_tokens=30,
                prompt_tokens_details=None,
                completion_tokens_details=None,
            ),
        )
        openai_fake = OpenAIFake(openai_response)

        PipelineClient("unused", "gpt-4o", provider_client=openai_fake).call("audit")

        self.assertEqual(
            openai_fake.chat.completions.requests,
            [
                {
                    "model": "gpt-4o",
                    "max_tokens": 8192,
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": "audit"}],
                }
            ],
        )

        gemini_response = SimpleNamespace(
            response_id="gemini-prod-1",
            model_version="gemini-flash-latest",
            text="[]",
            usage_metadata=SimpleNamespace(
                prompt_token_count=31,
                candidates_token_count=6,
                total_token_count=39,
                cached_content_token_count=2,
                thoughts_token_count=2,
            ),
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
        )
        gemini_fake = GeminiFake(gemini_response)

        gemini_result = PipelineClient(
            "unused", "gemini-flash-latest", provider_client=gemini_fake
        ).call("audit")

        self.assertEqual(
            gemini_fake.models.requests,
            [
                {
                    "model": "gemini-flash-latest",
                    "contents": "audit",
                    "config": {
                        "temperature": 0.1,
                        "max_output_tokens": 8192,
                    },
                }
            ],
        )
        self.assertEqual(gemini_result["provider"]["name"], "google")
        self.assertEqual(gemini_result["usage"]["cached_input_tokens"], 2)
        self.assertEqual(gemini_result["usage"]["reasoning_tokens"], 2)
        self.assertEqual(gemini_result["usage"]["total_tokens"], 39)

    def test_failure_exposes_request_and_provider_information(self):
        """Failures retain the metadata needed for later classification."""

        class ProviderFailure(Exception):
            status_code = 429
            code = "rate_limit_exceeded"
            request_id = "req_failed_1"

        fake = OpenAIFake(None)

        def fail(**kwargs):
            """Raise a provider-shaped failure without a network request."""
            raise ProviderFailure("try again later")

        fake.chat.completions.create = fail
        config = AuditRequestConfig(
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            temperature=None,
        )

        result = PipelineClient(
            "unused", request_config=config, provider_client=fake
        ).call("audit")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "try again later")
        self.assertEqual(result["provider"]["name"], "openai")
        self.assertEqual(result["provider"]["endpoint"], "chat.completions")
        self.assertEqual(result["model"], "gpt-5.6-luna")
        self.assertEqual(result["usage"]["total_tokens"], 0)
        self.assertIsNone(result["stop_reason"])
        self.assertEqual(
            result["failure"],
            {
                "type": "ProviderFailure",
                "message": "try again later",
                "code": "rate_limit_exceeded",
                "status_code": 429,
                "request_id": "req_failed_1",
            },
        )
        self.assertEqual(result["request"], config.as_metadata())

    def test_pipeline_persists_explicit_request_configuration(self):
        """The pipeline records explicit configuration without going live."""
        config = AuditRequestConfig(
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            temperature=None,
            max_output_tokens=8192,
        )

        with TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            root = Path(directory)
            html_path = root / "benchmark.html"
            html_path.write_text(
                "<html><head><title>Benchmark</title></head>"
                "<body><main><h1>Benchmark</h1></main></body></html>",
                encoding="utf-8",
            )

            manifest = run_pipeline(
                html_path=str(html_path),
                output_dir=root / "output",
                api_key=None,
                model="gpt-5.6-luna",
                dry_run=True,
                include_summaries=False,
                request_config=config,
            )

        self.assertTrue(manifest["dry_run"])
        self.assertEqual(manifest["request_config"], config.as_metadata())
        self.assertEqual(manifest["total_input_tokens"], 0)
        self.assertEqual(manifest["total_output_tokens"], 0)


@pytest.mark.parametrize(
    "parts,stop", [(["[", "]"], "end_turn"), ([], "end_turn"), (["["], "max_tokens")]
)
def test_haiku_thinking_stream_exposes_only_final_text(parts, stop):
    """Only final text and inclusive billed output leave a thinking stream."""
    from contextlib import nullcontext

    from processing_scripts.llm_client.audit import AuditRequestClient

    def event(kind, **values):
        return SimpleNamespace(type=kind, **values)

    events = [
        event(
            "message_start",
            message=SimpleNamespace(
                id="msg-thinking",
                model="claude-haiku-4-5-20251001",
                type="message",
                usage=SimpleNamespace(input_tokens=100, output_tokens=1),
            ),
        ),
        event(
            "content_block_start", content_block=event("thinking", thinking="SECRET")
        ),
        event("content_block_delta", delta=event("thinking_delta", thinking="SECRET")),
        event(
            "content_block_delta", delta=event("signature_delta", signature="SECRET")
        ),
        event(
            "content_block_start",
            content_block=event("redacted_thinking", data="SECRET"),
        ),
        *[
            event("content_block_start", content_block=event("text", text=part))
            for part in parts
        ],
        event("content_block_delta", delta=event("text_delta", text="")),
        event(
            "message_delta",
            delta=SimpleNamespace(stop_reason=stop),
            usage=SimpleNamespace(output_tokens=16002),
        ),
        event("message_stop"),
    ]
    fake = AnthropicFake(nullcontext(iter(events)))
    result = AuditRequestClient(
        "unused",
        provider_client=fake,
        request_config=AuditRequestConfig(
            model="claude-haiku-4-5-20251001",
            temperature=None,
            thinking_budget_tokens=16000,
            max_output_tokens=24192,
        ),
    ).call("audit")
    assert fake.messages.requests == [
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 24192,
            "messages": [{"role": "user", "content": "audit"}],
            "thinking": {"type": "enabled", "budget_tokens": 16000},
            "stream": True,
        }
    ]
    assert result["success"]
    assert result["response"] == "".join(parts)
    assert result["stop_reason"] == stop
    assert result["usage"]["output_tokens"] == 16002
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["reasoning_tokens"] is None
    assert "SECRET" not in str(result)


def test_interrupted_thinking_stream_keeps_reported_billed_usage():
    """An interrupted stream retains text already received and billed usage."""
    from contextlib import nullcontext

    from processing_scripts.llm_client.audit import AuditRequestClient

    def events():
        yield SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                id="partial",
                model="claude-haiku-4-5-20251001",
                type="message",
                usage=SimpleNamespace(input_tokens=100, output_tokens=1),
            ),
        )
        yield SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="text", text="partial finding"),
        )
        yield SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="max_tokens"),
            usage=SimpleNamespace(output_tokens=16002),
        )
        raise TimeoutError("stream interrupted")

    result = AuditRequestClient(
        "unused",
        provider_client=AnthropicFake(nullcontext(events())),
        request_config=AuditRequestConfig(
            model="claude-haiku-4-5-20251001",
            temperature=None,
            thinking_budget_tokens=16000,
            max_output_tokens=24192,
        ),
    ).call("audit")
    assert not result["success"]
    assert result["response"] == "partial finding"
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["output_tokens"] == 16002
    assert result["usage"]["reasoning_tokens"] is None
    assert result["stop_reason"] == "max_tokens"
    assert result["failure"]["type"] == "TimeoutError"


def test_evaluation_can_disable_anthropic_sdk_retries(monkeypatch):
    """The request client forwards a zero retry policy only when requested."""
    from processing_scripts.llm_client.audit import AuditRequestClient

    options = []
    monkeypatch.setattr(
        "anthropic.Anthropic",
        lambda **kwargs: options.append(kwargs) or AnthropicFake(None),
    )
    AuditRequestClient(
        "unused",
        request_config=AuditRequestConfig(model="claude-haiku-4-5-20251001"),
        max_retries=0,
    )
    assert options == [{"api_key": "unused", "max_retries": 0}]
