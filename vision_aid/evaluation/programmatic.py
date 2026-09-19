"""Adapter around the production programmatic accessibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from processing_scripts.programmatic.forms_checklist_02 import audit_forms
from processing_scripts.programmatic.nontext_checklist_03 import audit_nontext
from processing_scripts.programmatic.semantic_checklist_01 import (
    audit_html_file,
)
from vision_aid.evaluation.normalization import normalize_programmatic_findings
from vision_aid.evaluation.schemas import CanonicalFinding


@dataclass(frozen=True)
class ProgrammaticAudit:
    """Raw checker evidence and its canonical comparison records."""

    raw_findings: tuple[dict[str, Any], ...]
    findings: tuple[CanonicalFinding, ...]


def run_programmatic_audit(
    html_path: Path,
    *,
    run_id: str,
    page_url: str,
) -> ProgrammaticAudit:
    """Run the existing three checker entry points against a benchmark file."""
    path = str(html_path)
    raw = tuple(
        audit_html_file(path) + audit_forms(path) + audit_nontext(path)
    )
    return ProgrammaticAudit(
        raw_findings=raw,
        findings=normalize_programmatic_findings(
            raw,
            run_id=run_id,
            page_url=page_url,
        ),
    )
