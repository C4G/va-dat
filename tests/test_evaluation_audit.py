import hashlib
import json
from pathlib import Path

import pytest

from vision_aid.evaluation.audit import (
    AuditExecutionError,
    build_audit_plan,
    execute_authorized_audit,
    live_authorization_digest,
)
from vision_aid.evaluation.pricing import PriceSchedule


def _fake_pipeline(
    html_path: str,
    output_dir: Path,
    api_key: str | None,
    model: str,
    dry_run: bool,
    include_summaries: bool,
    progress_callback=None,
    request_config=None,
) -> dict:
    """Write two deterministic prompt artifacts through the adapter seam."""
    assert api_key is None
    assert dry_run is True
    assert include_summaries is False
    assert model == "gpt-5.6-luna"
    assert request_config.reasoning_effort == "medium"
    assert request_config.temperature is None
    assert request_config.max_output_tokens == 8192
    prompts = output_dir / "prompts"
    prompts.mkdir(parents=True)
    entries = []
    for index, name in enumerate(
        ("heading_structure", "link_clarity"), start=1
    ):
        prompt_text = f"prompt {index}"
        (prompts / f"{name}.json").write_text(
            json.dumps(
                {
                    "prompt_name": name,
                    "checklist": "CL01",
                    "wcag_criteria": ["1.3.1"],
                    "prompt_index": index,
                    "prompt_tokens_est": 10 * index,
                    "prompt_text": prompt_text,
                    "payload_slice": "{}",
                }
            ),
            encoding="utf-8",
        )
        entries.append(
            {
                "name": name,
                "checklist": "CL01",
                "wcag_criteria": ["1.3.1"],
                "prompt_tokens_est": 10 * index,
                "status": "dry_run",
            }
        )
    (output_dir / "programmatic_findings.json").write_text(
        "[]", encoding="utf-8"
    )
    return {
        "html_file": html_path,
        "model": model,
        "dry_run": True,
        "include_summaries": False,
        "prompts_dry_run": entries,
        "prompts_executed": [],
        "prompts_skipped": [],
        "pass1_filters_active": [],
    }


def test_dry_plan_freezes_configuration_content_and_code_identities(
    tmp_path: Path,
) -> None:
    """A dry plan records the complete frozen benchmark configuration."""
    snapshot = tmp_path / "source.html"
    snapshot.write_text(
        "<html><title>Synthetic</title></html>", encoding="utf-8"
    )
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    run_directory = tmp_path / "run"

    plan = build_audit_plan(
        snapshot,
        run_directory,
        workbook_sha256="a" * 64,
        snapshot_sha256=snapshot_sha256,
        reference_set_version="references-v1",
        eligibility_identity="c" * 64,
        pipeline=_fake_pipeline,
        repository=tmp_path,
    )

    assert plan["configuration"] == {
        "endpoint": "chat.completions",
        "include_summaries": False,
        "max_output_tokens": 8192,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "medium",
        "temperature": None,
        "execution": "sequential",
    }
    assert plan["request_count"] == 2
    assert plan["estimated_input_tokens"] == 30
    assert list(plan["prompt_hashes"]) == ["heading_structure", "link_clarity"]
    assert len(plan["parser_hash"]) == 64
    assert len(plan["pricing_identity"]) == 64
    assert len(plan["plan_digest"]) == 64
    assert (run_directory / "evaluation-manifest.json").is_file()


class FakeClient:
    def __init__(self, outcomes: list[dict]):
        """Queue provider outcomes in request order."""
        self.outcomes = outcomes

    def call(self, prompt: str) -> dict:
        """Return the next provider outcome without network access."""
        return self.outcomes.pop(0)


def _success(
    response: str, input_tokens: int = 10, output_tokens: int = 5
) -> dict:
    """Return one successful synthetic provider result."""
    return {
        "success": True,
        "response": response,
        "model": "gpt-5.6-luna",
        "provider": {"name": "openai", "endpoint": "chat.completions"},
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": 0,
            "output_tokens": output_tokens,
            "reasoning_tokens": 2,
            "cache_creation_input_tokens": 0,
            "total_tokens": input_tokens + output_tokens,
            "provider_usage": {},
        },
        "stop_reason": "stop",
        "duration_seconds": 0.2,
        "failure": None,
    }


def _transient() -> dict:
    """Return one billed, retryable rate-limit result."""
    return {
        "success": False,
        "response": None,
        "model": "gpt-5.6-luna",
        "provider": {"name": "openai", "endpoint": "chat.completions"},
        "usage": {
            "input_tokens": 2,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cache_creation_input_tokens": 0,
            "total_tokens": 2,
            "provider_usage": {},
        },
        "stop_reason": None,
        "duration_seconds": 0.1,
        "failure": {"type": "RateLimitError", "status_code": 429},
        "error": "rate limited",
    }


def _permanent(status_code: int, failure_type: str) -> dict:
    """Return an unbilled provider rejection that must not be retried."""
    result = _transient()
    result["usage"]["input_tokens"] = 0
    result["usage"]["total_tokens"] = 0
    result["failure"] = {
        "type": failure_type,
        "status_code": status_code,
    }
    return result


def test_live_gates_retries_and_format_failures(
    tmp_path: Path,
) -> None:
    """A live run enforces gates and preserves retries and malformed output."""
    snapshot = tmp_path / "source.html"
    snapshot.write_text("<html></html>", encoding="utf-8")
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    run_directory = tmp_path / "run"
    plan = build_audit_plan(
        snapshot,
        run_directory,
        workbook_sha256="a" * 64,
        snapshot_sha256=snapshot_sha256,
        reference_set_version="references-v1",
        eligibility_identity="c" * 64,
        pipeline=_fake_pipeline,
        repository=tmp_path,
    )
    plan_path = run_directory / "evaluation-manifest.json"
    authorization = live_authorization_digest(plan["plan_digest"], "1")

    with pytest.raises(AuditExecutionError, match="--live"):
        execute_authorized_audit(
            plan_path,
            live=False,
            authorization=authorization,
            api_key="secret",
            max_audit_cost_usd="1",
            client=FakeClient([]),
            sleep=lambda _delay: None,
        )
    with pytest.raises(AuditExecutionError, match="authorization"):
        execute_authorized_audit(
            plan_path,
            live=True,
            authorization="wrong",
            api_key="secret",
            max_audit_cost_usd="1",
            client=FakeClient([]),
            sleep=lambda _delay: None,
        )

    client = FakeClient(
        [
            _transient(),
            _success('[{"problem":"Heading skips a level"}]'),
            _success("not json"),
        ]
    )
    manifest = execute_authorized_audit(
        plan_path,
        live=True,
        authorization=authorization,
        api_key="secret",
        max_audit_cost_usd="1",
        client=client,
        sleep=lambda _delay: None,
    )

    assert manifest["complete"] is True
    assert manifest["rankable"] is True
    assert len(manifest["requests"][0]["attempts"]) == 2
    assert manifest["format_failures"] == ["link_clarity"]
    assert manifest["usage"]["input_tokens"] == 22
    assert manifest["estimated_audit_cost_usd"] == "0.0000164"
    assert manifest["configuration"]["temperature"] is None
    raw_attempts = json.loads(
        (run_directory / "raw-attempts.json").read_text(encoding="utf-8")
    )
    assert len(raw_attempts["requests"][0]["attempts"]) == 2

    with pytest.raises(AuditExecutionError, match="already been used"):
        execute_authorized_audit(
            plan_path,
            live=True,
            authorization=authorization,
            api_key="secret",
            max_audit_cost_usd="1",
            client=FakeClient([]),
            sleep=lambda _delay: None,
        )


def test_cost_guard_is_checked_before_each_retry(tmp_path: Path) -> None:
    """A billed failure can exhaust the limit before an automatic retry."""
    snapshot = tmp_path / "source.html"
    snapshot.write_text("<html></html>", encoding="utf-8")
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    run_directory = tmp_path / "run"
    plan = build_audit_plan(
        snapshot,
        run_directory,
        workbook_sha256="a" * 64,
        snapshot_sha256=snapshot_sha256,
        reference_set_version="references-v1",
        eligibility_identity="c" * 64,
        pipeline=_fake_pipeline,
        repository=tmp_path,
    )
    limit = "0.0000001"
    client = FakeClient([_transient(), _success("[]")])

    manifest = execute_authorized_audit(
        run_directory / "evaluation-manifest.json",
        live=True,
        authorization=live_authorization_digest(plan["plan_digest"], limit),
        api_key="secret",
        max_audit_cost_usd=limit,
        client=client,
        sleep=lambda _delay: None,
    )

    assert manifest["complete"] is False
    assert manifest["incomplete_reason"] == "audit_cost_limit_exhausted"
    assert len(manifest["requests"]) == 1
    assert len(manifest["requests"][0]["attempts"]) == 1
    assert len(client.outcomes) == 1


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (_permanent(401, "AuthenticationError"), "authentication"),
        (_permanent(400, "BadRequestError"), "invalid_request"),
    ],
)
def test_permanent_provider_failures_are_not_retried(
    tmp_path: Path,
    outcome: dict,
    expected: str,
) -> None:
    """Authentication and invalid requests stop after one recorded attempt."""
    snapshot = tmp_path / "source.html"
    snapshot.write_text("<html></html>", encoding="utf-8")
    run_directory = tmp_path / "run"
    plan = build_audit_plan(
        snapshot,
        run_directory,
        workbook_sha256="a" * 64,
        snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        reference_set_version="references-v1",
        eligibility_identity="c" * 64,
        pipeline=_fake_pipeline,
        repository=tmp_path,
    )
    client = FakeClient([outcome, _success("[]")])

    manifest = execute_authorized_audit(
        run_directory / "evaluation-manifest.json",
        live=True,
        authorization=live_authorization_digest(plan["plan_digest"], "1"),
        api_key="secret",
        max_audit_cost_usd="1",
        client=client,
        sleep=lambda _delay: None,
    )

    assert manifest["incomplete_reason"] == expected
    assert len(manifest["requests"][0]["attempts"]) == 1
    assert len(client.outcomes) == 1


def test_exhausted_transient_failures_make_the_run_unranked(
    tmp_path: Path,
) -> None:
    """Record three transient attempts before marking the run incomplete."""
    snapshot = tmp_path / "source.html"
    snapshot.write_text("<html></html>", encoding="utf-8")
    run_directory = tmp_path / "run"
    plan = build_audit_plan(
        snapshot,
        run_directory,
        workbook_sha256="a" * 64,
        snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        reference_set_version="references-v1",
        eligibility_identity="c" * 64,
        pipeline=_fake_pipeline,
        repository=tmp_path,
    )

    manifest = execute_authorized_audit(
        run_directory / "evaluation-manifest.json",
        live=True,
        authorization=live_authorization_digest(plan["plan_digest"], "1"),
        api_key="secret",
        max_audit_cost_usd="1",
        client=FakeClient([_transient(), _transient(), _transient()]),
        sleep=lambda _delay: None,
    )

    assert manifest["complete"] is False
    assert manifest["rankable"] is False
    assert manifest["incomplete_reason"] == "transient_failures_exhausted"
    assert len(manifest["requests"][0]["attempts"]) == 3


def test_versioned_price_schedule_uses_reported_token_categories() -> None:
    """Pricing distinguishes uncached, cached, written, and output tokens."""
    schedule = PriceSchedule.default()
    assert (
        schedule.estimate(
            "gpt-5.6-luna",
            {
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "cache_creation_input_tokens": 20,
                "output_tokens": 10,
                "reasoning_tokens": 5,
            },
        )
        == "0.0000298"
    )
