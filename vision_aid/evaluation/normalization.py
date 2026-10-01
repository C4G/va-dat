"""Lossless deterministic normalization of raw LLM outcomes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from entry_points.generate_report import NORMALIZERS, safe_parse_json
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
# Checks without a tool normalizer only reach users on screen; these fields name their element.
_SCREEN_ONLY_ELEMENT_KEYS = ("field_id", "src", "legend", "placeholder")


@dataclass(frozen=True)
class NormalizationResult:
    """Findings plus the parse outcome for one successful raw response."""

    prompt: str
    parse_status: str
    raw_response: str
    findings: tuple[CanonicalFinding, ...]
    error: str | None = None


def _first_text(item: dict[str, Any], keys: Iterable[str]) -> str:
    """Return the first populated evidence field as stable text."""
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)
    return ""


def _wcag(item: dict[str, Any], defaults: Sequence[str]) -> tuple[str, ...]:
    """Extract ordered WCAG identifiers or use the prompt defaults."""
    values: list[str] = []
    for key in _WCAG_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value)
        elif value:
            values.append(str(value))
    criteria = re.findall(r"\b\d+\.\d+\.\d+\b", " ".join(values))
    return tuple(dict.fromkeys(criteria or defaults))


def _listed(value: Any) -> list[Any]:
    """Treat a missing or empty value as no issues and a lone value as one."""
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def _objects(parsed: Any, shape: str) -> list[dict[str, Any]]:
    """Return a response's items, rejecting a shape the check's rule cannot read."""
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError(f"Expected a JSON {shape} response.")
    return parsed


def _tool_findings(
    normalizer: Any, parsed: Any, spec: PromptSpec
) -> list[tuple[int, Any, str, str, str]]:
    """Read findings with the tool's report rule, pairing each row with its source."""
    wcag = ", ".join(spec.wcag_criteria)
    if spec.output_type == "object":
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object response.")
        rows = normalizer(parsed, wcag=wcag)
        # Page-level rules write one row per issue, then one per vague heading.
        issues = [*(parsed.get("issues") or []), *(parsed.get("vague_headings") or [])]
        sources = [{"response": parsed, "issue": issue} for issue in issues]
        paired = list(enumerate(zip(sources, rows)))
    else:
        # One item at a time, so each row keeps the item it came from.
        paired = [
            (index, (item, row))
            for index, item in enumerate(_objects(parsed, "array"))
            for row in normalizer([item], wcag=wcag)
        ]
    return [
        (
            position,
            source,
            row.actual_result or row.issue_title,
            row.element_name,
            row.steps_to_reproduce,
        )
        for position, (source, row) in paired
    ]


def _screen_only_findings(
    prompt_name: str, parsed: Any
) -> list[tuple[int, Any, str, str, str]]:
    """Read a check the tool's report skips: a finding needs a listed problem."""
    if prompt_name == "table_semantics" and isinstance(parsed, dict):
        # The table prompt asks for one object rather than a list.
        parsed = [parsed]
    findings = []
    for index, item in enumerate(_objects(parsed, "array")):
        issues = _listed(item.get("issues"))
        if prompt_name == "table_semantics":
            issues += _listed(item.get("header_clarity_issues"))
        # Placeholder-only fields are the problem; that check lists no issues.
        if not issues and prompt_name != "placeholder_as_label":
            continue
        problem = "; ".join(str(issue) for issue in issues)
        findings.append((
            index,
            item,
            problem or str(item.get("reason") or "") or prompt_name,
            _first_text(item, _SCREEN_ONLY_ELEMENT_KEYS),
            str(item.get("location_hint") or ""),
        ))
    return findings


def normalize_prompt_response(
    prompt_name: str,
    raw_response: str,
    *,
    run_id: str,
    model: str,
    page_url: str,
) -> NormalizationResult:
    """Read one response with the tool's rules, without its filter or deduplication."""
    spec = _PROMPTS.get(prompt_name)
    if spec is None:
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="unknown_prompt",
            raw_response=raw_response,
            findings=(),
            error=(f"No fixed evaluation normalizer exists for {prompt_name!r}."),
        )
    try:
        # Parse exactly as the API's report does, so only responses it skips are unreadable.
        parsed = safe_parse_json(raw_response)
    except (json.JSONDecodeError, ValueError) as error:
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="malformed",
            raw_response=raw_response,
            findings=(),
            error=str(error),
        )
    normalizer = NORMALIZERS.get(prompt_name)
    try:
        if normalizer is None:
            sources = _screen_only_findings(prompt_name, parsed)
        else:
            sources = _tool_findings(normalizer, parsed, spec)
    except Exception as error:  # noqa: BLE001
        # A shape the check's rule cannot read is unreadable, not fatal to the run.
        return NormalizationResult(
            prompt=prompt_name,
            parse_status="malformed",
            raw_response=raw_response,
            findings=(),
            error=str(error) or type(error).__name__,
        )
    findings = []
    for position, source, problem, element, location in sources:
        canonical_source = json.dumps(
            source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = f"{run_id}\0{prompt_name}\0{position}\0{canonical_source}".encode()
        findings.append(
            CanonicalFinding(
                finding_id="llm-" + hashlib.sha256(identity).hexdigest()[:20],
                source="llm",
                run_id=run_id,
                model=model,
                prompt=prompt_name,
                checklist=spec.checklist,
                page_url=page_url,
                problem_family=prompt_name,
                problem=problem,
                element=element,
                location=location,
                wcag_evidence=tuple(spec.wcag_criteria),
                raw_source=source,
                parse_status="parsed",
                screen_only=normalizer is None,
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
