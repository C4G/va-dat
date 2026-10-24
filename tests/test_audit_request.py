"""Provider failures retain the evidence consumed by evaluator execution."""

from types import SimpleNamespace

from processing_scripts.llm_client.audit import AuditRequestClient, AuditRequestConfig


def test_failure_exposes_request_and_provider_information():
    """Failures retain the metadata needed for later classification."""
    class ProviderFailure(Exception):
        status_code = 429
        code = "rate_limit_exceeded"
        request_id = "req_failed_1"

    def fail(**kwargs):
        """Raise a provider-shaped failure without a network request."""
        raise ProviderFailure("try again later")

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    result = AuditRequestClient("unused", provider_client=fake, request_config=AuditRequestConfig(
        model="gpt-6-luna", reasoning_effort="medium", temperature=None,
    )).call("audit")
    assert not result["success"]
    assert result["error"] == "try again later"
    assert result["provider"] == {"name": "openai", "endpoint": "chat.completions"}
    assert result["model"] == "gpt-6-luna"
    assert result["usage"]["total_tokens"] == 0 and result["stop_reason"] is None
    assert result["failure"] == {
        "type": "ProviderFailure", "message": "try again later",
        "code": "rate_limit_exceeded", "status_code": 429, "request_id": "req_failed_1",
    }
    assert result["request"] == {
        "model": "gpt-6-luna", "reasoning_effort": "medium", "max_output_tokens": 8192,
        "sampling": {"temperature": None, "omitted_parameters": ["temperature"]},
    }
