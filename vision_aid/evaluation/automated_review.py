"""Shared core of the Automated reviewer: one structured request, validated.

The mapper and the matcher both send their decisions through `AutomatedReviewer`.
It fills a prompt template from `prompts/`, asks the model for a JSON-schema response
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
from vision_aid.evaluation.execution.pricing import PriceSchedule, format_usd

PROMPT_DIRECTORY = Path(__file__).parent / "prompts"
RECORD_FILENAME = "automated-review.json"


class ReviewFailure(Exception):
    """The Automated reviewer could not produce valid decisions."""


class CostLimitReached(ReviewFailure):
    """The cost limit was used up before the next reviewer request."""


def reviewer_attribution(model: str, prompt: str) -> str:
    """Return the reviewer name recorded in reports: `<model>/<effort>/<prompt>`."""
    effort = MODEL_PRESETS[model].reasoning_effort or "default"
    return f"{model}/{effort}/{prompt}"


def decision_schema(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return the response schema: a list of decisions, one per Human finding.

    Each decision has `human_finding_id` plus the role's `fields`, all required.
    """
    return {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"human_finding_id": {"type": "string"}, **fields},
                    "required": ["human_finding_id", *fields],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["decisions"],
        "additionalProperties": False,
    }


def decision_text(decision: dict[str, Any], field: str) -> str:
    """Return a decision's text field, stripped; missing or null is empty."""
    return str(decision.get(field) or "").strip()


def validated_decisions(
    response: Any,
    human_ids: list[str],
    refs_field: str,
    known_refs: set[str],
    ref_kind: str,
    decide: Callable[[str, dict[str, Any], list[str]], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Check the checks every role shares and return `decide`'s result per Human finding.

    Every Human finding in `human_ids` must be decided exactly once. Its
    `refs_field` must list only `known_refs`, each at most once, and no
    reference may serve two Human findings. `decide(human_id, decision, refs)`
    adds the role's own checks and returns the values to keep. Raises
    ValueError naming the first problem, which is sent back on retry.
    """
    if not isinstance(response, dict) or not isinstance(response.get("decisions"), list):
        raise ValueError("the response must be an object with a decisions list")
    decided: dict[str, dict[str, Any]] = {}
    used: dict[str, str] = {}
    for decision in response["decisions"]:
        human_id = decision.get("human_finding_id") if isinstance(decision, dict) else None
        if human_id not in human_ids:
            raise ValueError(f"unknown Human finding: {human_id}")
        if human_id in decided:
            raise ValueError(f"Human finding {human_id} is decided more than once")
        listed = decision.get(refs_field)
        if not isinstance(listed, list):
            raise ValueError(f"{refs_field} for {human_id} must be a list")
        refs = [text for text in (str(item).strip() for item in listed) if text]
        unknown = sorted(set(refs) - known_refs)
        if unknown:
            raise ValueError(f"unknown {ref_kind} for {human_id}: {', '.join(unknown)}")
        if len(refs) != len(set(refs)):
            raise ValueError(f"a {ref_kind} is repeated for {human_id}")
        for ref in refs:
            if ref in used:
                raise ValueError(f"{ref_kind} {ref} is used for both {used[ref]} and {human_id}")
            used[ref] = human_id
        decided[human_id] = decide(human_id, decision, refs)
    missing = [human_id for human_id in human_ids if human_id not in decided]
    if missing:
        raise ValueError(f"no decision for Human finding: {', '.join(missing)}")
    return decided


def load_prompt(prompt: str) -> str:
    """Read a reviewer prompt template from `prompts/`, e.g. `matcher`."""
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
            "estimated_cost_usd": format_usd(self.estimated_cost),
            "usage": self.usage,
            "requests": self.requests,
            "status": status,
            "failure": failure,
        })
        return path
