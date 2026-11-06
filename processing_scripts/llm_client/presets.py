"""Request presets for models that need more than the default request.

The web server and the model evaluator both read this table, so an
evaluated configuration is the one production runs. Models without an
entry use ``AuditRequestConfig(model=...)``: temperature 0.1 where the
model accepts it, 8,192 output tokens, and no thinking.
"""

from __future__ import annotations

from .audit import AuditRequestConfig

ANTHROPIC_THINKING_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")
OPENAI_REASONING_MODELS = ("gpt-6-luna", "gpt-6.1-sol")

MODEL_PRESETS: dict[str, AuditRequestConfig] = {
    **{
        model: AuditRequestConfig(
            model=model,
            adaptive_thinking=True,
            reasoning_effort="medium",
            max_output_tokens=24192,
            temperature=None,
        )
        for model in ANTHROPIC_THINKING_MODELS
    },
    **{
        model: AuditRequestConfig(
            model=model,
            reasoning_effort="medium",
            max_output_tokens=24192,
            temperature=None,
        )
        for model in OPENAI_REASONING_MODELS
    },
}


def request_config_for(model: str) -> AuditRequestConfig:
    """Return the preset for *model*, or the default request configuration."""
    return MODEL_PRESETS.get(model) or AuditRequestConfig(model=model)
