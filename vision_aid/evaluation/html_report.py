"""Prepare reader-facing data and publish self-contained evaluation reports."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from vision_aid.evaluation.review import _rate, _usage_description, detection_counts

if TYPE_CHECKING:
    from vision_aid.evaluation.page import PageReview

EXPECTED = {
    "llm_eligible": "LLM",
    "programmatic": "Programmatic checks",
    "unavailable_evidence": "Not testable from the page file",
    "ambiguous": "Not testable from the page file",
}


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
                        "page_url": finding["page_url"],
                        "run_id": finding["run_id"],
                        "element": finding["element"],
                        "location": finding["location"],
                    }
                )
        rows.append(
            {
                "human": human,
                "decision": decision,
                "expected": EXPECTED[classification],
                "llm_outcome": "Caught" if row["matches"]["llm"] else "Not caught",
                "programmatic_outcome": "Caught"
                if row["matches"]["programmatic"]
                else "Not caught",
                "matched": matched,
            }
        )
    rates = [
        {
            "label": label.removesuffix(" checks"),
            **counts[kind],
            "description": _rate(
                label, counts[kind]["caught"], counts[kind]["eligible"]
            ),
        }
        for kind, label in (
            ("llm", "LLM"),
            ("programmatic", "Programmatic checks"),
            ("overall", "Overall"),
        )
    ]
    return {
        "title": "LLM accessibility evaluation",
        "manifest": manifest,
        "reviewer": reviewer,
        "rows": rows,
        "rates": rates,
        "cost": f"{Decimal(manifest['estimated_cost_usd']):.2f}",
        "pricing_description": review.schedule.price_description,
        "pricing_identity": review.schedule.identity,
        "pricing_version": review.schedule.version,
        "pricing_sources": review.schedule.data.get(
            "sources",
            [review.schedule.data["source"]]
            if "source" in review.schedule.data
            else [],
        ),
        "usage_description": _usage_description(manifest["usage"]),
        "unreadable": len(manifest["format_failures"]),
        "prompts": len(manifest["prompts"]),
        "failed_checks": ", ".join(
            name.replace("_", " ") + " check" for name in manifest["format_failures"]
        ),
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
        "title": "Full accessibility evaluation", "full": True,
        "manifest": manifest, "reviewer": reviewer, "rows": rows, "pages": pages,
        "rates": [{
            "label": label.removesuffix(" checks"), **counts[kind],
            "description": _rate(label, counts[kind]["caught"], counts[kind]["eligible"]).replace(
                "the page's HTML", "the evaluated pages' HTML"),
        } for kind, label in (("llm", "LLM"), ("programmatic", "Programmatic checks"), ("overall", "Overall"))],
        "cost": f"{Decimal(manifest['estimated_cost_usd']):.2f}",
        "pricing_description": ", ".join(dict.fromkeys(page["pricing_description"] for page in pages)),
        "pricing_schedules": list({
            page["pricing_identity"]: {
                "version": page["pricing_version"], "identity": page["pricing_identity"],
                "sources": page["pricing_sources"],
            } for page in pages
        }.values()),
        "usage_description": _usage_description(manifest["usage"]),
        "unreadable": sum(page["unreadable"] for page in pages),
        "prompts": sum(page["prompts"] for page in pages),
    }


def write_full_report(
    path: Path, manifest: dict[str, Any], pooled: list[dict[str, Any]],
    reviews: list[PageReview], reviewer: str,
) -> None:
    """Render every accepted page decision into the standalone parent."""
    _write_html(path, "full.html", full_data(manifest, pooled, reviews, reviewer))


def write_page_report(path: Path, review: PageReview, reviewer: str) -> None:
    """Publish a standalone individual Evaluation report."""
    _write_html(path, "page.html", page_data(review, reviewer))


def _write_html(path: Path, template: str, data: dict[str, Any]) -> None:
    """Render completely, then atomically replace the report in its directory."""
    environment = Environment(
        loader=PackageLoader("vision_aid.evaluation", "templates"),
        autoescape=select_autoescape(("html",)),
        undefined=StrictUndefined,
    )
    try:
        content = environment.get_template(template).render(**data)
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
