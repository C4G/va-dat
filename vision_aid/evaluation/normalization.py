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
_EXPLICIT_PROBLEM_KEYS = (
    "problem",
    "issue",
    "issue_title",
    "description",
    "finding",
    "actual_result",
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
    """Remove one optional Markdown JSON fence."""
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", value, re.DOTALL)
    return match.group(1) if match else value.strip()


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


def _items(parsed: Any, spec: PromptSpec) -> list[dict[str, Any]] | None:
    """Return source finding objects from either supported JSON shape."""
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return None
    for key in ("findings", "violations", "results"):
        nested = parsed.get(key)
        if isinstance(nested, list) and all(isinstance(item, dict) for item in nested):
            return [item for item in nested if isinstance(item, dict)]
    return [parsed] if parsed else []


def _has_values(value: Any) -> bool:
    """Treat non-empty strings, mappings, and sequences as evidence."""
    return value not in (None, "", [], {}, ())


def _is_failure(prompt: str, item: dict[str, Any]) -> bool:
    """Apply the fixed failure predicate for one active prompt category."""
    if any(_has_values(item.get(key)) for key in _EXPLICIT_PROBLEM_KEYS):
        return True
    if _has_values(item.get("issues")):
        return True
    if prompt == "page_title":
        return item.get("is_descriptive") is False or item.get("matches_h1") is False
    if prompt == "heading_structure":
        return item.get("structure_clear") is False or _has_values(
            item.get("vague_headings")
        )
    if prompt == "link_clarity":
        return item.get("is_clear") is False
    if prompt == "table_semantics":
        return item.get("caption_clear") is False or _has_values(
            item.get("header_clarity_issues")
        )
    if prompt == "iframe_titles":
        return item.get("is_descriptive") is False
    if prompt == "landmark_structure":
        return item.get("structure_appropriate") is False
    if prompt == "label_quality":
        return item.get("is_descriptive") is False
    if prompt == "placeholder_as_label":
        return True
    if prompt == "group_labels":
        return item.get("legend_is_meaningful") is False
    if prompt == "required_field_indicators":
        return (
            item.get("requirement_in_label") is False
            and item.get("requirement_in_instructions") is False
        )
    if prompt == "form_instructions":
        return item.get("instructions_are_helpful") is False
    if prompt == "informative_alt_quality":
        return item.get("quality") == "poor"
    if prompt == "decorative_verification":
        return item.get("likely_decorative") is False
    if prompt == "actionable_image_alt":
        return item.get("describes_action_not_appearance") is False
    if prompt == "complex_descriptions":
        return item.get("alt_is_sufficient") is False or (
            item.get("long_description_needed") is True
            and item.get("long_description_adequate") is not True
        )
    if prompt == "svg_accessibility":
        return (
            item.get("has_accessible_name") is False
            or item.get("title_is_meaningful") is False
        )
    if prompt == "icon_font_accessibility":
        return item.get("pattern") in {"unlabeled_control", "missing_label"}
    if prompt == "media_captions":
        return (
            item.get("has_captions_track") is False or item.get("has_controls") is False
        )
    return False


def _problem(item: dict[str, Any], prompt_name: str) -> str:
    """Choose a readable problem statement while retaining the raw object."""
    explicit = _first_text(item, _EXPLICIT_PROBLEM_KEYS)
    if explicit:
        return explicit
    issues = item.get("issues")
    if isinstance(issues, list) and issues:
        return "; ".join(str(value) for value in issues)
    return _first_text(item, ("reason", "summary")) or prompt_name


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
            error=(f"No fixed evaluation normalizer exists for {prompt_name!r}."),
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
        if not _is_failure(prompt_name, item):
            continue
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
                problem=_problem(item, prompt_name),
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
