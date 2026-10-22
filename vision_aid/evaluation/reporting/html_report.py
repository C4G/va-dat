"""Prepare reader-facing data and publish self-contained evaluation reports."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from vision_aid.evaluation.review import detection_counts

if TYPE_CHECKING:
    from vision_aid.evaluation.execution.pricing import PriceSchedule
    from vision_aid.evaluation.page import PageReview

EXPECTED = {
    "llm_eligible": "LLM",
    "programmatic": "Programmatic checks",
    "unavailable_evidence": "Not testable from the page file",
    "ambiguous": "Not testable from the page file",
}


def _display_model(model: str) -> str:
    """Use uppercase GPT in report labels while preserving saved model IDs."""
    return "GPT-" + model[4:].replace("-", " ").title() if model.startswith("gpt-") else model


def _cost_details(manifest: dict[str, Any], schedules: list[PriceSchedule]) -> dict[str, Any]:
    """Present saved usage and model prices without recalculating the run cost."""
    usage = manifest["usage"]
    model = manifest["configuration"].get("model")
    if model is None:
        raise ValueError("Cannot render complete report: model is missing")
    token_usage = [
        {"label": label, "count": f"{usage[key]:,}"}
        for key, label in (
            ("input_tokens", "Input tokens"),
            ("output_tokens", "Output tokens"),
            ("cached_input_tokens", "Cached input tokens"),
            ("cache_creation_input_tokens", "Cache-write input tokens"),
        )
        if key in {"input_tokens", "output_tokens"} or usage[key]
    ]
    model_prices = []
    seen = set()
    for schedule in schedules:
        if schedule.identity in seen:
            continue
        seen.add(schedule.identity)
        rates = schedule.data["models"][model]
        upper = rates.get("long_context")
        tiers = [{"label": "All requests", "rates": rates}]
        if upper:
            threshold = f"{upper['above_input_tokens']:,}"
            tiers = [
                {"label": f"Up to {threshold}", "rates": rates},
                {"label": f"Over {threshold}", "rates": upper},
            ]
        model_prices.append({
            "model": _display_model(model), "description": schedule.price_description,
            "tiers": tiers,
            "show_cache_read": bool(usage["cached_input_tokens"]),
            "show_cache_write": bool(usage["cache_creation_input_tokens"]),
        })
    return {
        "cost": f"{Decimal(manifest['estimated_cost_usd']):.6f}",
        "model_name": _display_model(model),
        "token_usage": token_usage, "model_prices": model_prices,
    }


def _chart_rates(counts: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Prepare chart labels and widths from the existing deterministic counts."""
    rates = []
    for kind, label in (
        ("llm", "LLM"),
        ("programmatic", "Programmatic"),
        ("overall", "Overall"),
    ):
        caught, eligible = counts[kind]["caught"], counts[kind]["eligible"]
        percentage = f"{caught / eligible * 100:.1f}" if eligible else None
        rates.append({
            "label": label, **counts[kind],
            "bar_percent": percentage,
            "percentage": percentage + "%" if percentage is not None else (
                "Not defined: no imported Human findings" if kind == "overall"
                else "Not defined: no eligible Human findings"
            ),
        })
    return rates


def page_data(review: PageReview, reviewer: str) -> dict[str, Any]:
    """Resolve validated evidence and deterministic scores before rendering."""
    manifest = review.manifest
    findings = {item["finding_id"]: item for item in review.llm + review.programmatic}
    counts = detection_counts(review.rows)
    rows = []
    for row in review.rows:
        human, decision = row["human_finding"], row["decision"]
        classification = decision["classification"].strip()
        matched = []
        for kind in ("llm", "programmatic"):
            for identity in row["matches"][kind]:
                finding = findings[identity]
                check = finding["prompt"].replace("_", " ") + " check"
                if finding.get("screen_only"):
                    check += "; shown on screen only, not in the tool's CSV report"
                matched.append(
                    {
                        "id": finding["finding_id"],
                        "source": "LLM" if kind == "llm" else "Programmatic checks",
                        "check": check,
                        "check_id": finding["prompt"],
                        "checklist": finding["checklist"],
                        "problem": finding["problem"],
                        "element": finding["element"],
                        "location": finding["location"],
                    }
                )
        rows.append(
            {
                "human": human,
                "baseline_approved_by": manifest.get("evaluation_baseline_approved_by"),
                "decision": decision,
                "source_url": manifest["source_url"],
                "run_id": manifest["run_id"],
                "expected": EXPECTED[classification],
                "llm_outcome": "Caught" if row["matches"]["llm"] else "Not caught",
                "programmatic_outcome": "Caught"
                if row["matches"]["programmatic"]
                else "Not caught",
                "matched": matched,
            }
        )
    rates = _chart_rates(counts)
    return {
        "title": "LLM Accessibility Evaluation",
        "manifest": manifest,
        "reviewer": reviewer,
        "rows": rows,
        "rates": rates,
        **_cost_details(manifest, [review.schedule]),
    }


def full_data(
    manifest: dict[str, Any], pooled: list[dict[str, Any]],
    reviews: list[PageReview], reviewer: str,
) -> dict[str, Any]:
    """Combine validated presentation rows without changing pooled scoring."""
    pages = [page_data(review, reviewer) for review in reviews]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        for row in page["rows"]:
            grouped.setdefault(row["human"]["human_finding_id"], []).append({
                **row, "source_url": page["manifest"]["source_url"],
                "run_id": page["manifest"]["run_id"],
            })
    counts = detection_counts(pooled)
    rows = []
    for row in pooled:
        rows.append({
            "human": row["human_finding"],
            "expected": EXPECTED[row["decision"]["classification"]],
            "llm_outcome": "Caught" if row["matches"]["llm"] else "Not caught",
            "programmatic_outcome": "Caught" if row["matches"]["programmatic"] else "Not caught",
            "pages": grouped[row["human_finding"]["human_finding_id"]],
        })
    return {
        "title": "Full Accessibility Evaluation", "full": True,
        "manifest": manifest, "reviewer": reviewer, "rows": rows, "pages": pages,
        "rates": _chart_rates(counts),
        **_cost_details(manifest, [review.schedule for review in reviews]),
    }


def write_full_report(
    path: Path, manifest: dict[str, Any], pooled: list[dict[str, Any]],
    reviews: list[PageReview], reviewer: str,
) -> None:
    """Render every accepted page decision into the standalone parent."""
    _write_html(path, "full.html.jinja", full_data(manifest, pooled, reviews, reviewer))


def write_page_report(path: Path, review: PageReview, reviewer: str) -> None:
    """Publish a standalone individual Evaluation report."""
    _write_html(path, "page.html.jinja", page_data(review, reviewer))


def _write_html(path: Path, template: str, data: dict[str, Any]) -> None:
    """Render completely, then atomically replace the report in its directory."""
    environment = Environment(
        loader=PackageLoader("vision_aid.evaluation.reporting", "templates"),
        autoescape=select_autoescape(("html.jinja",)),
        undefined=StrictUndefined,
    )
    # Only trusted package assets bypass escaping; review data stays escaped.
    assets = files("vision_aid.evaluation.reporting")
    styles = "".join(
        assets.joinpath("css", name).read_text(encoding="utf-8")
        for name in ("report.css", "charts.css", "print.css")
    )
    scripts = {
        name: assets.joinpath("js", f"{name}.js").read_text(encoding="utf-8")
        for name in ("filters", "print")
    }
    try:
        content = environment.get_template(template).render(
            **data, styles=styles, scripts=scripts,
        )
    except TemplateError as error:
        raise ValueError(f"Cannot render complete report: {error}") from error
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
