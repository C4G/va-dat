"""Shared core of the Automated reviewer: one structured request, validated.

The mapper and the matcher both send their decisions through `AutomatedReviewer`.
It fills a versioned prompt template, asks the model for a JSON-schema response
through `llm_client`, checks the answer with the caller's validator, and retries
once with the validation error appended. Every request's usage and estimated
cost is kept so the caller can record what the review spent.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from processing_scripts.llm_client.request import LLMRequestClient
from vision_aid.evaluation.execution.llm_audit import (
    MODEL_PRESETS,
    USAGE_KEYS,
    billable_usage,
    evaluation_configuration,
    write_json,
)
from vision_aid.evaluation.execution.pricing import PriceSchedule

PROMPT_DIRECTORY = Path(__file__).parent
RECORD_FILENAME = "automated-review.json"


class ReviewFailure(Exception):
    """The Automated reviewer could not produce valid decisions."""


class CostLimitReached(ReviewFailure):
    """The cost limit was used up before the next reviewer request."""


def reviewer_attribution(model: str, prompt: str) -> str:
    """Return the reviewer name recorded in reports: `<model>/<effort>/<prompt>`."""
    effort = MODEL_PRESETS[model].reasoning_effort or "default"
    return f"{model}/{effort}/{prompt}"


def load_prompt(prompt: str) -> str:
    """Read a versioned reviewer prompt template, e.g. `matcher_v1`."""
    return (PROMPT_DIRECTORY / f"{prompt}.txt").read_text(encoding="utf-8")


class AutomatedReviewer:
    """A fixed model, preset, and prompt that makes review decisions.

    `spent` is what earlier steps already spent against `limit`; the limit is
    checked before every request, so one request can overshoot it.
    """

    def __init__(
        self,
        role: str,
        model: str,
        prompt: str,
        api_key: str,
        schedule: PriceSchedule,
        limit: Decimal,
        spent: Decimal = Decimal(0),
    ):
        """Create the provider client for `model` using its preset."""
        if model not in MODEL_PRESETS:
            raise ValueError(f"No request preset exists for reviewer model {model!r}")
        self.role = role
        self.model = model
        self.prompt = prompt
        self.request_config = MODEL_PRESETS[model]
        self.attribution = reviewer_attribution(model, prompt)
        self.schedule = schedule
        self.limit = limit
        self.spent = spent
        self.template = load_prompt(prompt)
        self.estimated_cost = Decimal(0)
        self.usage = {key: 0 for key in USAGE_KEYS}
        self.requests: list[dict[str, Any]] = []
        self._client = LLMRequestClient(
            api_key=api_key, request_config=self.request_config, max_retries=0,
        )

    def decide(
        self,
        payload: Any,
        schema: dict[str, Any],
        validate: Callable[[Any], Any],
        label: str,
    ) -> Any:
        """Ask for one decision set and return `validate(parsed_response)`.

        `validate` raises ValueError when the answer is unusable. The first
        failure is retried once with the error appended to the prompt; a
        second raises ReviewFailure.
        """
        prompt = self.template.replace(
            "{payload}", json.dumps(payload, indent=2, ensure_ascii=False)
        )
        error = None
        for attempt in (1, 2):
            text = prompt if error is None else (
                f"{prompt}\n\nYour previous answer was rejected: {error}\n"
                "Answer again, correcting that problem."
            )
            result = self._send(text, schema, label, attempt)
            try:
                if not result.get("success"):
                    raise ValueError(f"request failed: {result.get('error')}")
                return validate(json.loads(str(result.get("response") or "")))
            except ValueError as problem:  # json.JSONDecodeError is a ValueError.
                error = str(problem)
                self.requests[-1]["error"] = error
        raise ReviewFailure(f"{self.role} review failed for {label}: {error}")

    def _send(self, text: str, schema: dict[str, Any], label: str, attempt: int) -> dict:
        """Check the cost limit, send one request, and add its usage and cost."""
        if self.spent + self.estimated_cost >= self.limit:
            raise CostLimitReached(
                f"{self.role} review stopped: cost limit ${self.limit} reached"
            )
        try:
            result = self._client.call(text, json_schema=schema)
        except Exception as error:
            # Keep an unexpected client failure as a failed request.
            result = {"success": False, "response": None, "usage": {}, "error": str(error)}
        reported = result.get("usage") or {}
        for key in USAGE_KEYS:
            self.usage[key] += int(reported.get(key) or 0)
        billable = billable_usage(self.model, reported)
        cost = self.schedule.estimate(self.model, billable)
        self.estimated_cost += Decimal(cost)
        self.requests.append({
            "label": label, "attempt": attempt, "success": bool(result.get("success")),
            "billable_usage": billable, "estimated_cost_usd": cost, "error": None,
        })
        return result

    def record(self, folder: Path, status: str, failure: str | None = None) -> Path:
        """Write this reviewer's attribution, usage, and cost to `folder`."""
        path = folder / RECORD_FILENAME
        write_json(path, {
            "role": self.role,
            "reviewer": self.attribution,
            "prompt": self.prompt,
            "configuration": evaluation_configuration(self.request_config),
            "pricing_version": self.schedule.version,
            "pricing_sha256": self.schedule.identity,
            "max_cost_usd": str(self.limit - self.spent),
            "estimated_cost_usd": format(self.estimated_cost.normalize(), "f"),
            "usage": self.usage,
            "requests": self.requests,
            "status": status,
            "failure": failure,
        })
        return path
