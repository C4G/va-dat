"""Prepare readable audit decisions and export an approved Human finding mapping."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from processing_scripts.programmatic.forms_checklist_02 import audit_forms
from processing_scripts.programmatic.nontext_checklist_03 import audit_nontext
from processing_scripts.programmatic.semantic_checklist_01 import audit_html_file
from vision_aid.evaluation.execution.normalization import (
    normalize_programmatic_findings,
)
from vision_aid.evaluation.full import load_full_inputs
from vision_aid.evaluation.human_finding_mapping import (
    resolved_decisions,
    validate_human_finding_mapping,
)
from vision_aid.evaluation.inputs.human_audit import ELIGIBILITY_VALUES, HEADERS

IDENTITY_COLUMNS = (
    "human_finding_id",
    "source_sheet",
    "source_row",
    "page_scope",
    "source_element",
    *HEADERS,
)
CLASSIFICATION_COLUMNS = (*IDENTITY_COLUMNS, "classification", "classification_reason")
MATCH_COLUMNS = (
    "source_url",
    *IDENTITY_COLUMNS,
    "programmatic_finding_refs",
    "programmatic_reason",
)
FINDING_COLUMNS = (
    "finding_ref",
    "source_url",
    "rule",
    "problem",
    "element",
    "text",
    "target",
    "location",
)


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
    """Write a UTF-8 CSV that Excel can open with multiline evidence intact."""
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, restval="")
        writer.writeheader()
        writer.writerows(rows)


def _human_columns(finding: dict[str, Any]) -> dict[str, Any]:
    """Flatten original evidence beside generated identities for human review."""
    return {
        key: finding[key] for key in IDENTITY_COLUMNS if key not in HEADERS
    } | finding["raw_evidence"]


def prepare_human_finding_mapping_review(human_audit: Path, snapshots: Path, output: Path) -> None:
    """Run existing checks on saved pages and prepare two editable decision CSVs."""
    audits, html_files = load_full_inputs(human_audit, snapshots)
    output.mkdir(parents=True)
    (output / "snapshots").mkdir()
    originals = {}
    pages = []
    matches = []
    catalog = []
    for number, (url, audit) in enumerate(audits.items(), start=1):
        snapshot = f"snapshots/page-{number:03d}.html"
        saved = output / snapshot
        shutil.copyfile(html_files[url], saved)
        raw = (
            audit_html_file(str(saved))
            + audit_forms(str(saved))
            + audit_nontext(str(saved))
        )
        findings = normalize_programmatic_findings(
            raw, run_id="human-finding-mapping-review", page_url=url
        )
        evidence = {}
        for position, item in enumerate(findings, start=1):
            ref = f"P{number:03d}-F{position:03d}"
            finding = asdict(item)
            evidence[ref] = finding
            location = finding["raw_source"].get("location") or {}
            attributes = location.get("attributes") or {}
            catalog.append(
                {
                    "finding_ref": ref,
                    "source_url": url,
                    "rule": finding["problem_family"],
                    "problem": finding["problem"],
                    "element": location.get("tag", finding["element"]),
                    "text": location.get("text_preview")
                    or attributes.get("aria-label")
                    or attributes.get("alt")
                    or attributes.get("title", ""),
                    "target": location.get("href")
                    or location.get("src")
                    or attributes.get("id", ""),
                    "location": location.get("css_path", finding["location"]),
                }
            )
        humans = list(audit.to_dict()["human_findings"])
        for finding in humans:
            originals[finding["human_finding_id"]] = finding
            matches.append({"source_url": url, **_human_columns(finding)})
        pages.append(
            {
                "source_url": url,
                "snapshot": snapshot,
                "snapshot_sha256": hashlib.sha256(saved.read_bytes()).hexdigest(),
                "human_finding_ids": [
                    finding["human_finding_id"] for finding in humans
                ],
                "findings": evidence,
            }
        )
    humans = sorted(originals.values(), key=lambda finding: finding["source_row"])
    _write_csv(
        output / "classifications.csv",
        CLASSIFICATION_COLUMNS,
        [_human_columns(finding) for finding in humans],
    )
    _write_csv(output / "programmatic-review.csv", MATCH_COLUMNS, matches)
    _write_csv(output / "programmatic-findings.csv", FINDING_COLUMNS, catalog)
    evidence = {
        "schema_version": 1,
        "human_audit_filename": human_audit.name,
        "human_audit_sha256": next(iter(audits.values())).human_audit_sha256,
        "human_findings": humans,
        "pages": pages,
    }
    path = output / "evidence.json"
    path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "evidence.sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n", encoding="ascii"
    )
    (output / "README.md").write_text(
        "# Review the Human finding mapping\n\n"
        "1. Open classifications.csv in Excel or another CSV editor. For every original Human finding, "
        "fill classification and classification_reason. Classify each original once, including Globals. "
        "Use programmatic only when existing checker findings fully cover the reported defect; "
        "llm_eligible for semantic judgment or checks absent from existing rules; unavailable_evidence "
        "when saved HTML cannot establish the defect; ambiguous when the Human finding is unclear.\n\n"
        "2. Open programmatic-review.csv and programmatic-findings.csv side by side. "
        "For each Human finding and page, enter complete matching finding_ref values in "
        "programmatic_finding_refs, separated by semicolons, and explain them in programmatic_reason. "
        "Multiple selected findings must jointly cover the full defect. A shared WCAG criterion alone "
        "does not establish a match. Select only findings from that page, and use each reference once. "
        "Leave references blank for no complete match and explain the absence. Programmatic "
        "classifications require complete matches on every applicable page. Not-testable classifications "
        "cannot claim matches. LLM classifications may have Programmatic cross-catches.\n\n"
        "3. Save both edited files as CSV. Keep original evidence, IDs, headers, and every row unchanged. "
        "Row order may change. Inspect the copied snapshots when needed. The findings catalog is "
        "read-only reference material; editing it does not change saved checker evidence.\n\n"
        "4. Run visionaid-evaluate human-finding-mapping-approve --review-dir THIS_DIRECTORY "
        "--reviewer 'Your name'. The CLI validates the decisions and writes human-finding-mapping.json. "
        "Use that file with run or run-all --human-finding-mapping PATH. Approval records your decisions; it does "
        "not automatically judge whether the selected evidence semantically covers a defect.\n",
        encoding="utf-8",
    )


def _read_review(
    path: Path,
    columns: tuple[str, ...],
    expected: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> dict[tuple[str, ...], dict[str, str]]:
    """Accept reordered rows while rejecting missing rows and altered original evidence."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if len(reader.fieldnames or []) != len(columns) or set(
            reader.fieldnames or []
        ) != set(columns):
            raise ValueError(f"{path.name}: keep every original column exactly once")
        entered = list(reader)
    originals = {tuple(str(row[key]) for key in keys): row for row in expected}
    if len(entered) != len(originals):
        raise ValueError(f"{path.name}: keep every original review row exactly once")
    result = {}
    for line, row in enumerate(entered, start=2):
        key = tuple(row[column] for column in keys)
        if key not in originals or key in result:
            raise ValueError(
                f"{path.name} row {line}: unknown or repeated Human finding/page {key}"
            )
        if any(
            row.get(column) != str(value) for column, value in originals[key].items()
        ):
            raise ValueError(
                f"{path.name} row {line}: original Human finding evidence changed for {key}"
            )
        if None in row or any(value is None for value in row.values()):
            raise ValueError(
                f"{path.name} row {line}: invalid CSV row; preserve all columns"
            )
        result[key] = row
    return result


def approve_human_finding_mapping_review(
    directory: Path, reviewer: str, output: Path | None = None
) -> Path:
    """Validate human CSV decisions and generate portable approved evidence expectations."""
    if not reviewer.strip():
        raise ValueError("A Human finding mapping reviewer description is required")
    evidence_path = directory / "evidence.json"
    if (
        hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        != (directory / "evidence.sha256").read_text().strip()
    ):
        raise ValueError(
            "Prepared Human finding mapping evidence checksum changed; prepare a new review"
        )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    humans = evidence["human_findings"]
    by_id = {finding["human_finding_id"]: finding for finding in humans}
    classifications = _read_review(
        directory / "classifications.csv",
        CLASSIFICATION_COLUMNS,
        [_human_columns(finding) for finding in humans],
        ("human_finding_id",),
    )
    expected_matches = [
        {"source_url": page["source_url"], **_human_columns(by_id[identity])}
        for page in evidence["pages"]
        for identity in page["human_finding_ids"]
    ]
    matches = _read_review(
        directory / "programmatic-review.csv",
        MATCH_COLUMNS,
        expected_matches,
        ("source_url", "human_finding_id"),
    )
    decisions = {}
    for identity in by_id:
        row = classifications[(identity,)]
        if (
            row["classification"].strip() not in ELIGIBILITY_VALUES
            or not row["classification_reason"].strip()
        ):
            raise ValueError(
                f"classifications.csv Human finding {identity}: fill a valid classification and classification_reason"
            )
        decisions[identity] = {
            "human_finding_id": identity,
            "classification": row["classification"].strip(),
            "classification_reason": row["classification_reason"].strip(),
            "programmatic_by_page": {},
        }
    for page in evidence["pages"]:
        snapshot = (directory / page["snapshot"]).resolve()
        if (
            not snapshot.is_relative_to(directory.resolve())
            or hashlib.sha256(snapshot.read_bytes()).hexdigest()
            != page["snapshot_sha256"]
        ):
            raise ValueError(
                f"Prepared snapshot changed for {page['source_url']}; prepare a new review"
            )
        for identity in page["human_finding_ids"]:
            row = matches[(page["source_url"], identity)]
            prefix = f"programmatic-review.csv Human finding {identity} on {page['source_url']}"
            reason = row["programmatic_reason"].strip()
            if not reason:
                raise ValueError(
                    f"{prefix}: explain the complete match or deliberate absence in programmatic_reason"
                )
            expectations = []
            for ref in (
                part.strip()
                for part in row["programmatic_finding_refs"].split(";")
                if part.strip()
            ):
                if ref not in page["findings"]:
                    raise ValueError(
                        f"{prefix}: unknown or wrong-page Programmatic finding reference {ref}"
                    )
                finding = page["findings"][ref]
                expectations.append(
                    {
                        "rule": finding["problem_family"],
                        "evidence": {"raw_source": finding["raw_source"]},
                    }
                )
            decisions[identity]["programmatic_by_page"][page["source_url"]] = {
                "expectations": expectations,
                "reason": reason,
            }
    mapping = {
        "schema_version": 1,
        "human_audit_sha256": evidence["human_audit_sha256"],
        "approved_by": reviewer.strip(),
        "decisions": list(decisions.values()),
    }
    validate_human_finding_mapping(mapping, evidence["human_audit_sha256"])
    for page in evidence["pages"]:
        resolved_decisions(
            mapping,
            {
                "human_audit_sha256": evidence["human_audit_sha256"],
                "human_findings": [
                    by_id[identity] for identity in page["human_finding_ids"]
                ],
            },
            page["source_url"],
            list(page["findings"].values()),
        )
    output = output or directory / "human-finding-mapping.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    return output
