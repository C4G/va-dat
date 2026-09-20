"""Model-provider detection and request capability helpers."""

# OpenAI model prefixes used to detect provider from model ID
_OPENAI_PREFIXES = ("gpt-", "o1", "o3", "o4")

# Gemini model prefixes used to detect provider from model ID
_GEMINI_PREFIXES = ("gemini-",)


def is_openai_model(model: str) -> bool:
    """Return True if *model* looks like an OpenAI model ID."""
    return model.startswith(_OPENAI_PREFIXES)


def is_gemini_model(model: str) -> bool:
    """Return True if *model* looks like a Gemini model ID."""
    return model.startswith(_GEMINI_PREFIXES)


# Claude models (Opus 4.6+, Sonnet 4.6+, Fable/Mythos 5) that reject
# temperature/top_p/top_k (400 error) in favor of adaptive thinking + effort.
_NO_SAMPLING_PARAMS_MODELS = {
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
}


def supports_temperature(model: str) -> bool:
    """Return False for Claude models that reject the `temperature` param."""
    return model not in _NO_SAMPLING_PARAMS_MODELS
