"""Immutable benchmark snapshots for model evaluation."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from vision_aid.evaluation.workspace import PrivateInputError, PrivateWorkspace

SNAPSHOT_HTML_FILENAME = "pristine-homepage.html"
SNAPSHOT_METADATA_FILENAME = "pristine-homepage.json"
DAT_VISION_AID_FIXTURE = "dat_visionaid_home.html"
HTTP_TIMEOUT = (5, 30)


@dataclass(frozen=True)
class BenchmarkSnapshot:
    """A verified raw HTML benchmark and its provenance record."""

    html_path: Path
    metadata_path: Path
    metadata: dict[str, Any]
    reused: bool


def prepare_benchmark_snapshot(
    workspace: PrivateWorkspace,
    source_url: str,
    temporal_assumption: str | None,
) -> BenchmarkSnapshot:
    """Capture a benchmark once or verify an existing immutable capture."""
    _require_http_source(source_url)
    html_path = workspace.root / "snapshots" / SNAPSHOT_HTML_FILENAME
    metadata_path = workspace.root / "snapshots" / SNAPSHOT_METADATA_FILENAME

    if html_path.exists() or metadata_path.exists():
        return _load_snapshot(
            html_path,
            metadata_path,
            source_url,
            temporal_assumption,
        )

    assumption = (temporal_assumption or "").strip()
    if not assumption:
        raise PrivateInputError(
            "A new benchmark snapshot requires --temporal-assumption so the "
            "stakeholder-supported relationship to the workbook audit is explicit."
        )

    import requests

    try:
        response = requests.get(source_url, timeout=HTTP_TIMEOUT)
    except requests.RequestException as error:
        raise PrivateInputError(
            f"Could not retrieve Pristine benchmark source {source_url}: {error}"
        ) from error

    if response.status_code != 200:
        raise PrivateInputError(
            f"Pristine benchmark source returned HTTP {response.status_code}; "
            "no snapshot was saved."
        )
    content_type = response.headers.get("Content-Type")
    if content_type is not None and not content_type.lower().startswith("text/html"):
        raise PrivateInputError(
            f"Pristine benchmark source returned {content_type!r}, not raw HTML; "
            "no snapshot was saved."
        )
    body = response.content
    if not body:
        raise PrivateInputError(
            "Pristine benchmark source returned an empty body; no snapshot was saved."
        )

    metadata = {
        "byte_length": len(body),
        "html_file": SNAPSHOT_HTML_FILENAME,
        "http": {
            "content_length": response.headers.get("Content-Length"),
            "content_type": content_type,
            "etag": response.headers.get("ETag"),
            "final_url": response.url,
            "last_modified": response.headers.get("Last-Modified"),
            "status_code": response.status_code,
        },
        "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "source_url": source_url,
        "temporal_assumption": assumption,
    }
    _save_new_snapshot(html_path, metadata_path, body, metadata)
    return BenchmarkSnapshot(html_path, metadata_path, metadata, reused=False)


def _require_http_source(source_url: str) -> None:
    """Reject local substitutes and malformed benchmark source URLs."""
    parsed = urlparse(source_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return
    if Path(source_url).name == DAT_VISION_AID_FIXTURE:
        raise PrivateInputError(
            "The DAT Vision Aid fixture is not a Pristine benchmark input. "
            "Capture the authorized Pristine homepage over HTTP(S)."
        )
    raise PrivateInputError(
        "Benchmark snapshot sources must be HTTP(S) URLs. Local HTML files "
        "cannot substitute for the Pristine homepage."
    )


def _load_snapshot(
    html_path: Path,
    metadata_path: Path,
    source_url: str,
    temporal_assumption: str | None,
) -> BenchmarkSnapshot:
    """Validate an existing snapshot without fetching or changing it."""
    if not html_path.is_file() or not metadata_path.is_file():
        raise PrivateInputError(
            "The benchmark snapshot is incomplete. It will not be refetched or "
            "overwritten; restore the matching HTML and metadata files."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PrivateInputError(
            "The benchmark snapshot metadata is unreadable. The existing "
            "snapshot will not be overwritten."
        ) from error
    if not isinstance(metadata, dict):
        raise PrivateInputError(
            "The benchmark snapshot metadata is invalid. The existing snapshot "
            "will not be overwritten."
        )

    recorded_url = metadata.get("source_url")
    if recorded_url != source_url:
        raise PrivateInputError(
            f"The existing benchmark snapshot was captured from {recorded_url!r}, "
            f"not {source_url!r}. It will not be refetched or overwritten."
        )
    supplied_assumption = (temporal_assumption or "").strip()
    if (
        supplied_assumption
        and supplied_assumption != metadata.get("temporal_assumption")
    ):
        raise PrivateInputError(
            "The supplied temporal assumption differs from the immutable snapshot "
            "metadata. The existing snapshot will not be overwritten."
        )

    body = html_path.read_bytes()
    actual_sha256 = hashlib.sha256(body).hexdigest()
    if metadata.get("sha256") != actual_sha256:
        raise PrivateInputError(
            "The benchmark snapshot checksum does not match its metadata. The "
            "existing snapshot will not be refetched or overwritten."
        )
    if metadata.get("byte_length") != len(body):
        raise PrivateInputError(
            "The benchmark snapshot byte length does not match its metadata. The "
            "existing snapshot will not be refetched or overwritten."
        )
    if metadata.get("html_file") != html_path.name:
        raise PrivateInputError(
            "The benchmark metadata identifies a different HTML file. The "
            "existing snapshot will not be refetched or overwritten."
        )
    return BenchmarkSnapshot(html_path, metadata_path, metadata, reused=True)


def _save_new_snapshot(
    html_path: Path,
    metadata_path: Path,
    body: bytes,
    metadata: dict[str, Any],
) -> None:
    """Create both snapshot artifacts exclusively so neither is overwritten."""
    metadata_bytes = (
        json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    try:
        with html_path.open("xb") as html_file:
            html_file.write(body)
        with metadata_path.open("xb") as metadata_file:
            metadata_file.write(metadata_bytes)
    except FileExistsError as error:
        raise PrivateInputError(
            "A benchmark snapshot artifact appeared during capture. It was not "
            "overwritten; rerun prepare to verify the existing snapshot."
        ) from error
