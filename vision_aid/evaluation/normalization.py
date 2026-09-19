"""Lossless deterministic normalization of raw audit outcomes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from processing_scripts.llm.registry import PROMPT_REGISTRY, PromptSpec
from vision_aid.evaluation.schemas import CanonicalFinding

_PROMPTS = {item.name: item for item in PROMPT_REGISTRY if not item.is_summary}
_PROBLEM_KEYS = (
    "problem",
    "issue",
    "issue_title",
    "description",
    "finding",
    "reason",
    "actual_result",
    "summary",
)
_LOCATION_KEYS = (
    "location",
    "location_hint",
    "selector",
    "xpath",
    "text",
    "link_text",
    "src",
)
_ELEMENT_KEYS = ("element", "element_name", "tag", "html", "selector")
_WCAG_KEYS = ("wcag", "wcag_sc", "wcag_criteria", "criterion", "criteria")


@dataclass(frozen=True)
class NormalizationResult:
    """Findings plus the parse outcome for one successful raw response."""

    prompt: str
    parse_status: str
    raw_response: str
    findings: tuple[CanonicalFinding, ...]
    error: str | None = None


def _strip_fence(value: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", value, re.DOTALL)
    return match.group(1) if match else value.strip()


def _first_text(item: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)
    return ""


def _wcag(item: dict[str, Any], defaults: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    for key in _WCAG_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value)
        elif value:
            values.append(str(value))
    criteria = re.findall(r"\b\d+\.\d+\.\d+\b", " ".join(values))
    return tuple(dict.fromkeys(criteria or defaults))


def _items(parsed: Any, spec: PromptSpec) -> list[dict[str, Any]] | None:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return None
    for key in ("findings", "issues", "problems", "violations", "results"):
        nested = parsed.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    if spec.output_type == "object":
        if not parsed:
            return []
        return [parsed]
    return None


def normalize_prompt_response(
    prompt_name: str,
    raw_response: str,
    *,
    run_id: str,
    model: str,
    page_url: str,
) -> NormalizationResult:
    """Normalize one prompt directly, without suppression or deduplication."""
    spec = _PROMPTS.get(prompt_name)
    if spec is None:
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="unknown_prompt",
            raw_response=raw_response,
            findings=(),
            error=f"No fixed evaluation normalizer exists for {prompt_name!r}.",
        )
    try:
        parsed = json.loads(_strip_fence(raw_response))
    except (json.JSONDecodeError, TypeError) as error:
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="malformed",
            raw_response=raw_response,
            findings=(),
            error=str(error),
        )
    items = _items(parsed, spec)
    if items is None:
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="malformed",
            raw_response=raw_response,
            findings=(),
            error=f"Expected a JSON {spec.output_type} response.",
        )
    findings = []
    for index, item in enumerate(items):
        canonical_item = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = f"{run_id}\0{prompt_name}\0{index}\0{canonical_item}".encode()
        findings.append(
            CanonicalFinding(
                finding_id="finding-" + hashlib.sha256(identity).hexdigest()[:20],
                source="audit",
                run_id=run_id,
                model=model,
                prompt=prompt_name,
                checklist=spec.checklist,
                page_url=page_url,
                problem_family=prompt_name,
                problem=_first_text(item, _PROBLEM_KEYS) or prompt_name,
                element=_first_text(item, _ELEMENT_KEYS),
                location=_first_text(item, _LOCATION_KEYS),
                wcag_evidence=_wcag(item, spec.wcag_criteria),
                raw_source=item,
                parse_status="parsed",
            )
        )
    return NormalizationResult(
        prompt=prompt_name,
        parse_status="parsed" if findings else "empty",
        raw_response=raw_response,
        findings=tuple(findings),
    )


def normalize_programmatic_findings(
    raw_findings: Sequence[dict[str, Any]],
    *,
    run_id: str,
    page_url: str,
) -> tuple[CanonicalFinding, ...]:
    """Normalize checker output while retaining each complete source object."""
    normalized = []
    for index, item in enumerate(raw_findings):
        canonical_item = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = f"{run_id}\0programmatic\0{index}\0{canonical_item}".encode()
        rule = str(item.get("rule_id") or item.get("rule") or "programmatic")
        normalized.append(
            CanonicalFinding(
                finding_id="programmatic-" + hashlib.sha256(identity).hexdigest()[:20],
                source="programmatic",
                run_id=run_id,
                model=None,
                prompt=rule,
                checklist=str(item.get("checklist") or "programmatic"),
                page_url=page_url,
                problem_family=rule,
                problem=_first_text(item, _PROBLEM_KEYS + ("message",)) or rule,
                element=_first_text(item, _ELEMENT_KEYS),
                location=_first_text(item, _LOCATION_KEYS),
                wcag_evidence=_wcag(item, ()),
                raw_source=item,
                parse_status="parsed",
            )
        )
    return tuple(normalized)
