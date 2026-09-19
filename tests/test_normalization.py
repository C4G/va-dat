import json

import pytest

from processing_scripts.llm.registry import PROMPT_REGISTRY
from vision_aid.evaluation.normalization import (
    normalize_programmatic_findings,
    normalize_prompt_response,
)


@pytest.mark.parametrize(
    "prompt_name,output_type",
    [(spec.name, spec.output_type) for spec in PROMPT_REGISTRY if not spec.is_summary],
)
def test_every_active_prompt_has_a_lossless_normalizer(
    prompt_name: str,
    output_type: str,
) -> None:
    item = {
        "problem": "Synthetic accessibility failure",
        "location": "hero image",
        "element": "img.hero",
        "wcag": ["1.1.1"],
        "recommended_fix": "Synthetic fix retained as evidence",
    }
    response = item if output_type == "object" else [item]

    result = normalize_prompt_response(
        prompt_name,
        json.dumps(response),
        run_id="run-1",
        model="gpt-5.6-luna",
        page_url="https://example.test/",
    )

    assert result.parse_status == "parsed"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.prompt == prompt_name
    assert finding.raw_source == item
    assert finding.problem == "Synthetic accessibility failure"
    assert finding.location == "hero image"
    assert finding.wcag_evidence == ("1.1.1",)


def test_normalization_records_fenced_empty_malformed_and_unknown_responses() -> None:
    fenced = normalize_prompt_response(
        "link_clarity",
        '```json\n[{"issue": "Unclear link", "text": "Read more"}]\n```',
        run_id="run-1",
        model="gpt-5.6-luna",
        page_url="https://example.test/",
    )
    empty = normalize_prompt_response(
        "link_clarity",
        "[]",
        run_id="run-1",
        model="gpt-5.6-luna",
        page_url="https://example.test/",
    )
    malformed = normalize_prompt_response(
        "link_clarity",
        "successful but not JSON",
        run_id="run-1",
        model="gpt-5.6-luna",
        page_url="https://example.test/",
    )
    unknown = normalize_prompt_response(
        "invented_prompt",
        "[]",
        run_id="run-1",
        model="gpt-5.6-luna",
        page_url="https://example.test/",
    )

    assert fenced.parse_status == "parsed"
    assert empty.parse_status == "empty"
    assert malformed.parse_status == "malformed"
    assert malformed.findings == ()
    assert malformed.raw_response == "successful but not JSON"
    assert unknown.parse_status == "unknown_prompt"


def test_programmatic_normalization_retains_rule_and_raw_source() -> None:
    raw = {
        "rule_id": "HEAD_002",
        "message": "Multiple H1 elements",
        "element": "<h1>Second</h1>",
        "location": "line 20",
        "wcag": "1.3.1",
    }

    findings = normalize_programmatic_findings(
        [raw],
        run_id="run-1",
        page_url="https://example.test/",
    )

    assert findings[0].source == "programmatic"
    assert findings[0].problem_family == "HEAD_002"
    assert findings[0].raw_source == raw
