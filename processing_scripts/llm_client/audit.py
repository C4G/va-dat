"""Provider-independent request configuration for accessibility audits."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from .client import is_gemini_model, is_openai_model, supports_temperature

ReasoningEffort = Literal[
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
]


@dataclass(frozen=True)
class AuditRequestConfig:
    """Configuration shared by every prompt in one audit run.

    ``temperature=None`` deliberately omits the sampling parameter. Existing
    production callers retain the historical 0.1 temperature and 8,192-token
    output limit when they do not supply this configuration explicitly.
    """

    model: str
    reasoning_effort: ReasoningEffort | None = None
    temperature: float | None = 0.1
    max_output_tokens: int = 8192

    def __post_init__(self) -> None:
        """Reject configuration values that cannot form an audit request."""
        if not self.model:
            raise ValueError("model must not be empty")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero")

    def as_metadata(self) -> dict[str, Any]:
        """Return the requested configuration as serializable metadata."""
        omitted = [] if self.temperature is not None else ["temperature"]
        return {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "sampling": {
                "temperature": self.temperature,
                "omitted_parameters": omitted,
            },
        }


def resolved_request_metadata(config: AuditRequestConfig) -> dict[str, Any]:
    """Describe the effective request after provider capability omissions."""
    metadata = config.as_metadata()
    if (
        not is_openai_model(config.model)
        and not is_gemini_model(config.model)
        and not supports_temperature(config.model)
    ):
        metadata["sampling"] = {
            "temperature": None,
            "omitted_parameters": ["temperature"],
        }
    return metadata


def _provider_data(value: Any) -> Any:
    """Convert SDK response metadata into JSON-serializable builtins."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _provider_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_provider_data(item) for item in value]
    if hasattr(value, "model_dump"):
        return _provider_data(value.model_dump())
    if hasattr(value, "to_dict"):
        return _provider_data(value.to_dict())
    if hasattr(value, "__dict__"):
        return {
            key: _provider_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def _usage_result(
    provider_usage: Any,
    *,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
    cached_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> dict[str, Any]:
    """Return common token categories plus the lossless provider payload."""
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": (
            total_tokens
            if total_tokens is not None
            else input_tokens + output_tokens
        ),
        "cached_input_tokens": cached_input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "provider_usage": _provider_data(provider_usage),
    }


class AuditRequestClient:
    """Send an audit prompt through Anthropic, OpenAI, or Gemini.

    The returned dict retains the legacy keys consumed by the production
    pipeline and adds complete provider, request, usage, timing, stop, and
    failure metadata for evaluation runs.
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        max_tokens: int = 8192,
        *,
        request_config: AuditRequestConfig | None = None,
        provider_client: Any | None = None,
    ):
        """Resolve legacy arguments and initialize the selected SDK client."""
        if request_config is None:
            if model is None:
                raise TypeError("model or request_config is required")
            request_config = AuditRequestConfig(
                model=model,
                max_output_tokens=max_tokens,
            )
        elif model is not None and model != request_config.model:
            raise ValueError("model and request_config.model must match")

        self.request_config = request_config
        self.model = request_config.model
        self.max_tokens = request_config.max_output_tokens
        self._is_openai = is_openai_model(self.model)
        self._is_gemini = is_gemini_model(self.model)

        if request_config.reasoning_effort is not None and not self._is_openai:
            raise ValueError(
                "reasoning_effort is only supported for OpenAI audit requests"
            )

        if provider_client is not None:
            self._client = provider_client
        elif self._is_openai:
            import openai

            self._client = openai.OpenAI(api_key=api_key)
        elif self._is_gemini:
            from google import genai

            self._client = genai.Client(api_key=api_key)
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key)

    def call(self, prompt: str) -> dict[str, Any]:
        """Send one prompt and return a provider-neutral audit result."""
        start = time.monotonic()

        try:
            if self._is_openai:
                result = self._call_openai(prompt, start)
            elif self._is_gemini:
                result = self._call_gemini(prompt, start)
            else:
                result = self._call_anthropic(prompt, start)
            result["request"] = resolved_request_metadata(self.request_config)
            return result
        except Exception as exc:
            return {
                "success": False,
                "response": None,
                "model": self.model,
                "provider": self._provider_identity(),
                "request": resolved_request_metadata(self.request_config),
                "usage": _usage_result(
                    None,
                    input_tokens=0,
                    output_tokens=0,
                ),
                "stop_reason": None,
                "error": str(exc),
                "duration_seconds": round(time.monotonic() - start, 2),
                "failure": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "code": _provider_data(getattr(exc, "code", None)),
                    "status_code": getattr(exc, "status_code", None),
                    "request_id": getattr(exc, "request_id", None),
                },
            }

    def _provider_identity(self) -> dict[str, Any]:
        """Return stable provider and endpoint names for failed requests."""
        if self._is_openai:
            return {"name": "openai", "endpoint": "chat.completions"}
        if self._is_gemini:
            return {"name": "google", "endpoint": "models.generate_content"}
        return {"name": "anthropic", "endpoint": "messages"}

    def _call_anthropic(self, prompt: str, start: float) -> dict[str, Any]:
        """Send one prompt through Anthropic Messages."""
        request_kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if (
            self.request_config.temperature is not None
            and supports_temperature(self.model)
        ):
            request_kwargs["temperature"] = self.request_config.temperature

        message = self._client.messages.create(**request_kwargs)
        response_text = "".join(
            block.text for block in message.content if block.type == "text"
        )

        return {
            "success": True,
            "response": response_text,
            "model": message.model,
            "provider": {
                "name": "anthropic",
                "endpoint": "messages",
                "response_id": getattr(message, "id", None),
                "response_model": message.model,
                "response_type": getattr(message, "type", None),
            },
            "usage": _usage_result(
                message.usage,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                cached_input_tokens=getattr(
                    message.usage, "cache_read_input_tokens", 0
                )
                or 0,
                cache_creation_input_tokens=getattr(
                    message.usage, "cache_creation_input_tokens", 0
                )
                or 0,
            ),
            "stop_reason": message.stop_reason,
            "duration_seconds": round(time.monotonic() - start, 2),
            "failure": None,
        }

    def _call_openai(self, prompt: str, start: float) -> dict[str, Any]:
        """Send one prompt through OpenAI Chat Completions."""
        request_kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.request_config.reasoning_effort is None:
            request_kwargs["max_tokens"] = self.max_tokens
        else:
            request_kwargs["max_completion_tokens"] = self.max_tokens
            request_kwargs["reasoning_effort"] = (
                self.request_config.reasoning_effort
            )
        if self.request_config.temperature is not None:
            request_kwargs["temperature"] = self.request_config.temperature

        response = self._client.chat.completions.create(**request_kwargs)
        prompt_details = getattr(response.usage, "prompt_tokens_details", None)
        completion_details = getattr(
            response.usage, "completion_tokens_details", None
        )

        return {
            "success": True,
            "response": response.choices[0].message.content,
            "model": response.model,
            "provider": {
                "name": "openai",
                "endpoint": "chat.completions",
                "response_id": getattr(response, "id", None),
                "response_model": response.model,
                "service_tier": getattr(response, "service_tier", None),
                "system_fingerprint": getattr(
                    response, "system_fingerprint", None
                ),
            },
            "usage": _usage_result(
                response.usage,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=getattr(response.usage, "total_tokens", None),
                cached_input_tokens=getattr(
                    prompt_details, "cached_tokens", 0
                )
                or 0,
                reasoning_tokens=getattr(
                    completion_details, "reasoning_tokens", 0
                )
                or 0,
            ),
            "stop_reason": response.choices[0].finish_reason,
            "duration_seconds": round(time.monotonic() - start, 2),
            "failure": None,
        }

    def _call_gemini(self, prompt: str, start: float) -> dict[str, Any]:
        """Send one prompt through Gemini generateContent."""
        generation_config = {"max_output_tokens": self.max_tokens}
        if self.request_config.temperature is not None:
            generation_config["temperature"] = self.request_config.temperature

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=generation_config,
        )
        usage = response.usage_metadata

        return {
            "success": True,
            "response": response.text,
            "model": self.model,
            "provider": {
                "name": "google",
                "endpoint": "models.generate_content",
                "response_id": getattr(response, "response_id", None),
                "response_model": getattr(
                    response, "model_version", self.model
                ),
            },
            "usage": _usage_result(
                usage,
                input_tokens=usage.prompt_token_count,
                output_tokens=usage.candidates_token_count,
                total_tokens=getattr(usage, "total_token_count", None),
                cached_input_tokens=getattr(
                    usage, "cached_content_token_count", 0
                )
                or 0,
                reasoning_tokens=(
                    getattr(usage, "thoughts_token_count", 0) or 0
                ),
            ),
            "stop_reason": (
                response.candidates[0].finish_reason.name
                if response.candidates
                else None
            ),
            "duration_seconds": round(time.monotonic() - start, 2),
            "failure": None,
        }
