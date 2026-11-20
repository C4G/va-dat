"""Evaluation series: run one model N times on fixed snapshots and summarize the spread.

`run_series` builds (or reuses) the Human finding mapping, then runs N Full
evaluations, each followed by the matcher's review and reports. One cost limit
covers every request of every role. A run that fails for any reason (a request
failure, a failed review, or an unexpected error) is recorded as incomplete and
the series moves on; reaching the cost limit stops it. `series.json` is saved
after every step, and `report.html` summarizes the runs that completed, even
when the series stops early.
"""

from __future__ import annotations

import json
from collections.abc import Callable
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from vision_aid.evaluation.automated_review import AutomatedReviewer, reviewer_attribution
from vision_aid.evaluation.execution.llm_audit import (
    MODEL_PRESETS,
    USAGE_KEYS,
    evaluation_configuration,
    write_json,
)
from vision_aid.evaluation.execution.pricing import PriceSchedule, format_usd
from vision_aid.evaluation.full import (
    execute_full_evaluation,
    load_full_inputs,
    pooled_rows,
    prepare_full_evaluation,
)
from vision_aid.evaluation.human_finding_mapping import load_human_finding_mapping
from vision_aid.evaluation.mapper import PROMPT as MAPPER_PROMPT
from vision_aid.evaluation.mapper import build_human_finding_mapping
from vision_aid.evaluation.matcher import PROMPT as MATCHER_PROMPT
from vision_aid.evaluation.matcher import review_and_report
from vision_aid.evaluation.page import validated_page_review
from vision_aid.evaluation.reporting.html_report import (
    EXPECTED,
    display_model_name,
    render_report,
)
from vision_aid.evaluation.review import detection_counts
from vision_aid.evaluation.schemas import HumanAudit

MAPPING_FOLDER = "human-finding-mapping"
ROLES = ("mapper", "model", "matcher")
ROLE_LABELS = {"mapper": "Mapper", "model": "Model under test", "matcher": "Matcher"}


def saved_mapping(snapshots: Path) -> Path:
    """Return where `auto` keeps the mapping built from these snapshots."""
    return snapshots.parent / MAPPING_FOLDER / "human-finding-mapping.json"


@dataclass
class SeriesPlan:
    """What a series will do, settled before anything is spent.

    `mapper_model` is None when the mapping already exists.
    """

    human_audit: Path
    snapshots: Path
    mapping: Path
    model: str
    matcher_model: str
    mapper_model: str | None
    runs: int
    limit: Decimal


class _RunIncomplete(Exception):
    """The model under test did not finish every request of a run."""


class _Series:
    """The series folder and its series.json, saved after every change."""

    def __init__(self, directory: Path, plan: SeriesPlan):
        """Start the record for `plan` in `directory`."""
        self.directory = directory
        self.spent = Decimal(0)
        self.completed: list[dict[str, Any]] = []
        self.record: dict[str, Any] = {
            "series_id": directory.name,
            "model": evaluation_configuration(MODEL_PRESETS[plan.model]),
            "reviewers": {
                "mapper": reviewer_attribution(plan.mapper_model, MAPPER_PROMPT)
                if plan.mapper_model else None,
                "matcher": reviewer_attribution(plan.matcher_model, MATCHER_PROMPT),
                "human_finding_mapping_approved_by": None,
            },
            "runs_requested": plan.runs,
            "completed": 0,
            "max_cost_usd": str(plan.limit),
            "estimated_cost_usd": "0",
            "cost_by_role": {
                role: {"estimated_cost_usd": "0", "usage": {key: 0 for key in USAGE_KEYS}}
                for role in ROLES
            },
            "snapshots": str(plan.snapshots.resolve()),
            "human_finding_mapping": str(plan.mapping.resolve()),
            "human_finding_mapping_built": plan.mapper_model is not None,
            "runs": [],
            "stopped_reason": None,
        }
        self.save()

    def add_cost(self, role: str, cost: Decimal | str, usage: dict[str, int]) -> None:
        """Add one step's cost and token usage to `role` and the total, and save."""
        entry = self.record["cost_by_role"][role]
        entry["estimated_cost_usd"] = format_usd(Decimal(entry["estimated_cost_usd"]) + Decimal(cost))
        for key in USAGE_KEYS:
            entry["usage"][key] += usage[key]
        self.spent += Decimal(cost)
        self.record["estimated_cost_usd"] = format_usd(self.spent)
        self.save()

    def save(self) -> None:
        """Write series.json."""
        write_json(self.directory / "series.json", self.record)


def _new_run(series: Path) -> Path:
    """Create a fresh run folder under the series' runs/ folder."""
    run = series / "runs" / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    )
    run.mkdir(parents=True)
    return run


def _completed_rows(run: Path) -> list[dict[str, Any]]:
    """Return a reported run's pooled rows, one per original Human finding."""
    manifest = json.loads((run / "full.json").read_text())
    original = json.loads((run / "human-findings.json").read_text())
    reviews = [validated_page_review(run / page["run_dir"]) for page in manifest["pages"]]
    return pooled_rows(original["human_findings"], manifest["pages"], reviews)


def run_series(
    directory: Path, plan: SeriesPlan, api_keys: dict[str, str],
    schedule: PriceSchedule,
) -> dict[str, Any]:
    """Run the series in `directory` and return series.json's contents.

    `api_keys` maps each needed provider to its key. Writes series.json after
    every step and report.html at the end, even when no run completed or an
    error stops the series.
    """
    series = _Series(directory, plan)
    try:
        _run(series, plan, api_keys, schedule)
    finally:
        series.save()
        _write_report(directory, series.record, series.completed)
    return series.record


def _run(
    series: _Series, plan: SeriesPlan, api_keys: dict[str, str], schedule: PriceSchedule,
) -> None:
    """Build or load the mapping, then run until N runs are tried or the limit is reached."""
    record = series.record

    def key(model: str) -> str:
        """Return the API key for `model`'s provider."""
        return api_keys[evaluation_configuration(MODEL_PRESETS[model])["provider"]]

    if plan.mapper_model:
        mapper = AutomatedReviewer(
            "mapper", plan.mapper_model, MAPPER_PROMPT, key(plan.mapper_model),
            schedule, plan.limit,
        )
        try:
            build_human_finding_mapping(
                plan.human_audit, plan.snapshots, plan.mapping.parent, mapper, plan.mapping,
            )
        except Exception as error:
            record["stopped_reason"] = f"Human finding mapping not built: {error}"
            return
        finally:
            series.add_cost("mapper", mapper.estimated_cost, mapper.usage)

    audits, snapshots = load_full_inputs(plan.human_audit, plan.snapshots)
    mapping = load_human_finding_mapping(
        plan.mapping, next(iter(audits.values())).human_audit_sha256,
    )
    record["reviewers"]["human_finding_mapping_approved_by"] = mapping["approved_by"]
    for _ in range(plan.runs):
        if plan.limit - series.spent <= 0:
            break
        run = _new_run(series.directory)
        entry: dict[str, Any] = {
            "run_id": run.name, "run_dir": f"runs/{run.name}",
            "status": "incomplete", "reason": None, "counts": None,
        }
        record["runs"].append(entry)
        series.save()
        try:
            rows = _run_once(series, plan, run, audits, snapshots, mapping, key, schedule)
        except Exception as error:
            # Any failure costs this run only; the cost limit check above stops the series.
            entry["reason"] = str(error)
        else:
            entry.update(status="complete", counts=detection_counts(rows))
            series.completed.append({"run_id": run.name, "rows": rows})
            record["completed"] = len(series.completed)
        series.save()
    if series.spent >= plan.limit and record["completed"] < plan.runs:
        record["stopped_reason"] = "cost limit reached"


def _run_once(
    series: _Series, plan: SeriesPlan, run: Path,
    audits: dict[str, HumanAudit], snapshots: dict[str, Path],
    mapping: dict[str, Any], key: Callable[[str], str], schedule: PriceSchedule,
) -> list[dict[str, Any]]:
    """Prepare, execute, review and report one run, adding each role's cost.

    Returns the run's pooled rows; raises on any failure.
    """
    request_config = MODEL_PRESETS[plan.model]
    manifest = prepare_full_evaluation(
        run, audits, snapshots, request_config, plan.limit - series.spent, mapping,
    )
    try:
        finished = execute_full_evaluation(run, manifest, key(plan.model), request_config)
    finally:
        series.add_cost("model", manifest["estimated_cost_usd"], manifest["usage"])
    if not finished:
        raise _RunIncomplete(f"run incomplete: {manifest['incomplete_reason']}")
    matcher = AutomatedReviewer(
        "matcher", plan.matcher_model, MATCHER_PROMPT, key(plan.matcher_model),
        schedule, plan.limit, series.spent,
    )
    try:
        review_and_report(run, matcher)
    finally:
        series.add_cost("matcher", matcher.estimated_cost, matcher.usage)
    return _completed_rows(run)


def _spread(values: list[float]) -> dict[str, str]:
    """Return mean, min, max and sample standard deviation as percentages."""
    if not values:
        return {name: "Not defined" for name in ("mean", "min", "max", "stdev")}
    return {
        "mean": f"{statistics.mean(values):.1f}%",
        "min": f"{min(values):.1f}%",
        "max": f"{max(values):.1f}%",
        "stdev": f"{statistics.stdev(values):.1f} points" if len(values) > 1
        else "Not defined: one run",
    }


def _write_report(directory: Path, record: dict[str, Any], completed: list[dict]) -> None:
    """Write the series report.html from series.json and the completed runs' rows."""
    rates = []
    for kind, label in (("llm", "LLM"), ("overall", "Overall")):
        values = [
            run["counts"][kind]["caught"] / run["counts"][kind]["eligible"] * 100
            for run in record["runs"]
            if run["status"] == "complete" and run["counts"][kind]["eligible"]
        ]
        rates.append({"label": label, **_spread(values)})
    first = next((run["counts"] for run in record["runs"] if run["status"] == "complete"), None)
    programmatic = None
    if first:
        caught, eligible = first["programmatic"]["caught"], first["programmatic"]["eligible"]
        programmatic = f"{caught} caught / {eligible} eligible" + (
            f"; {caught / eligible * 100:.1f}%" if eligible else "; not defined"
        )
    findings: dict[str, dict[str, Any]] = {}
    for run in completed:
        for row in run["rows"]:
            human = row["human_finding"]
            item = findings.setdefault(human["human_finding_id"], {
                "human": human, "expected": EXPECTED[row["decision"]["classification"]],
                "caught": 0, "llm": 0,
            })
            item["caught"] += any(row["matches"].values())
            item["llm"] += bool(row["matches"]["llm"])
    reviewers = record["reviewers"]
    render_report(directory / "report.html", "series.html.jinja", {
        "title": "Evaluation Series",
        "model_name": display_model_name(record["model"]["model"]),
        "record": record,
        "reviewer": "; ".join(
            f"{name} {value}" for name, value in (
                ("mapping approved by", reviewers["human_finding_mapping_approved_by"]),
                ("matcher", reviewers["matcher"]),
            ) if value
        ),
        "rates": rates,
        "programmatic": programmatic,
        "findings": sorted(findings.values(), key=lambda item: item["human"]["source_row"]),
        "completed": len(completed),
        "costs": [
            {"role": ROLE_LABELS[role], **record["cost_by_role"][role]} for role in ROLES
        ],
    })
