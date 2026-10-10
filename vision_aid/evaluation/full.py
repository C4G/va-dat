"""Coordinate Full evaluation preparation and saved Benchmark snapshots."""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests

from vision_aid.evaluation.human_audit import list_audit_urls
from vision_aid.evaluation.llm_audit import write_json


def capture_snapshots(human_audit: Path, output_dir: Path) -> Path:
    """Download only listed pages and publish their mapping after all succeed."""
    urls = list_audit_urls(human_audit)
    audit_checksum = hashlib.sha256(human_audit.read_bytes()).hexdigest()
    output_dir.mkdir(parents=True)
    snapshots = []
    for number, source_url in enumerate(urls, start=1):
        response = requests.get(source_url, allow_redirects=True)
        response.raise_for_status()
        html = f"page-{number:03d}.html"
        (output_dir / html).write_bytes(response.content)
        snapshots.append({"source_url": source_url, "html": html})
    mapping = output_dir / "snapshots.json"
    write_json(mapping, {
        "human_audit_filename": human_audit.name,
        "human_audit_sha256": audit_checksum,
        "snapshots": snapshots,
    })
    return mapping
